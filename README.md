# GAD - Good Article Digest

A lightweight, database-free article ingestion and summarization tool. Ingest high-quality articles from URLs and RSS feeds, extract clean text, deduplicate, summarize with an LLM, and store everything as local Markdown/JSON files.

## Features

- 📥 **Ingest articles** from URLs or RSS/Atom feeds
- 📝 **Extract clean text** using trafilatura with BeautifulSoup fallback
- 🔄 **Deduplicate** by URL hash and content hash
- 🤖 **Summarize** with OpenAI GPT models (or offline mock summarizer)
- 📁 **File-based storage** - no database required
- 📊 **Daily digests** - generate Markdown summaries of ingested articles
- 🖥️ **Cross-platform** - works on Windows and Linux

## Quickstart

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/reading-summarizer.git
cd reading-summarizer

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

### Configuration

```bash
# Copy the example config
cp configs/settings.example.yaml configs/settings.yaml

# Edit to customize (optional)
# Set your OpenAI API key for AI summaries
export OPENAI_API_KEY="sk-..."
```

### Basic Usage

```bash
# Check your setup
gad doctor

# Ingest a single article
gad ingest "https://example.com/interesting-article"

# Ingest with custom tags
gad ingest "https://example.com/article" --tag tech --tag ai

# Dry run to see what would happen
gad ingest "https://example.com/article" --dry-run

# Force re-ingest a duplicate
gad ingest "https://example.com/article" --force

# Run batch ingestion from sources file
gad run --sources configs/sources.txt --limit 5

# Generate a daily digest
gad digest

# Generate digest for a specific date
gad digest --date 2024-01-15
```

### 🖥️ Viewing the Web UI

This project includes a web frontend interface (located in the `web/` directory) to display your generated JSON digests. **Since GAD is a Python project, there is no need to install Node.js or run `npm run dev`.**

1. Place your generated `digest.json` into the `web/` directory.
2. Start the built-in Python HTTP server from the project root:

```bash
python -m http.server 8000 --directory web
```

3. Open your browser and navigate to `http://localhost:8000/` to view the digest.

## CLI Commands

### `gad ingest <url>`

Fetch, extract, and summarize a single article.

| Option | Description |
|--------|-------------|
| `--tag, -t` | Add tags to the article (repeatable) |
| `--dry-run, -n` | Show what would be done without writing |
| `--force, -f` | Ingest even if duplicate detected |
| `--verbose, -v` | Enable debug output |

### `gad run --sources <file>`

Batch ingest from a sources file containing URLs and RSS feeds.

| Option | Description |
|--------|-------------|
| `--sources, -s` | Path to sources file (default: configs/sources.txt) |
| `--limit, -l` | Max articles per source |
| `--verbose, -v` | Enable debug output |

### `gad digest`

Generate a daily digest Markdown file.

| Option | Description |
|--------|-------------|
| `--date, -d` | Date in YYYY-MM-DD format (default: today) |
| `--verbose, -v` | Enable debug output |

### `gad doctor`

Check dependencies, configuration, and directory permissions.

## Configuration

Copy `configs/settings.example.yaml` to `configs/settings.yaml`:

```yaml
# Output directory for all data
output_dir: ./data

# OpenAI model (requires OPENAI_API_KEY env var)
model: gpt-4o-mini

# Max characters to send to LLM
max_input_chars: 15000

# Default tags for all articles
default_tags:
  - reading-list

# HTTP settings
http:
  timeout: 30
  user_agent: "GAD/0.1"

# Logging level
log_level: INFO
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for AI summarization |
| `GAD_OUTPUT_DIR` | Override output directory |
| `GAD_LOG_LEVEL` | Override log level |

## Output Structure

All data is stored under the configured `output_dir` (default: `./data`):

```
data/
├── seen.jsonl              # Deduplication log (append-only)
├── library/                # Article storage
│   └── 2024/
│       └── 01/
│           └── article-slug-143052/
│               ├── meta.json      # Article metadata
│               ├── content.txt    # Clean extracted text
│               └── summary.md     # LLM-generated summary
└── daily_digest/
    └── 2024-01-15.md       # Daily summary
