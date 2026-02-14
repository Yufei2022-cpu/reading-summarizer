"""Configuration management for GAD."""

import logging
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger(__name__)


class HttpConfig(BaseModel):
    """HTTP request configuration."""

    timeout: int = Field(default=30, description="Request timeout in seconds")
    user_agent: str = Field(
        default="GAD/0.1 (Good Article Digest)",
        description="User agent string for requests",
    )


class Settings(BaseSettings):
    """Application settings loaded from YAML and environment."""

    model_config = SettingsConfigDict(
        env_prefix="GAD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core settings
    output_dir: Path = Field(default=Path("./data"), description="Output directory for all data")
    model: str = Field(default="gpt-4o-mini", description="OpenAI model for summarization")
    max_input_chars: int = Field(
        default=15000, description="Max chars to send to LLM"
    )
    default_tags: list[str] = Field(
        default_factory=lambda: ["reading-list"], description="Default tags for articles"
    )
    log_level: str = Field(default="INFO", description="Logging level")

    # HTTP settings
    http: HttpConfig = Field(default_factory=HttpConfig)

    # API keys from environment
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")

    @property
    def data_dir(self) -> Path:
        """Get the data directory path."""
        return self.output_dir

    @property
    def library_dir(self) -> Path:
        """Get the library directory path."""
        return self.output_dir / "library"

    @property
    def digest_dir(self) -> Path:
        """Get the daily digest directory path."""
        return self.output_dir / "daily_digest"

    @property
    def seen_file(self) -> Path:
        """Get the seen.jsonl file path."""
        return self.output_dir / "seen.jsonl"

    def ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.digest_dir.mkdir(parents=True, exist_ok=True)


def find_config_file() -> Optional[Path]:
    """Find the configuration file in standard locations."""
    search_paths = [
        Path("configs/settings.yaml"),
        Path("configs/settings.yml"),
        Path("settings.yaml"),
        Path("settings.yml"),
        Path.home() / ".config" / "gad" / "settings.yaml",
    ]

    for path in search_paths:
        if path.exists():
            return path

    return None


def load_yaml_config(config_path: Optional[Path] = None) -> dict[str, Any]:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = find_config_file()

    if config_path is None or not config_path.exists():
        logger.debug("No config file found, using defaults")
        return {}

    logger.info(f"Loading config from {config_path}")
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config or {}


def load_settings(config_path: Optional[Path] = None) -> Settings:
    """Load settings from YAML file and environment variables.

    Priority (highest to lowest):
    1. Environment variables (GAD_* prefix)
    2. YAML config file
    3. Default values
    """
    yaml_config = load_yaml_config(config_path)

    # Handle nested http config
    if "http" in yaml_config and isinstance(yaml_config["http"], dict):
        yaml_config["http"] = HttpConfig(**yaml_config["http"])

    # Environment variables for secrets
    if os.environ.get("OPENAI_API_KEY"):
        yaml_config["openai_api_key"] = os.environ["OPENAI_API_KEY"]

    settings = Settings(**yaml_config)

    # Configure logging based on settings
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    return settings


# Global settings instance (lazy loaded)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reset_settings() -> None:
    """Reset the global settings instance (for testing)."""
    global _settings
    _settings = None
