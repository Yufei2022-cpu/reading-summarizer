"""URL and RSS feed fetching for GAD."""

import logging
from typing import Optional
from urllib.parse import urlparse

import feedparser
import httpx

from gad.config import get_settings
from gad.models import FeedItem


logger = logging.getLogger(__name__)


class FetchError(Exception):
    """Error fetching a URL."""

    pass


def fetch_url(url: str, timeout: Optional[int] = None) -> str:
    """Fetch the HTML content of a URL.

    Args:
        url: The URL to fetch.
        timeout: Optional timeout override in seconds.

    Returns:
        The HTML content as a string.

    Raises:
        FetchError: If the request fails.
    """
    settings = get_settings()
    timeout = timeout or settings.http.timeout

    headers = {
        "User-Agent": settings.http.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        logger.debug(f"Fetching URL: {url}")
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            return response.text
    except httpx.TimeoutException as e:
        logger.error(f"Timeout fetching {url}: {e}")
        raise FetchError(f"Timeout fetching URL: {url}") from e
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching {url}: {e.response.status_code}")
        raise FetchError(f"HTTP {e.response.status_code} for URL: {url}") from e
    except httpx.RequestError as e:
        logger.error(f"Request error fetching {url}: {e}")
        raise FetchError(f"Failed to fetch URL: {url}") from e


def is_feed_url(url: str) -> bool:
    """Check if a URL is likely an RSS/Atom feed.

    Uses heuristics based on URL path and common feed patterns.

    Args:
        url: The URL to check.

    Returns:
        True if the URL is likely a feed.
    """
    parsed = urlparse(url)
    path = parsed.path.lower()

    # Common feed URL patterns
    feed_indicators = [
        "/feed",
        "/rss",
        "/atom",
        ".rss",
        ".atom",
        ".xml",
        "/feeds/",
        "feed.xml",
        "rss.xml",
        "atom.xml",
        "index.xml",
    ]

    return any(indicator in path for indicator in feed_indicators)


def parse_feed(url: str, limit: Optional[int] = None) -> list[FeedItem]:
    """Parse an RSS/Atom feed and extract items.

    Args:
        url: The feed URL.
        limit: Optional maximum number of items to return.

    Returns:
        List of FeedItem objects.

    Raises:
        FetchError: If the feed cannot be parsed.
    """
    logger.debug(f"Parsing feed: {url}")

    try:
        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            logger.error(f"Failed to parse feed {url}: {feed.bozo_exception}")
            raise FetchError(f"Failed to parse feed: {url}")

        items: list[FeedItem] = []
        for entry in feed.entries:
            if limit is not None and len(items) >= limit:
                break

            link = entry.get("link", "")
            if not link:
                continue

            title = entry.get("title", "Untitled")
            published = entry.get("published", entry.get("updated"))

            items.append(FeedItem(title=title, link=link, published=published))

        logger.info(f"Parsed {len(items)} items from feed: {url}")
        return items

    except Exception as e:
        if isinstance(e, FetchError):
            raise
        logger.error(f"Error parsing feed {url}: {e}")
        raise FetchError(f"Failed to parse feed: {url}") from e


def detect_and_parse_source(url: str, limit: Optional[int] = None) -> list[str]:
    """Detect if a URL is a feed or article and return URLs to ingest.

    Args:
        url: The source URL (can be an article or feed).
        limit: Optional limit on number of URLs from feeds.

    Returns:
        List of article URLs to ingest.
    """
    if is_feed_url(url):
        try:
            items = parse_feed(url, limit=limit)
            return [item.link for item in items]
        except FetchError:
            logger.warning(f"Failed to parse as feed, treating as article: {url}")
            return [url]
    else:
        # Try parsing as feed anyway (some feeds don't have obvious URLs)
        try:
            items = parse_feed(url, limit=limit)
            if items:
                return [item.link for item in items]
        except FetchError:
            pass

        # Treat as direct article URL
        return [url]
