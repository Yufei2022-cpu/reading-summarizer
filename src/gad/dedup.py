"""Deduplication logic for GAD."""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

from gad.config import get_settings
from gad.models import SeenRecord


logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """Normalize a URL for consistent hashing.

    Normalization steps:
    - Lowercase scheme and host
    - Remove default ports (80, 443)
    - Remove trailing slashes
    - Sort query parameters
    - Remove common tracking parameters

    Args:
        url: The URL to normalize.

    Returns:
        Normalized URL string.
    """
    parsed = urlparse(url)

    # Lowercase scheme and host
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Remove default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    # Normalize path - remove trailing slash (except for root)
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Sort query parameters and remove tracking params
    tracking_params = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "ref",
        "source",
        "fbclid",
        "gclid",
    }

    query_parts = []
    if parsed.query:
        for param in sorted(parsed.query.split("&")):
            if "=" in param:
                key = param.split("=")[0]
                if key.lower() not in tracking_params:
                    query_parts.append(param)

    query = "&".join(query_parts)

    # Reconstruct URL without fragment
    normalized = urlunparse((scheme, netloc, path, "", query, ""))

    return normalized


def normalize_text(text: str) -> str:
    """Normalize text for consistent content hashing.

    Args:
        text: The text to normalize.

    Returns:
        Normalized text string.
    """
    # Lowercase
    text = text.lower()
    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text)
    # Strip
    text = text.strip()
    return text


def compute_url_hash(url: str) -> str:
    """Compute SHA256 hash of normalized URL.

    Args:
        url: The URL to hash.

    Returns:
        Hex digest of the hash.
    """
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_content_hash(text: str) -> str:
    """Compute SHA256 hash of normalized content.

    Args:
        text: The text content to hash.

    Returns:
        Hex digest of the hash.
    """
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def load_seen_records(seen_file: Optional[Path] = None) -> dict[str, SeenRecord]:
    """Load all seen records from the JSONL file.

    Args:
        seen_file: Path to seen.jsonl file, uses config default if None.

    Returns:
        Dict mapping url_hash to SeenRecord.
    """
    if seen_file is None:
        settings = get_settings()
        seen_file = settings.seen_file

    records: dict[str, SeenRecord] = {}

    if not seen_file.exists():
        return records

    try:
        with open(seen_file, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    record = SeenRecord.model_validate(data)
                    records[record.url_hash] = record
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Invalid record at line {line_num}: {e}")
    except OSError as e:
        logger.error(f"Error reading seen file: {e}")

    logger.debug(f"Loaded {len(records)} seen records")
    return records


def get_content_hashes(seen_file: Optional[Path] = None) -> set[str]:
    """Get all content hashes from seen records.

    Args:
        seen_file: Path to seen.jsonl file, uses config default if None.

    Returns:
        Set of content hashes.
    """
    records = load_seen_records(seen_file)
    return {r.content_hash for r in records.values()}


def is_duplicate(
    url: str,
    content: Optional[str] = None,
    seen_file: Optional[Path] = None,
) -> tuple[bool, Optional[str]]:
    """Check if a URL or content is a duplicate.

    Args:
        url: The URL to check.
        content: Optional content text to check.
        seen_file: Path to seen.jsonl file, uses config default if None.

    Returns:
        Tuple of (is_duplicate, reason).
        Reason is None if not duplicate, otherwise describes why.
    """
    url_hash = compute_url_hash(url)
    records = load_seen_records(seen_file)

    # Check URL hash
    if url_hash in records:
        return True, f"URL already seen: {records[url_hash].title}"

    # Check content hash if provided
    if content:
        content_hash = compute_content_hash(content)
        content_hashes = {r.content_hash for r in records.values()}
        if content_hash in content_hashes:
            # Find the matching record
            for record in records.values():
                if record.content_hash == content_hash:
                    return True, f"Content matches existing: {record.title}"

    return False, None


def record_seen(record: SeenRecord, seen_file: Optional[Path] = None) -> None:
    """Append a record to the seen.jsonl file.

    Args:
        record: The SeenRecord to append.
        seen_file: Path to seen.jsonl file, uses config default if None.
    """
    if seen_file is None:
        settings = get_settings()
        seen_file = settings.seen_file

    # Ensure parent directory exists
    seen_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(seen_file, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")
        logger.debug(f"Recorded seen: {record.title}")
    except OSError as e:
        logger.error(f"Error writing to seen file: {e}")
        raise
