"""Pytest fixtures for GAD tests."""

import tempfile
from pathlib import Path
from typing import Generator

import pytest

from gad.config import Settings, reset_settings


@pytest.fixture
def temp_data_dir() -> Generator[Path, None, None]:
    """Create a temporary data directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_settings(temp_data_dir: Path) -> Generator[Settings, None, None]:
    """Create test settings with temporary data directory."""
    settings = Settings(
        output_dir=temp_data_dir,
        model="gpt-4o-mini",
        max_input_chars=15000,
        default_tags=["test"],
        log_level="DEBUG",
    )
    yield settings
    reset_settings()


@pytest.fixture
def sample_html() -> str:
    """Sample HTML content for extraction tests."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Article Title</title>
        <meta name="author" content="John Doe">
        <meta property="article:published_time" content="2024-01-15">
    </head>
    <body>
        <header>Site Navigation</header>
        <article>
            <h1>Test Article Title</h1>
            <p>This is the first paragraph of the article content.
            It contains some interesting information about various topics.</p>
            <p>This is the second paragraph with more detailed information.
            The article continues with additional context and examples.</p>
            <p>Finally, this is the conclusion of the article with key takeaways
            and recommendations for the reader.</p>
        </article>
        <footer>Copyright 2024</footer>
    </body>
    </html>
    """


@pytest.fixture
def sample_text() -> str:
    """Sample extracted text content."""
    return """
    This is the first paragraph of the article content.
    It contains some interesting information about various topics.
    This is the second paragraph with more detailed information.
    The article continues with additional context and examples.
    Finally, this is the conclusion of the article with key takeaways
    and recommendations for the reader.
    """
