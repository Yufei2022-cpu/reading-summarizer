"""Tests for deduplication logic."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from gad.dedup import (
    compute_content_hash,
    compute_url_hash,
    is_duplicate,
    load_seen_records,
    normalize_text,
    normalize_url,
    record_seen,
)
from gad.models import SeenRecord, SourceType


class TestNormalizeUrl:
    """Tests for URL normalization."""

    def test_lowercase_scheme_and_host(self) -> None:
        """Should lowercase scheme and host."""
        url = "HTTPS://EXAMPLE.COM/Path"
        normalized = normalize_url(url)
        assert normalized.startswith("https://example.com")

    def test_remove_trailing_slash(self) -> None:
        """Should remove trailing slash from path."""
        url = "https://example.com/article/"
        normalized = normalize_url(url)
        assert not normalized.endswith("/")

    def test_preserve_root_slash(self) -> None:
        """Should preserve root path slash."""
        url = "https://example.com/"
        normalized = normalize_url(url)
        assert normalized == "https://example.com/"

    def test_remove_utm_parameters(self) -> None:
        """Should remove tracking parameters."""
        url = "https://example.com/article?utm_source=twitter&utm_medium=social&id=123"
        normalized = normalize_url(url)
        assert "utm_source" not in normalized
        assert "utm_medium" not in normalized
        assert "id=123" in normalized

    def test_sort_query_parameters(self) -> None:
        """Should sort query parameters alphabetically."""
        url = "https://example.com/article?z=1&a=2&m=3"
        normalized = normalize_url(url)
        assert normalized == "https://example.com/article?a=2&m=3&z=1"

    def test_remove_default_port_http(self) -> None:
        """Should remove default port 80 for HTTP."""
        url = "http://example.com:80/article"
        normalized = normalize_url(url)
        assert ":80" not in normalized

    def test_remove_default_port_https(self) -> None:
        """Should remove default port 443 for HTTPS."""
        url = "https://example.com:443/article"
        normalized = normalize_url(url)
        assert ":443" not in normalized


class TestNormalizeText:
    """Tests for text normalization."""

    def test_collapse_whitespace(self) -> None:
        """Should collapse multiple whitespace to single space."""
        text = "Hello    world\n\n\ntest"
        normalized = normalize_text(text)
        assert normalized == "hello world test"

    def test_strip_whitespace(self) -> None:
        """Should strip leading/trailing whitespace."""
        text = "  hello world  "
        normalized = normalize_text(text)
        assert normalized == "hello world"

    def test_lowercase(self) -> None:
        """Should convert to lowercase."""
        text = "Hello WORLD"
        normalized = normalize_text(text)
        assert normalized == "hello world"


class TestComputeHashes:
    """Tests for hash computation."""

    def test_url_hash_consistent(self) -> None:
        """Same URL should produce same hash."""
        url = "https://example.com/article"
        hash1 = compute_url_hash(url)
        hash2 = compute_url_hash(url)
        assert hash1 == hash2

    def test_url_hash_normalized(self) -> None:
        """Normalized URLs should produce same hash."""
        url1 = "https://example.com/article"
        url2 = "https://EXAMPLE.COM/article/"
        hash1 = compute_url_hash(url1)
        hash2 = compute_url_hash(url2)
        assert hash1 == hash2

    def test_content_hash_consistent(self) -> None:
        """Same content should produce same hash."""
        text = "This is test content"
        hash1 = compute_content_hash(text)
        hash2 = compute_content_hash(text)
        assert hash1 == hash2

    def test_content_hash_normalized(self) -> None:
        """Normalized content should produce same hash."""
        text1 = "Hello World"
        text2 = "hello   world"
        hash1 = compute_content_hash(text1)
        hash2 = compute_content_hash(text2)
        assert hash1 == hash2


class TestSeenRecords:
    """Tests for seen.jsonl operations."""

    def test_record_seen(self, temp_data_dir: Path) -> None:
        """Should append record to seen.jsonl."""
        seen_file = temp_data_dir / "seen.jsonl"

        record = SeenRecord(
            url="https://example.com/article",
            url_hash="abc123",
            content_hash="def456",
            title="Test Article",
            fetched_at=datetime.now(),
            stored_path="library/2024/01/test-article",
            source=SourceType.MANUAL,
        )

        record_seen(record, seen_file)

        assert seen_file.exists()
        with open(seen_file, encoding="utf-8") as f:
            line = f.readline()
            data = json.loads(line)
            assert data["url"] == "https://example.com/article"
            assert data["title"] == "Test Article"

    def test_load_seen_records(self, temp_data_dir: Path) -> None:
        """Should load records from seen.jsonl."""
        seen_file = temp_data_dir / "seen.jsonl"

        # Create two records
        for i in range(2):
            record = SeenRecord(
                url=f"https://example.com/article{i}",
                url_hash=f"hash{i}",
                content_hash=f"content{i}",
                title=f"Article {i}",
                fetched_at=datetime.now(),
                stored_path=f"library/2024/01/article-{i}",
                source=SourceType.MANUAL,
            )
            record_seen(record, seen_file)

        records = load_seen_records(seen_file)
        assert len(records) == 2
        assert "hash0" in records
        assert "hash1" in records

    def test_load_empty_file(self, temp_data_dir: Path) -> None:
        """Should return empty dict for non-existent file."""
        seen_file = temp_data_dir / "seen.jsonl"
        records = load_seen_records(seen_file)
        assert records == {}


class TestIsDuplicate:
    """Tests for duplicate detection."""

    def test_not_duplicate_empty_db(self, temp_data_dir: Path) -> None:
        """Should not be duplicate with empty seen file."""
        seen_file = temp_data_dir / "seen.jsonl"
        is_dup, reason = is_duplicate(
            "https://example.com/new-article",
            "New content here",
            seen_file,
        )
        assert not is_dup
        assert reason is None

    def test_duplicate_by_url(self, temp_data_dir: Path) -> None:
        """Should detect duplicate by URL hash."""
        seen_file = temp_data_dir / "seen.jsonl"

        url = "https://example.com/article"
        url_hash = compute_url_hash(url)

        record = SeenRecord(
            url=url,
            url_hash=url_hash,
            content_hash="somehash",
            title="Existing Article",
            fetched_at=datetime.now(),
            stored_path="library/2024/01/existing",
            source=SourceType.MANUAL,
        )
        record_seen(record, seen_file)

        is_dup, reason = is_duplicate(url, None, seen_file)
        assert is_dup
        assert "already seen" in reason.lower()

    def test_duplicate_by_content(self, temp_data_dir: Path) -> None:
        """Should detect duplicate by content hash."""
        seen_file = temp_data_dir / "seen.jsonl"

        content = "This is the article content"
        content_hash = compute_content_hash(content)

        record = SeenRecord(
            url="https://example.com/original",
            url_hash="originalhash",
            content_hash=content_hash,
            title="Original Article",
            fetched_at=datetime.now(),
            stored_path="library/2024/01/original",
            source=SourceType.MANUAL,
        )
        record_seen(record, seen_file)

        # Different URL, same content
        is_dup, reason = is_duplicate(
            "https://different.com/repost",
            content,
            seen_file,
        )
        assert is_dup
        assert "matches existing" in reason.lower()