```

### meta.json

```json
{
  "title": "Article Title",
  "author": "John Doe",
  "published_date": "2024-01-15",
  "url": "https://example.com/article",
  "url_hash": "a1b2c3...",
  "content_hash": "d4e5f6...",
  "fetched_at": "2024-01-15T14:30:52",
  "word_count": 1500,
  "tags": ["tech", "ai"],
  "source": "manual"
}
```

### seen.jsonl

Each line is a JSON record:

```json
{"url": "...", "url_hash": "...", "content_hash": "...", "title": "...", "fetched_at": "...", "stored_path": "...", "source": "manual|rss"}
```

## Deduplication

GAD uses two-level deduplication:

1. **URL Hash**: SHA256 of normalized URL
   - Removes tracking parameters (utm_*, fbclid, etc.)
   - Normalizes case and trailing slashes
   - Catches exact URL duplicates

2. **Content Hash**: SHA256 of normalized text
   - Catches reposts with different URLs
   - Ignores whitespace and case differences

Skip duplicates by default. Use `--force` to re-ingest.

## Summarization

### With OpenAI API

Set `OPENAI_API_KEY` environment variable. Summaries include:

- **TL;DR**: 2-3 sentence executive summary
- **Problem/Motivation**: What the article addresses
- **Core Ideas/Methods**: Main concepts
- **Key Evidence/Examples**: Supporting data
- **Limitations/Open Questions**: Acknowledged gaps
- **Practical Implications**: Takeaways
- **Key Quotes**: Notable direct quotes

### Without API Key

Falls back to a mock summarizer that extracts:
- First few sentences as TL;DR
- Word count statistics
- Sample quote

## Limitations

- **Paywalled sites**: Cannot access content behind login walls
- **JavaScript-heavy pages**: May not extract dynamically-loaded content
- **Rate limits**: No built-in rate limiting; be respectful with batch ingestion
- **Large files**: Content truncated to `max_input_chars` before summarization
- **Rate limits**: No built-in rate limiting; be respectful with batch ingestion

## Manual Generation (No CLI)

You can generate `digest.json` without the Python backend — just paste the prompt below into any **LLM with web search** (ChatGPT-4o + Search, Gemini Advanced, Perplexity Pro).

> 💡 **Tip:** The prompt template is also available as a standalone file in `configs/digest_prompt.txt`. If you want to modify the search queries or rules, edit that file!

### Prompt Template

> **你可以直接打开 `configs/digest_prompt.txt` 复制，或者复制下面整段 prompt，粘贴到有联网能力的 LLM 中即可。**

````text
# AI Frontier Weekly Digest Generator

## Your Identity
You are a senior AI industry analyst and chief editor.
Your job: autonomously search the web, find the most impactful AI news
from the past 7 days, and produce a single machine-readable JSON file.

## Step 1 — Search (do this FIRST, before writing any JSON)

Search the web using the following queries (adapt to this week's events):
- "OpenAI announcement this week"
- "Anthropic Claude new release 2026"
- "Google DeepMind Gemini update"
- "Meta AI LLaMA new model"
- "AI funding round 2026"
- "AI safety policy regulation news"
- "Hugging Face open source model release"
- "NVIDIA AI chip inference"
- "AI agent framework tool release"
- "arXiv trending AI paper this week"

Also check these sites directly:
- openai.com/blog, anthropic.com/news, deepmind.google/discover
- huggingface.co/blog, blog.nvidia.com
- techcrunch.com/category/artificial-intelligence
- theverge.com/ai-artificial-intelligence
- arxiv.org (cs.AI, cs.CL, cs.LG — sort by recent)

## Step 2 — Filter & Rank

From everything you found, keep ONLY stories that meet at least one:
- 🏆 New SOTA model release or major model update
- 🔬 Significant research breakthrough (reasoning, agents, multimodal)
- 💰 Funding round > $100M or major acquisition
- ⚖️ Important policy/regulation/safety development
- 🛠️ Notable open-source release (>1k GitHub stars potential)
- 📊 Benchmark result that changes the leaderboard

DISCARD anything that is:
- Generic opinion pieces ("AI will change everything")
- Minor product updates or tutorials
- Rewritten press releases with no new information
- News older than 7 days

Target: 12–15 top stories.

## Step 3 — Generate JSON

Produce a SINGLE valid JSON object. No markdown fencing, no commentary, 
no explanation, and NO SEARCH LOGS — ONLY the raw JSON starting with `{`.

### Schema (v1)

{
  "schema_version": "v1",
  "generated_at": "<today's date YYYY-MM-DD>",
  "stats": {
    "items_in": <total articles you scanned>,
    "items_kept": <number of top_stories>,
    "top_stories_count": <same as items_kept>,
    "duplicates_count": <number of duplicates merged>
  },

  "top_stories": [
    {
      "id":             "<english-kebab-case-slug>",
      "title":          "<English headline>",
      "subtitle":       "<中文翻译标题>",
      "url":            "<canonical source URL — MUST be a real, working link>",
      "source":         "<publisher name>",
      "date":           "<YYYY-MM-DD>",
      "section":        "<one of: Models|Agents|Multimodal|Systems|Safety|Industry|OpenSource|Policy|Research>",
      "one_liner":      "<一句话中文摘要，不超过 30 字>",
      "bullets":        ["<要点1（中文）>", "<要点2>", "<要点3>", "<要点4>"],
      "why_it_matters": "<为什么重要（中文，2-3 句话）>",
      "action_items":   ["<建议行动1（中文）>", "<建议行动2>"],
      "read_time_min":  <estimated reading time in minutes>,
      "scores": {
        "importance":  <1-5>,
        "credibility": <1-5>,
        "freshness":   <1-5>
      },
      "tags":  ["<lowercase-tag-1>", "<lowercase-tag-2>"],
      "notes": "<可选备注，如'需等待同行评议'，无则留空>"
    }
  ],

  "sections": [
    {
      "name": "<section name, must match a section value used in top_stories>",
      "items": [
        {
          "ref_id":    "<id from top_stories>",
          "title":     "<title>",
          "url":       "<url>",
          "source":    "<source>",
          "date":      "<date>",
          "one_liner": "<one_liner (Chinese)>",
          "scores":    { "importance": 5, "credibility": 5, "freshness": 5 },
          "tags":      ["tag1"]
        }
      ]
    }
  ],

  "tag_index": {
    "<tag>": ["<story-id-1>", "<story-id-2>"]
  },

  "search_summaries": [
    {
      "query_hint":       "<搜索关键词，如 'openai gpt'>",
      "matching_tags":    ["<相关 tag>"],
      "top_refs":         ["<story-id>"],
      "one_sentence_map": "<一句话总结该主题（中文）>"
    }
  ],

  "duplicates": [
    {
      "title":       "<被合并的文章标题>",
      "url":         "<被合并的 URL>",
      "merged_into": "<保留的 story id>",
      "reason":      "<合并原因（中文）>"
    }
  ]
}

### Scoring Rubric

importance (影响力):
  5 = Industry-defining (new GPT-5 class model, >$10B funding)
  4 = Major (new SOTA on key benchmark, >$1B funding)
  3 = Notable (meaningful update, interesting research)
  2 = Minor (incremental improvement)
  1 = Low impact

credibility (可信度):
  5 = Official announcement or peer-reviewed paper
  4 = Reputable tech media with primary sources
  3 = Industry blog or credible analyst
  2 = Rumor from credible source
  1 = Unverified claim

freshness (时效性):
  5 = Published today or yesterday
  4 = Published 2-3 days ago
  3 = Published 4-5 days ago
  2 = Published 6-7 days ago
  1 = Older than 7 days

## Hard Rules
1. Every URL MUST be real. Do NOT hallucinate URLs.  
2. Every story MUST have appeared in a real publication in the last 7 days.
3. Language: Chinese for subtitle, one_liner, bullets, why_it_matters, 
   action_items, notes. English for title, id, tags, source.
4. Each top_story must appear in exactly ONE section.
5. tag_index must reference only IDs that exist in top_stories.
6. Generate 4-6 search_summaries covering the major themes of the week.
7. Output ONLY valid JSON starting with `{`. Do NOT output any search logs, markdown fences, or conversational text.
````
## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
uv run pytest -v

# Run type checking
uv run mypy src/

# Run linting
uv run ruff check src/
```

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.
