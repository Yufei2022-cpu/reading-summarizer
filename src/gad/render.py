"""Output rendering for GAD."""

import json
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional

from gad.config import get_settings
from gad.models import ArticleMeta, SeenRecord, SourceType


logger = logging.getLogger(__name__)


def slugify(text: str, max_length: int = 50) -> str:
    """Convert text to a URL-friendly slug.

    Args:
        text: The text to slugify.
        max_length: Maximum length of the slug.

    Returns:
        URL-friendly slug string.
    """
    # Normalize unicode
    text = unicodedata.normalize("NFKD", text)
    # Convert to ASCII
    text = text.encode("ascii", "ignore").decode("ascii")
    # Lowercase
    text = text.lower()
    # Replace spaces and special chars with hyphens
    text = re.sub(r"[^a-z0-9]+", "-", text)
    # Remove leading/trailing hyphens
    text = text.strip("-")
    # Truncate
    if len(text) > max_length:
        text = text[:max_length].rsplit("-", 1)[0]

    return text or "untitled"


def get_article_path(
    title: str,
    fetched_at: datetime,
    base_dir: Optional[Path] = None,
) -> Path:
    """Generate the storage path for an article.

    Path format: library/<YYYY>/<MM>/<slug>/

    Args:
        title: Article title for slug generation.
        fetched_at: Fetch timestamp for date-based path.
        base_dir: Base library directory, uses config default if None.

    Returns:
        Path to the article directory.
    """
    if base_dir is None:
        settings = get_settings()
        base_dir = settings.library_dir

    year = fetched_at.strftime("%Y")
    month = fetched_at.strftime("%m")
    slug = slugify(title)

    # Add timestamp suffix to avoid collisions
    timestamp_suffix = fetched_at.strftime("%H%M%S")
    slug_with_time = f"{slug}-{timestamp_suffix}"

    return base_dir / year / month / slug_with_time


def write_article(
    meta: ArticleMeta,
    content: str,
    summary: str,
    base_dir: Optional[Path] = None,
) -> Path:
    """Write article files to the library.

    Creates:
    - meta.json: Article metadata
    - content.txt: Clean extracted text
    - summary.md: LLM-generated summary

    Args:
        meta: Article metadata.
        content: Extracted text content.
        summary: Generated summary.
        base_dir: Base library directory, uses config default if None.

    Returns:
        Path to the article directory.
    """
    article_dir = get_article_path(meta.title, meta.fetched_at, base_dir)
    article_dir.mkdir(parents=True, exist_ok=True)

    # Write meta.json
    meta_file = article_dir / "meta.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta.model_dump(mode="json"), f, indent=2, default=str)
    logger.debug(f"Wrote meta.json: {meta_file}")

    # Write content.txt
    content_file = article_dir / "content.txt"
    with open(content_file, "w", encoding="utf-8") as f:
        f.write(content)
    logger.debug(f"Wrote content.txt: {content_file}")

    # Write summary.md
    summary_file = article_dir / "summary.md"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(summary)
    logger.debug(f"Wrote summary.md: {summary_file}")

    logger.info(f"Article saved to: {article_dir}")
    return article_dir


def load_articles_for_date(
    date: datetime,
    base_dir: Optional[Path] = None,
) -> list[tuple[ArticleMeta, Path]]:
    """Load all articles for a specific date.

    Args:
        date: The date to load articles for.
        base_dir: Base library directory, uses config default if None.

    Returns:
        List of (metadata, article_dir) tuples.
    """
    if base_dir is None:
        settings = get_settings()
        base_dir = settings.library_dir

    year = date.strftime("%Y")
    month = date.strftime("%m")

    month_dir = base_dir / year / month
    if not month_dir.exists():
        return []

    articles = []
    for article_dir in month_dir.iterdir():
        if not article_dir.is_dir():
            continue

        meta_file = article_dir / "meta.json"
        if not meta_file.exists():
            continue

        try:
            with open(meta_file, encoding="utf-8") as f:
                meta_data = json.load(f)
            meta = ArticleMeta.model_validate(meta_data)

            # Check if fetched on the target date
            if meta.fetched_at.date() == date.date():
                articles.append((meta, article_dir))
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Invalid meta.json in {article_dir}: {e}")

    return articles


def generate_digest(
    date: Optional[datetime] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    """Generate a daily digest markdown file.

    Args:
        date: Date for the digest, defaults to today.
        output_dir: Directory for digest files, uses config default if None.

    Returns:
        Path to the generated digest file.
    """
    if date is None:
        date = datetime.now()

    if output_dir is None:
        settings = get_settings()
        output_dir = settings.digest_dir

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load articles for the date
    articles = load_articles_for_date(date)

    # Sort by fetch time
    articles.sort(key=lambda x: x[0].fetched_at)

    # Generate digest content
    date_str = date.strftime("%Y-%m-%d")
    lines = [
        f"# Daily Reading Digest: {date_str}",
        "",
        f"*Generated: {datetime.now().isoformat()}*",
        "",
    ]

    if not articles:
        lines.extend([
            "No articles ingested on this date.",
            "",
        ])
    else:
        lines.extend([
            f"## Summary",
            "",
            f"- **Articles ingested**: {len(articles)}",
            f"- **Total words**: {sum(m.word_count for m, _ in articles):,}",
            "",
            "---",
            "",
            "## Articles",
            "",
        ])

        for meta, article_dir in articles:
            summary_file = article_dir / "summary.md"

            # Read TL;DR from summary if available
            tldr = "Summary not available."
            if summary_file.exists():
                with open(summary_file, encoding="utf-8") as f:
                    summary_content = f.read()
                # Extract TL;DR section
                if "## TL;DR" in summary_content:
                    tldr_match = re.search(
                        r"## TL;DR\s*\n(.+?)(?=\n##|\n---|\Z)",
                        summary_content,
                        re.DOTALL,
                    )
                    if tldr_match:
                        tldr = tldr_match.group(1).strip()

            lines.extend([
                f"### {meta.title}",
                "",
                f"- **URL**: [{meta.url}]({meta.url})",
                f"- **Words**: {meta.word_count:,}",
                f"- **Source**: {meta.source.value}",
                f"- **Tags**: {', '.join(meta.tags) if meta.tags else 'none'}",
                "",
                f"**Summary**: {tldr}",
                "",
                f"[Read full summary]({summary_file.relative_to(output_dir.parent)})",
                "",
                "---",
                "",
            ])

    # Write digest file
    digest_file = output_dir / f"{date_str}.md"
    with open(digest_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"Generated digest: {digest_file}")
    return digest_file


def create_seen_record(
    url: str,
    url_hash: str,
    content_hash: str,
    title: str,
    stored_path: Path,
    source: SourceType,
    fetched_at: Optional[datetime] = None,
) -> SeenRecord:
    """Create a SeenRecord for the seen.jsonl file.

    Args:
        url: Original URL.
        url_hash: SHA256 hash of normalized URL.
        content_hash: SHA256 hash of content.
        title: Article title.
        stored_path: Path where article was stored.
        source: How the article was ingested.
        fetched_at: Fetch timestamp, defaults to now.

    Returns:
        SeenRecord instance.
    """
    if fetched_at is None:
        fetched_at = datetime.now()

    return SeenRecord(
        url=url,
        url_hash=url_hash,
        content_hash=content_hash,
        title=title,
        fetched_at=fetched_at,
        stored_path=str(stored_path),
        source=source,
    )
