"""GAD (Good Article Digest) - Article ingestion and summarization tool."""

__version__ = "0.1.0"

from gad.config import get_settings, load_settings
from gad.models import ArticleMeta, ExtractedContent, SeenRecord, SourceType

__all__ = [
    "__version__",
    "get_settings",
    "load_settings",
    "ArticleMeta",
    "ExtractedContent",
    "SeenRecord",
    "SourceType",
]
