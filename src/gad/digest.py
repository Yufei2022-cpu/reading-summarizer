"""Two-step digest pipeline for GAD.

Step 1 — pre_rank: score items locally (source weight, freshness, content length)
Step 2 — generate_digest_json: send Top-K to LLM, validate, cache result
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from gad.config import get_settings
from gad.models import DigestItemInput, DigestOutput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source weight table (higher = more authoritative)
# ---------------------------------------------------------------------------
_SOURCE_WEIGHTS: dict[str, int] = {
    "openai": 5,
    "anthropic": 5,
    "google": 5,
    "deepmind": 5,
    "meta": 5,
    "microsoft": 4,
    "nvidia": 4,
    "arxiv": 4,
    "huggingface": 4,
    "stability": 4,
    "mistral": 4,
    "cohere": 4,
    "together": 3,
    "github": 3,
    "techcrunch": 3,
    "theverge": 3,
    "venturebeat": 3,
    "hacker news": 2,
    "reddit": 2,
}


def _source_weight(item: DigestItemInput) -> int:
    """Return a 1-5 weight for the item's source domain."""
    src = (item.source or "").lower()
    url = item.url.lower()
    for key, weight in _SOURCE_WEIGHTS.items():
        if key in src or key in url:
            return weight
    return 2  # unknown source gets a neutral score


def _freshness_score(item: DigestItemInput) -> float:
    """0-5 score based on how recent the date is."""
    if not item.date:
        return 2.0
    try:
        # try ISO and common formats
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                dt = datetime.strptime(item.date[:19], fmt)
                break
            except ValueError:
                continue
        else:
            return 2.0
        days_old = (datetime.now(timezone.utc).replace(tzinfo=None) - dt).days
        if days_old <= 1:
            return 5.0
        if days_old <= 3:
            return 4.0
        if days_old <= 7:
            return 3.0
        if days_old <= 30:
            return 2.0
        return 1.0
    except Exception:
        return 2.0


def _content_length_score(item: DigestItemInput) -> float:
    """0-5 score based on available text length."""
    text = item.content or item.snippet or ""
    length = len(text)
    if length > 5000:
        return 5.0
    if length > 2000:
        return 4.0
    if length > 500:
        return 3.0
    if length > 100:
        return 2.0
    return 1.0


