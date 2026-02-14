"""CLI entrypoint for GAD (Good Article Digest)."""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from gad.config import get_settings, load_settings, reset_settings
from gad.dedup import compute_content_hash, compute_url_hash, is_duplicate, record_seen
from gad.extract import extract_content
from gad.fetch import FetchError, detect_and_parse_source, fetch_url
from gad.models import ArticleMeta, IngestResult, SourceType
from gad.render import create_seen_record, generate_digest, write_article
from gad.summarize import get_summarizer


app = typer.Typer(
    name="gad",
    help="Good Article Digest - Ingest, summarize, and organize articles",
    no_args_is_help=True,
)

console = Console()
logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )


@app.command()
def ingest(
    url: Annotated[str, typer.Argument(help="URL of the article to ingest")],
    tag: Annotated[
        Optional[list[str]],
        typer.Option("--tag", "-t", help="Tags to apply to the article"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without writing files"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Ingest even if duplicate detected"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
) -> None:
    """Ingest a single article from a URL.

    Fetches the URL, extracts main text, checks for duplicates,
    summarizes with LLM, and writes files to the library.
    """
    setup_logging(verbose)
    settings = get_settings()
    settings.ensure_directories()

    console.print(f"[bold blue]Ingesting:[/] {url}")

    try:
        # Fetch HTML
        console.print("  Fetching...", end=" ")
        html = fetch_url(url)
        console.print("[green]✓[/]")

        # Extract content
        console.print("  Extracting content...", end=" ")
        extracted = extract_content(html, url)
        console.print(f"[green]✓[/] ({extracted.word_count:,} words)")

        if extracted.word_count < 50:
            console.print("[yellow]Warning: Very little content extracted[/]")

        # Check for duplicates
        url_hash = compute_url_hash(url)
        content_hash = compute_content_hash(extracted.text)

        is_dup, reason = is_duplicate(url, extracted.text)
        if is_dup and not force:
            console.print(f"[yellow]Skipped:[/] {reason}")
            raise typer.Exit(0)
        elif is_dup:
            console.print(f"[yellow]Duplicate detected but --force used:[/] {reason}")

        # Prepare tags
        tags = list(tag) if tag else list(settings.default_tags)

        if dry_run:
            console.print("\n[bold yellow]DRY RUN - No files written[/]")
            console.print(f"  Title: {extracted.title}")
            console.print(f"  Author: {extracted.author or 'Unknown'}")
            console.print(f"  Words: {extracted.word_count:,}")
            console.print(f"  Tags: {', '.join(tags)}")
            console.print(f"  URL Hash: {url_hash[:16]}...")
            console.print(f"  Content Hash: {content_hash[:16]}...")
            raise typer.Exit(0)

        # Generate summary
        console.print("  Summarizing...", end=" ")
        summarizer = get_summarizer()
        summary = summarizer.summarize(extracted.text, extracted.title)
        console.print("[green]✓[/]")

        # Create metadata
        fetched_at = datetime.now()
        meta = ArticleMeta(
            title=extracted.title,
            author=extracted.author,
            published_date=extracted.published_date,
            url=url,
            url_hash=url_hash,
            content_hash=content_hash,
            fetched_at=fetched_at,
            word_count=extracted.word_count,
            tags=tags,
            source=SourceType.MANUAL,
        )

        # Write files
        console.print("  Writing files...", end=" ")
        article_dir = write_article(meta, extracted.text, summary)
        console.print("[green]✓[/]")

        # Record in seen.jsonl
        seen_record = create_seen_record(
            url=url,
            url_hash=url_hash,
            content_hash=content_hash,
            title=extracted.title,
            stored_path=article_dir,
            source=SourceType.MANUAL,
            fetched_at=fetched_at,
        )
        record_seen(seen_record)

        console.print(f"\n[bold green]Success![/] Article saved to: {article_dir}")

    except FetchError as e:
        console.print(f"[red]Error fetching URL:[/] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        logger.exception("Ingest failed")
        raise typer.Exit(1)


@app.command()
def run(
    sources: Annotated[
        Path,
        typer.Option("--sources", "-s", help="Path to sources file"),
    ] = Path("configs/sources.txt"),
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-l", help="Max articles to ingest per source"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
) -> None:
    """Run ingestion from a sources file.

    Each line in the sources file can be a direct URL or RSS feed.
    Lines starting with # are treated as comments.
    """
    setup_logging(verbose)
    settings = get_settings()
    settings.ensure_directories()

    if not sources.exists():
        console.print(f"[red]Error:[/] Sources file not found: {sources}")
        raise typer.Exit(1)

    # Read sources
    with open(sources, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    console.print(f"[bold blue]Processing {len(lines)} source(s)[/]")

    results: list[IngestResult] = []

    for source_url in lines:
        console.print(f"\n[bold]Source:[/] {source_url}")

        try:
            # Detect if RSS feed and get article URLs
            article_urls = detect_and_parse_source(source_url, limit=limit)
            console.print(f"  Found {len(article_urls)} article(s)")

            for article_url in article_urls:
                result = _ingest_single(
                    article_url,
                    tags=list(settings.default_tags),
                    source=SourceType.RSS if len(article_urls) > 1 else SourceType.MANUAL,
                )
                results.append(result)

                if result.success:
                    console.print(f"  [green]✓[/] {result.title or article_url}")
                elif result.skipped:
                    console.print(f"  [yellow]⊘[/] Skipped: {result.title or article_url}")
                else:
                    console.print(f"  [red]✗[/] {result.error or 'Unknown error'}")

        except Exception as e:
            console.print(f"  [red]Error processing source:[/] {e}")
            logger.exception(f"Error processing source: {source_url}")

    # Print summary
    success_count = sum(1 for r in results if r.success)
    skipped_count = sum(1 for r in results if r.skipped)
    error_count = sum(1 for r in results if not r.success and not r.skipped)

    console.print(f"\n[bold]Summary:[/]")
    console.print(f"  Ingested: {success_count}")
    console.print(f"  Skipped: {skipped_count}")
    console.print(f"  Errors: {error_count}")


def _ingest_single(url: str, tags: list[str], source: SourceType) -> IngestResult:
    """Ingest a single URL, returning result without raising exceptions."""
    settings = get_settings()

    try:
        # Fetch
        html = fetch_url(url)

        # Extract
        extracted = extract_content(html, url)

        if extracted.word_count < 50:
            return IngestResult(
                url=url,
                success=False,
                error="Too little content extracted",
            )

        # Check duplicates
        url_hash = compute_url_hash(url)
        content_hash = compute_content_hash(extracted.text)

        is_dup, reason = is_duplicate(url, extracted.text)
        if is_dup:
            return IngestResult(
                url=url,
                success=False,
                skipped=True,
                title=extracted.title,
            )

        # Summarize
        summarizer = get_summarizer()
        summary = summarizer.summarize(extracted.text, extracted.title)

        # Create metadata
        fetched_at = datetime.now()
        meta = ArticleMeta(
            title=extracted.title,
            author=extracted.author,
            published_date=extracted.published_date,
            url=url,
            url_hash=url_hash,
            content_hash=content_hash,
            fetched_at=fetched_at,
            word_count=extracted.word_count,
            tags=tags,
            source=source,
        )

        # Write
        article_dir = write_article(meta, extracted.text, summary)

        # Record seen
        seen_record = create_seen_record(
            url=url,
            url_hash=url_hash,
            content_hash=content_hash,
            title=extracted.title,
            stored_path=article_dir,
            source=source,
            fetched_at=fetched_at,
        )
        record_seen(seen_record)

        return IngestResult(
            url=url,
            success=True,
            title=extracted.title,
            stored_path=str(article_dir),
        )

    except FetchError as e:
        return IngestResult(url=url, success=False, error=str(e))
    except Exception as e:
        logger.exception(f"Error ingesting {url}")
        return IngestResult(url=url, success=False, error=str(e))


@app.command()
def digest(
    date: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Date for digest (YYYY-MM-DD), defaults to today"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
) -> None:
    """Generate a daily digest of ingested articles.

    Creates a Markdown file listing all articles ingested on the specified date.
    """
    setup_logging(verbose)
    settings = get_settings()
    settings.ensure_directories()

    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            console.print("[red]Error:[/] Invalid date format. Use YYYY-MM-DD")
            raise typer.Exit(1)
    else:
        target_date = datetime.now()

    console.print(f"[bold blue]Generating digest for:[/] {target_date.strftime('%Y-%m-%d')}")

    try:
        digest_path = generate_digest(target_date)
        console.print(f"[bold green]Digest created:[/] {digest_path}")
    except Exception as e:
        console.print(f"[red]Error generating digest:[/] {e}")
        logger.exception("Digest generation failed")
        raise typer.Exit(1)


@app.command()
def doctor(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
) -> None:
    """Check dependencies, configuration, and data directories.

    Verifies that GAD is properly configured and ready to use.
    """
    setup_logging(verbose)
    reset_settings()  # Force reload

    console.print("[bold blue]GAD Doctor[/]\n")

    table = Table(title="Configuration Check")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details")

    all_ok = True

    # Check Python version
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11):
        table.add_row("Python Version", "✓", py_version)
    else:
        table.add_row("Python Version", "[red]✗[/]", f"{py_version} (need 3.11+)")
        all_ok = False

    # Check config file
    from gad.config import find_config_file

    config_path = find_config_file()
    if config_path:
        table.add_row("Config File", "✓", str(config_path))
    else:
        table.add_row("Config File", "[yellow]⊘[/]", "Using defaults (copy settings.example.yaml)")

    # Load settings
    try:
        settings = load_settings()
        table.add_row("Settings Load", "✓", "Valid configuration")
    except Exception as e:
        table.add_row("Settings Load", "[red]✗[/]", str(e))
        all_ok = False
        settings = None

    if settings:
        # Check directories
        try:
            settings.ensure_directories()
            table.add_row("Data Directory", "✓", str(settings.output_dir))
        except Exception as e:
            table.add_row("Data Directory", "[red]✗[/]", f"Cannot create: {e}")
            all_ok = False

        # Check writability
        try:
            test_file = settings.output_dir / ".doctor_test"
            test_file.write_text("test")
            test_file.unlink()
            table.add_row("Directory Writable", "✓", "Can write to data directory")
        except Exception as e:
            table.add_row("Directory Writable", "[red]✗[/]", str(e))
            all_ok = False

        # Check OpenAI API key
        if settings.openai_api_key:
            table.add_row("OpenAI API Key", "✓", "Configured")
        else:
            table.add_row(
                "OpenAI API Key",
                "[yellow]⊘[/]",
                "Not set (will use mock summarizer)",
            )

    # Check dependencies
    deps = [
        ("trafilatura", "Content extraction"),
        ("feedparser", "RSS parsing"),
        ("httpx", "HTTP client"),
        ("bs4", "HTML parsing"),
        ("pydantic", "Data validation"),
        ("typer", "CLI framework"),
        ("openai", "LLM summarization"),
    ]

    for module, desc in deps:
        try:
            __import__(module)
            table.add_row(f"Dependency: {module}", "✓", desc)
        except ImportError:
            table.add_row(f"Dependency: {module}", "[red]✗[/]", f"Missing ({desc})")
            all_ok = False

    console.print(table)

    if all_ok:
        console.print("\n[bold green]All checks passed![/] GAD is ready to use.")
    else:
        console.print("\n[bold red]Some checks failed.[/] Please resolve issues above.")
        raise typer.Exit(1)


@app.command("digest-json")
def digest_json(
    input_file: Annotated[
        Optional[Path],
        typer.Option("--input", "-i", help="Path to items JSON file"),
    ] = None,
    date: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Load articles from library for this date (YYYY-MM-DD)"),
    ] = None,
    top_k: Annotated[
        int,
        typer.Option("--top-k", "-k", help="Number of items to send to LLM after pre-ranking"),
    ] = 30,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Skip LLM output cache"),
    ] = False,
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output directory (default: data/web/)"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
) -> None:
    """Generate a UI-ready digest JSON from ingested articles.

    Two-step pipeline:
    1. Pre-rank items locally (source weight, freshness, content length).
    2. Send Top-K to LLM for scoring, grouping, and copywriting.
    """
    import json as _json

    from gad.digest import generate_digest_json, pre_rank
    from gad.models import DigestItemInput

    setup_logging(verbose)
    settings = get_settings()
    settings.ensure_directories()

    # --- Collect items ---
    items: list[DigestItemInput] = []

    if input_file:
        if not input_file.exists():
            console.print(f"[red]Error:[/] Input file not found: {input_file}")
            raise typer.Exit(1)
        raw = _json.loads(input_file.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            items = [DigestItemInput.model_validate(r) for r in raw]
        else:
            console.print("[red]Error:[/] Input file must contain a JSON array")
            raise typer.Exit(1)
        console.print(f"[bold blue]Loaded {len(items)} items from {input_file}[/]")

    elif date:
        # Load articles from library for the given date
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            console.print("[red]Error:[/] Invalid date format. Use YYYY-MM-DD")
            raise typer.Exit(1)

        from gad.render import load_articles_for_date

        articles = load_articles_for_date(target_date)
        for meta, article_dir in articles:
            content_path = article_dir / "content.txt"
            content = content_path.read_text(encoding="utf-8") if content_path.exists() else None
            items.append(
                DigestItemInput(
                    title=meta.title,
                    url=meta.url,
                    source=meta.source.value,
                    date=meta.published_date or meta.fetched_at.strftime("%Y-%m-%d"),
                    content=content,
                    author=meta.author,
                    tags=meta.tags,
                )
            )
        console.print(f"[bold blue]Loaded {len(items)} articles from library for {date}[/]")

    else:
        console.print("[red]Error:[/] Provide --input <file> or --date <YYYY-MM-DD>")
        raise typer.Exit(1)

    if not items:
        console.print("[yellow]No items found. Nothing to do.[/]")
        raise typer.Exit(0)

    # --- Step 1: Pre-rank ---
    console.print(f"  Pre-ranking {len(items)} items → top {top_k}...", end=" ")
    ranked = pre_rank(items, top_k=top_k)
    console.print(f"[green]✓[/] ({len(ranked)} candidates)")

    # --- Step 2: Generate digest ---
    console.print("  Generating digest JSON...", end=" ")
    digest_output = generate_digest_json(
        ranked,
        all_count=len(items),
        use_cache=not no_cache,
    )
    console.print("[green]✓[/]")

    # --- Write output ---
    out_dir = output or (settings.output_dir / "web")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "digest.json"
    out_path.write_text(
        digest_output.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    console.print(f"\n[bold green]Digest written to:[/] {out_path}")
    console.print(
        f"  Stats: {digest_output.stats.items_in} in → "
        f"{digest_output.stats.items_kept} kept, "
        f"{digest_output.stats.top_stories_count} top stories, "
        f"{digest_output.stats.duplicates_count} duplicates"
    )


if __name__ == "__main__":
    app()

