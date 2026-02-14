# GAD - Good Article Digest

A lightweight, database-free article ingestion and summarization tool. Ingest high-quality articles from URLs and RSS feeds, extract clean text, deduplicate, summarize with an LLM, and store everything as local Markdown/JSON files.

## Features

- 📥 **Ingest articles** from URLs or RSS/Atom feeds
- 📝 **Extract clean text** using trafilatura with BeautifulSoup fallback
- 🔄 **Deduplicate** by URL hash and content hash
- 🤖 **Summarize** with OpenAI GPT models (or offline mock summarizer)
- 📁 **File-based storage** - no database required
- 📊 **Daily digests** - generate Markdown summaries of ingested articles
- 🖥️ **Cross-platform** - works on Windows and Linux

## Quickstart

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/reading-summarizer.git
cd reading-summarizer

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

### Configuration

```bash
# Copy the example config
cp configs/settings.example.yaml configs/settings.yaml

# Edit to customize (optional)
# Set your OpenAI API key for AI summaries
export OPENAI_API_KEY="sk-..."
```

### Basic Usage

```bash
# Check your setup
gad doctor

# Ingest a single article
gad ingest "https://example.com/interesting-article"

# Ingest with custom tags
gad ingest "https://example.com/article" --tag tech --tag ai

# Dry run to see what would happen
gad ingest "https://example.com/article" --dry-run

# Force re-ingest a duplicate
gad ingest "https://example.com/article" --force

# Run batch ingestion from sources file
gad run --sources configs/sources.txt --limit 5

# Generate a daily digest
gad digest

# Generate digest for a specific date
gad digest --date 2024-01-15
```

## CLI Commands

### `gad ingest <url>`

Fetch, extract, and summarize a single article.

| Option | Description |
|--------|-------------|
| `--tag, -t` | Add tags to the article (repeatable) |
| `--dry-run, -n` | Show what would be done without writing |
| `--force, -f` | Ingest even if duplicate detected |
| `--verbose, -v` | Enable debug output |

### `gad run --sources <file>`

Batch ingest from a sources file containing URLs and RSS feeds.

| Option | Description |
|--------|-------------|
| `--sources, -s` | Path to sources file (default: configs/sources.txt) |
| `--limit, -l` | Max articles per source |
| `--verbose, -v` | Enable debug output |

### `gad digest`

Generate a daily digest Markdown file.

| Option | Description |
|--------|-------------|
| `--date, -d` | Date in YYYY-MM-DD format (default: today) |
| `--verbose, -v` | Enable debug output |

### `gad doctor`

Check dependencies, configuration, and directory permissions.

## Configuration

Copy `configs/settings.example.yaml` to `configs/settings.yaml`:

```yaml
# Output directory for all data
output_dir: ./data

# OpenAI model (requires OPENAI_API_KEY env var)
model: gpt-4o-mini

# Max characters to send to LLM
max_input_chars: 15000

# Default tags for all articles
default_tags:
  - reading-list

# HTTP settings
http:
  timeout: 30
  user_agent: "GAD/0.1"

# Logging level
log_level: INFO
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for AI summarization |
| `GAD_OUTPUT_DIR` | Override output directory |
| `GAD_LOG_LEVEL` | Override log level |

## Output Structure

All data is stored under the configured `output_dir` (default: `./data`):

```
data/
├── seen.jsonl              # Deduplication log (append-only)
├── library/                # Article storage
│   └── 2024/
│       └── 01/
│           └── article-slug-143052/
│               ├── meta.json      # Article metadata
│               ├── content.txt    # Clean extracted text
│               └── summary.md     # LLM-generated summary
└── daily_digest/
    └── 2024-01-15.md       # Daily summary
```

### meta.json

```json
{
  "title": "Article Title",
  "author": "John Doe",
  "published_date": "2024-01-15",
  "url": "https://example.com/article",
  "url_hash": "a1b2c3...",
  "content_hash": "d4e5f6...",
  "fetched_at": "2024-01-15T14:30:52",
  "word_count": 1500,
  "tags": ["tech", "ai"],
  "source": "manual"
}
```

### seen.jsonl

Each line is a JSON record:

```json
{"url": "...", "url_hash": "...", "content_hash": "...", "title": "...", "fetched_at": "...", "stored_path": "...", "source": "manual|rss"}
```

## Deduplication

GAD uses two-level deduplication:

1. **URL Hash**: SHA256 of normalized URL
   - Removes tracking parameters (utm_*, fbclid, etc.)
   - Normalizes case and trailing slashes
   - Catches exact URL duplicates

2. **Content Hash**: SHA256 of normalized text
   - Catches reposts with different URLs
   - Ignores whitespace and case differences

Skip duplicates by default. Use `--force` to re-ingest.

## Summarization

### With OpenAI API

Set `OPENAI_API_KEY` environment variable. Summaries include:

- **TL;DR**: 2-3 sentence executive summary
- **Problem/Motivation**: What the article addresses
- **Core Ideas/Methods**: Main concepts
- **Key Evidence/Examples**: Supporting data
- **Limitations/Open Questions**: Acknowledged gaps
- **Practical Implications**: Takeaways
- **Key Quotes**: Notable direct quotes

### Without API Key

Falls back to a mock summarizer that extracts:
- First few sentences as TL;DR
- Word count statistics
- Sample quote

## Limitations

- **Paywalled sites**: Cannot access content behind login walls
- **JavaScript-heavy pages**: May not extract dynamically-loaded content
- **Rate limits**: No built-in rate limiting; be respectful with batch ingestion
- **Large files**: Content truncated to `max_input_chars` before summarization

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
uv run pytest -v

# Run type checking
uv run mypy src/

# Run linting
uv run ruff check src/
```

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.