def pre_rank(
    items: list[DigestItemInput],
    top_k: int = 30,
) -> list[DigestItemInput]:
    """Step 1 — rank items locally and return the top-K candidates.

    Scoring formula: 0.4 * source_weight + 0.3 * freshness + 0.3 * content_length
    """
    scored: list[tuple[float, int, DigestItemInput]] = []
    for idx, item in enumerate(items):
        score = (
            0.4 * _source_weight(item)
            + 0.3 * _freshness_score(item)
            + 0.3 * _content_length_score(item)
        )
        scored.append((score, idx, item))

    scored.sort(key=lambda t: (-t[0], t[1]))
    top = [item for _, _, item in scored[:top_k]]
    logger.info("pre_rank: %d items → top %d", len(items), len(top))
    return top


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _items_hash(items: list[DigestItemInput]) -> str:
    """Deterministic SHA-256 of the item titles+urls (order-independent)."""
    keys = sorted(f"{it.title}|{it.url}" for it in items)
    blob = json.dumps(keys, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _cache_dir() -> Path:
    settings = get_settings()
    p = Path(settings.output_dir) / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_get(h: str) -> Optional[DigestOutput]:
    path = _cache_dir() / f"digest_{h}.json"
    if path.exists():
        logger.info("Cache HIT: %s", path.name)
        return DigestOutput.model_validate_json(path.read_text(encoding="utf-8"))
    return None


def _cache_put(h: str, output: DigestOutput) -> None:
    path = _cache_dir() / f"digest_{h}.json"
    path.write_text(
        output.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Cached digest → %s", path.name)


# ---------------------------------------------------------------------------
# LLM system prompt (the user's original prompt, trimmed for API use)
# ---------------------------------------------------------------------------

DIGEST_SYSTEM_PROMPT = r"""你是 "AI Frontier Web Digest Generator"。把输入 items 变成 UI-ready JSON（可直接渲染：顶部精选、分组列表、标签、搜索结果摘要、去重说明）。

【核心任务】
1) 去重与合并：同一事件/发布多篇文章，保留信息量最大的一条，其余放 duplicates。
2) 选"前沿 + 有用"：挑最值得读的内容进 top_stories（默认 8-12 条）。
3) 自动分组：按主题生成 sections（Models / Agents / Multimodal / Systems / Safety / Evaluation / Product / OpenSource / Policy / Other）。
4) 生成可渲染字段：卡片副标题、一句话结论、要点 bullets、阅读时长、重要度、可信度、行动建议。
5) 输出严格 JSON，不要任何额外文字。

【筛选与评分规则】
- credibility(1-5)：官方发布/论文/技术报告最高；二手解读较低。
- importance(1-5)：对行业影响范围 + 新颖度 + 可复用性综合。
- freshness(1-5)：越近越高；旧但突然重要（爆火/被大量引用）可高，但要在 notes 说明原因。
- 实话实说：不确定就写 "unknown"，不要编造。

【生成内容风格】
- 中文为主，关键术语可保留英文（如 "Agentic workflow"）。
- 一句话结论要像信息流卡片：<= 26 字，直接点题。
- bullets 是"事实/变化点/贡献点"，每条 <= 22 字，3-5 条。
- action_items 偏工程落地：例如"把 X 加入评测集""试用 Y 的 API""对比 A vs B"。

【输出 JSON Schema（必须完全符合）】
{
  "schema_version": "v1",
  "generated_at": "YYYY-MM-DD",
  "stats": { "items_in": N, "items_kept": N, "top_stories_count": N, "duplicates_count": N },
  "top_stories": [{
    "id": "kebab-case-stable-id",
    "title": "", "subtitle": "", "url": "", "source": "", "date": "",
    "section": "Models|Agents|Multimodal|Systems|Safety|Evaluation|Product|OpenSource|Policy|Other",
    "one_liner": "", "bullets": ["","",""],
    "why_it_matters": "", "action_items": ["",""],
    "read_time_min": N,
    "scores": { "importance": 1-5, "credibility": 1-5, "freshness": 1-5 },
    "tags": [], "notes": ""
  }],
  "sections": [{ "name": "...", "items": [{ "ref_id": "", "title": "", "url": "", "source": "", "date": "", "one_liner": "", "scores": {...}, "tags": [] }] }],
  "tag_index": { "tag": ["ref_id1"] },
  "search_summaries": [{ "query_hint": "", "matching_tags": [], "top_refs": [], "one_sentence_map": "" }],
  "duplicates": [{ "title": "", "url": "", "merged_into": "ref_id", "reason": "" }]
}

【重要】
- 必须输出合法 JSON（双引号、无注释、无尾逗号）。
- 不要输出 Markdown 或其他包裹。
- 若 date/source 缺失，用 "unknown"。
- id 生成规则：对 title 做简化 slug，必要时加 source 前缀避免冲突。
"""


# ---------------------------------------------------------------------------
# Step 2 — call LLM or mock
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """Simple slug generator for item IDs."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text)
    return text.strip("-")[:60]


def _mock_digest(items: list[DigestItemInput], all_count: int) -> DigestOutput:
    """Generate a structurally-valid mock digest without LLM."""
    logger.info("Using MockDigestGenerator (no API key)")
    today = datetime.now().strftime("%Y-%m-%d")

    top_stories = []
    section_map: dict[str, list] = {}

    for i, item in enumerate(items[:12]):
        sid = _slugify(item.title) or f"item-{i}"
        section = "Other"

        story = {
            "id": sid,
            "title": item.title,
            "subtitle": item.title[:40],
            "url": item.url,
            "source": item.source or "unknown",
            "date": item.date or "unknown",
            "section": section,
            "one_liner": item.title[:26],
            "bullets": [
                (item.snippet or item.title)[:22],
                f"来源: {item.source or 'unknown'}"[:22],
                f"日期: {item.date or 'unknown'}"[:22],
            ],
            "why_it_matters": "需要 LLM 生成详细分析",
            "action_items": ["配置 OPENAI_API_KEY 以获取完整摘要"],
            "read_time_min": max(1, len(item.content or item.snippet or "") // 1500),
            "scores": {"importance": 3, "credibility": 3, "freshness": 3},
            "tags": item.tags or ["untagged"],
            "notes": "Mock 生成，仅结构占位",
        }
        top_stories.append(story)

        sec_item = {
            "ref_id": sid,
            "title": item.title,
            "url": item.url,
            "source": item.source or "unknown",
            "date": item.date or "unknown",
            "one_liner": item.title[:26],
            "scores": {"importance": 3, "credibility": 3, "freshness": 3},
            "tags": item.tags or [],
        }
        section_map.setdefault(section, []).append(sec_item)

    sections = [{"name": k, "items": v} for k, v in section_map.items()]

    return DigestOutput.model_validate({
        "schema_version": "v1",
        "generated_at": today,
        "stats": {
            "items_in": all_count,
            "items_kept": len(top_stories),
            "top_stories_count": len(top_stories),
            "duplicates_count": 0,
        },
        "top_stories": top_stories,
        "sections": sections,
        "tag_index": {},
        "search_summaries": [],
        "duplicates": [],
    })


def generate_digest_json(
    items: list[DigestItemInput],
    all_count: int,
    *,
    use_cache: bool = True,
) -> DigestOutput:
    """Step 2 — send pre-ranked items to LLM and return validated DigestOutput.

    Falls back to mock generator if no API key is configured.
    """
    settings = get_settings()

    # Cache check
    h = _items_hash(items)
    if use_cache:
        cached = _cache_get(h)
        if cached is not None:
            return cached

    # No API key → mock
    if not settings.openai_api_key:
        result = _mock_digest(items, all_count)
        if use_cache:
            _cache_put(h, result)
        return result

    # Prepare items payload (strip long content to save tokens)
    items_payload = []
    for it in items:
        d = it.model_dump(exclude_none=True)
        # cap content at 3000 chars per item to save tokens
        if d.get("content") and len(d["content"]) > 3000:
            d["content"] = d["content"][:3000] + "…"
        items_payload.append(d)

    user_prompt = (
        f"items = {json.dumps(items_payload, ensure_ascii=False, indent=None)}\n\n"
        f"共 {all_count} 条原始输入，上面是 pre-rank 后的 Top {len(items)} 条。"
    )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        logger.info("Calling OpenAI (%s) for digest generation…", settings.model)

        response = client.chat.completions.create(
            model=settings.model,
            messages=[
                {"role": "system", "content": DIGEST_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.25,
            max_tokens=8000,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        result = DigestOutput.model_validate(data)

        if use_cache:
            _cache_put(h, result)

        return result

    except Exception as e:
        logger.error("LLM digest generation failed: %s — falling back to mock", e)
        result = _mock_digest(items, all_count)
        if use_cache:
            _cache_put(h, result)
        return result
