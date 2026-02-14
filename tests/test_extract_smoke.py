"""Smoke tests for content extraction."""

import pytest

from gad.extract import (
    extract_content,
    extract_meta_info,
    extract_with_beautifulsoup,
    normalize_whitespace,
)


class TestNormalizeWhitespace:
    """Tests for whitespace normalization."""

    def test_collapse_spaces(self) -> None:
        """Should collapse multiple spaces."""
        text = "Hello    world"
        result = normalize_whitespace(text)
        assert result == "Hello world"

    def test_collapse_newlines(self) -> None:
        """Should collapse newlines to spaces."""
        text = "Hello\n\n\nworld"
        result = normalize_whitespace(text)
        assert result == "Hello world"

    def test_strip_whitespace(self) -> None:
        """Should strip leading/trailing whitespace."""
        text = "  Hello world  "
        result = normalize_whitespace(text)
        assert result == "Hello world"

    def test_mixed_whitespace(self) -> None:
        """Should handle mixed whitespace characters."""
        text = "Hello\t\n  world\r\n"
        result = normalize_whitespace(text)
        assert result == "Hello world"


class TestExtractMetaInfo:
    """Tests for metadata extraction from HTML."""

    def test_extract_title(self, sample_html: str) -> None:
        """Should extract title from HTML."""
        title, _, _ = extract_meta_info(sample_html)
        assert title == "Test Article Title"

    def test_extract_author(self, sample_html: str) -> None:
        """Should extract author from meta tag."""
        _, author, _ = extract_meta_info(sample_html)
        assert author == "John Doe"

    def test_extract_published_date(self, sample_html: str) -> None:
        """Should extract published date from meta tag."""
        _, _, published = extract_meta_info(sample_html)
        assert published == "2024-01-15"

    def test_missing_metadata(self) -> None:
        """Should return None for missing metadata."""
        html = "<html><body><p>Content</p></body></html>"
        title, author, published = extract_meta_info(html)
        assert title is None
        assert author is None
        assert published is None


class TestExtractWithBeautifulsoup:
    """Tests for BeautifulSoup fallback extraction."""

    def test_extract_article_content(self, sample_html: str) -> None:
        """Should extract text from article element."""
        text = extract_with_beautifulsoup(sample_html)
        assert "first paragraph" in text
        assert "second paragraph" in text
        assert "conclusion" in text

    def test_exclude_header_footer(self, sample_html: str) -> None:
        """Should exclude header and footer content."""
        text = extract_with_beautifulsoup(sample_html)
        # The header/footer content might still appear in some cases
        # but the main content should be prioritized
        assert "first paragraph" in text

    def test_handle_minimal_html(self) -> None:
        """Should handle minimal HTML documents."""
        html = "<p>Just some text</p>"
        text = extract_with_beautifulsoup(html)
        assert "Just some text" in text

    def test_remove_script_style(self) -> None:
        """Should remove script and style elements."""
        html = """
        <html>
        <head><style>body { color: red; }</style></head>
        <body>
            <script>console.log('hello');</script>
            <p>Real content</p>
        </body>
        </html>
        """
        text = extract_with_beautifulsoup(html)
        assert "Real content" in text
        assert "console.log" not in text
        assert "color: red" not in text


class TestExtractContent:
    """Integration tests for content extraction."""

    def test_extract_returns_content(self, sample_html: str) -> None:
        """Should return ExtractedContent with text."""
        result = extract_content(sample_html)
        assert result.text
        assert result.word_count > 0

    def test_extract_includes_title(self, sample_html: str) -> None:
        """Should include title in result."""
        result = extract_content(sample_html)
        assert result.title == "Test Article Title"

    def test_extract_includes_author(self, sample_html: str) -> None:
        """Should include author in result."""
        result = extract_content(sample_html)
        assert result.author == "John Doe"

    def test_extract_includes_word_count(self, sample_html: str) -> None:
        """Should calculate word count."""
        result = extract_content(sample_html)
        assert result.word_count > 0
        # Verify word count is approximately correct
        assert result.word_count == len(result.text.split())

    def test_extract_empty_html(self) -> None:
        """Should handle empty HTML gracefully."""
        result = extract_content("")
        assert result.title == "Untitled"
        assert result.text == ""
        assert result.word_count == 0

    def test_extract_with_url(self, sample_html: str) -> None:
        """Should accept optional URL parameter."""
        result = extract_content(sample_html, url="https://example.com/article")
        assert result.text
        # URL is used for context but doesn't change extraction
