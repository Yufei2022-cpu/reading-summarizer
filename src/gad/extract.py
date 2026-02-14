"""Content extraction from HTML for GAD."""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from gad.models import ExtractedContent


logger = logging.getLogger(__name__)


# Try to import trafilatura, fall back to None if not available
try:
    import trafilatura
    from trafilatura.settings import use_config

    # Configure trafilatura for better extraction
    TRAFILATURA_CONFIG = use_config()
    TRAFILATURA_CONFIG.set("DEFAULT", "EXTRACTION_TIMEOUT", "30")
    HAS_TRAFILATURA = True
except ImportError:
    trafilatura = None  # type: ignore
    TRAFILATURA_CONFIG = None
    HAS_TRAFILATURA = False
    logger.warning("trafilatura not available, using fallback extraction")


def normalize_whitespace(text: str) -> str:
    """Collapse multiple whitespace characters into single spaces.

    Args:
        text: The text to normalize.

    Returns:
        Text with collapsed whitespace.
    """
    # Replace multiple whitespace (including newlines) with single space
    text = re.sub(r"\s+", " ", text)
    # Strip leading/trailing whitespace
    text = text.strip()
    return text


def extract_meta_info(html: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract title, author, and published date from HTML meta tags.

    Args:
        html: The HTML content.

    Returns:
        Tuple of (title, author, published_date), any can be None.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Try Open Graph title
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()

    # Extract author
    author = None
    author_meta = soup.find("meta", attrs={"name": "author"})
    if author_meta and author_meta.get("content"):
        author = author_meta["content"].strip()

    # Try article:author
    article_author = soup.find("meta", property="article:author")
    if article_author and article_author.get("content"):
        author = article_author["content"].strip()

    # Extract published date
    published_date = None
    date_meta = soup.find("meta", property="article:published_time")
    if date_meta and date_meta.get("content"):
        published_date = date_meta["content"].strip()

    # Try other date meta tags
    if not published_date:
        date_meta = soup.find("meta", attrs={"name": "date"})
        if date_meta and date_meta.get("content"):
            published_date = date_meta["content"].strip()

    return title, author, published_date


def extract_with_trafilatura(html: str, url: Optional[str] = None) -> Optional[str]:
    """Extract main content using trafilatura.

    Args:
        html: The HTML content.
        url: Optional URL for context.

    Returns:
        Extracted text or None if extraction failed.
    """
    if not HAS_TRAFILATURA:
        return None

    try:
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            config=TRAFILATURA_CONFIG,
        )
        if text:
            logger.debug("Successfully extracted with trafilatura")
            return text
    except Exception as e:
        logger.warning(f"trafilatura extraction failed: {e}")

    return None


def extract_with_beautifulsoup(html: str) -> str:
    """Extract text content using BeautifulSoup as fallback.

    Args:
        html: The HTML content.

    Returns:
        Extracted text content.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style", "nav", "header", "footer", "aside"]):
        element.decompose()

    # Try to find main content areas
    main_content = None
    for selector in ["article", "main", '[role="main"]', ".content", "#content"]:
        if selector.startswith(".") or selector.startswith("#"):
            main_content = soup.select_one(selector)
        else:
            main_content = soup.find(selector)
        if main_content:
            break

    if main_content:
        text = main_content.get_text(separator=" ", strip=True)
    else:
        # Fall back to body
        body = soup.find("body")
        if body:
            text = body.get_text(separator=" ", strip=True)
        else:
            text = soup.get_text(separator=" ", strip=True)

    return text


def extract_content(html: str, url: Optional[str] = None) -> ExtractedContent:
    """Extract clean text content from HTML.

    Uses trafilatura as primary extractor with BeautifulSoup fallback.

    Args:
        html: The HTML content.
        url: Optional URL for context.

    Returns:
        ExtractedContent with title, author, text, and word count.
    """
    logger.debug(f"Extracting content from HTML ({len(html)} chars)")

    # Extract metadata first
    title, author, published_date = extract_meta_info(html)

    # Try trafilatura first
    text = extract_with_trafilatura(html, url)

    # Fall back to BeautifulSoup
    if not text or len(text.strip()) < 100:
        logger.debug("Using BeautifulSoup fallback extraction")
        text = extract_with_beautifulsoup(html)

    # Normalize whitespace
    text = normalize_whitespace(text)

    if not text:
        logger.warning("No content could be extracted")
        text = ""

    return ExtractedContent.from_text(
        text=text,
        title=title or "Untitled",
        author=author,
        published_date=published_date,
    )
