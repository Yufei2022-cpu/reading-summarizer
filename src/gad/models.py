"""Pydantic models for GAD data structures."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Source type for ingested articles."""

    MANUAL = "manual"
    RSS = "rss"


class SeenRecord(BaseModel):
    """Record stored in seen.jsonl for deduplication tracking."""

    url: str = Field(description="Original URL of the article")
    url_hash: str = Field(description="SHA256 hash of normalized URL")
    content_hash: str = Field(description="SHA256 hash of normalized content")
    title: str = Field(description="Article title")
    fetched_at: datetime = Field(description="When the article was fetched")
    stored_path: str = Field(description="Relative path to stored article directory")
    source: SourceType = Field(description="How the article was ingested")

    def model_dump_jsonl(self) -> str:
        """Serialize to JSON line format."""
        return self.model_dump_json()


class ArticleMeta(BaseModel):
    """Full metadata for a stored article."""

    title: str = Field(description="Article title")
    author: Optional[str] = Field(default=None, description="Author if found")
    published_date: Optional[str] = Field(default=None, description="Published date if found")
    url: str = Field(description="Original URL")
    url_hash: str = Field(description="SHA256 hash of normalized URL")
    content_hash: str = Field(description="SHA256 hash of content")
    fetched_at: datetime = Field(description="When the article was fetched")
    word_count: int = Field(description="Word count of extracted content")
    tags: list[str] = Field(default_factory=list, description="Tags applied to article")
    source: SourceType = Field(description="How the article was ingested")


class ExtractedContent(BaseModel):
    """Extracted content from an article."""

    title: str = Field(description="Article title")
    author: Optional[str] = Field(default=None, description="Author if found")
    published_date: Optional[str] = Field(default=None, description="Published date if found")
    text: str = Field(description="Clean extracted text content")
    word_count: int = Field(description="Word count of extracted text")

    @classmethod
    def from_text(
        cls,
        text: str,
        title: str = "Untitled",
        author: Optional[str] = None,
        published_date: Optional[str] = None,
    ) -> "ExtractedContent":
        """Create ExtractedContent from text with computed word count."""
        word_count = len(text.split())
        return cls(
            title=title,
            author=author,
            published_date=published_date,
            text=text,
            word_count=word_count,
        )


class FeedItem(BaseModel):
    """An item from an RSS/Atom feed."""

    title: str = Field(description="Item title")
    link: str = Field(description="Item URL")
    published: Optional[str] = Field(default=None, description="Published date")


class IngestResult(BaseModel):
    """Result of ingesting a single article."""

    url: str = Field(description="URL that was ingested")
    success: bool = Field(description="Whether ingestion succeeded")
    skipped: bool = Field(default=False, description="Whether skipped due to dedup")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    stored_path: Optional[str] = Field(default=None, description="Path where article was stored")
    title: Optional[str] = Field(default=None, description="Article title if extracted")


# ---------------------------------------------------------------------------
# Digest JSON models (for gad digest-json)
# ---------------------------------------------------------------------------

SectionName = str  # e.g. "Models", "Agents", "Multimodal", etc.


class DigestItemInput(BaseModel):
    """A single item fed into the digest pipeline."""

    title: str
    url: str
    source: Optional[str] = None
    date: Optional[str] = None
    snippet: Optional[str] = None
    content: Optional[str] = None
    author: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class DigestScores(BaseModel):
    """Importance / credibility / freshness triple."""

    importance: int = Field(ge=1, le=5)
    credibility: int = Field(ge=1, le=5)
    freshness: int = Field(ge=1, le=5)


class TopStory(BaseModel):
    """Full top-story card ready for rendering."""

    id: str
    title: str
    subtitle: str = Field(description="<= 40 chars")
    url: str
    source: str
    date: str
    section: str
    one_liner: str = Field(description="<= 26 chars headline")
    bullets: list[str] = Field(min_length=3, max_length=5)
    why_it_matters: str
    action_items: list[str]
    read_time_min: int
    scores: DigestScores
    tags: list[str]
    notes: str = ""


class SectionItem(BaseModel):
    """Lightweight item inside a section group."""

    ref_id: str
    title: str
    url: str
    source: str
    date: str
    one_liner: str
    scores: DigestScores
    tags: list[str] = Field(default_factory=list)


class Section(BaseModel):
    """A thematic group of items."""

    name: SectionName
    items: list[SectionItem]


class SearchSummary(BaseModel):
    """Pre-computed search hint for common queries."""

    query_hint: str
    matching_tags: list[str]
    top_refs: list[str]
    one_sentence_map: str


class DuplicateRecord(BaseModel):
    """A de-duplicated item that was merged into another."""

    title: str
    url: str
    merged_into: str
    reason: str


class DigestStats(BaseModel):
    """Aggregate counters for the digest."""

    items_in: int
    items_kept: int
    top_stories_count: int
    duplicates_count: int


class DigestOutput(BaseModel):
    """Root schema returned by gad digest-json."""

    schema_version: str = "v1"
    generated_at: str
    stats: DigestStats
    top_stories: list[TopStory]
    sections: list[Section]
    tag_index: dict[str, list[str]] = Field(default_factory=dict)
    search_summaries: list[SearchSummary] = Field(default_factory=list)
    duplicates: list[DuplicateRecord] = Field(default_factory=list)

