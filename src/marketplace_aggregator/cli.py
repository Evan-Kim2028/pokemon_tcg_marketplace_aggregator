from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from rich import print as rprint
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from marketplace_aggregator._client import make_client
from marketplace_aggregator.models import OTCListing
from marketplace_aggregator.sources import ALL_SOURCES, DEFAULT_SOURCES, REGISTRY


def run(
    sources: list[str],
    output: Path,
    max_pages: int | None = None,
) -> list[OTCListing]:
    output.parent.mkdir(parents=True, exist_ok=True)
    client = make_client()
    all_listings: list[OTCListing] = []
    stats: dict[str, dict] = {}

    for source in sources:
        fn = REGISTRY.get(source)
        if not fn:
            rprint(f"[yellow]Unknown source '{source}', skipping. Available: {', '.join(ALL_SOURCES)}[/yellow]")
            continue

        rprint(f"\n[bold cyan]Fetching {source}...[/bold cyan]")
        source_listings: list[OTCListing] = []
        errors = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed} listings"),
            transient=True,
        ) as progress:
            task = progress.add_task(f"  {source}", total=None)
            try:
                gen = fn(client, max_pages=max_pages) if max_pages is not None else fn(client)
                for listing in gen:
                    source_listings.append(listing)
                    progress.update(task, completed=len(source_listings))
            except Exception as e:
                rprint(f"[red]  Error from {source}: {e}[/red]")
                errors += 1

        stats[source] = {
            "count": len(source_listings),
            "errors": errors,
            "with_ask_price": sum(1 for listing in source_listings if listing.ask_usd is not None),
            "with_grade": sum(1 for listing in source_listings if listing.grade is not None),
            "with_cert": sum(1 for listing in source_listings if listing.cert_number is not None),
        }
        all_listings.extend(source_listings)
        rprint(f"  [green]{len(source_listings)} listings[/green]")

    with output.open("w") as f:
        for listing in all_listings:
            f.write(json.dumps(listing.to_dict()) + "\n")

    table = Table(title="Marketplace Aggregator Snapshot", show_header=True)
    table.add_column("Source")
    table.add_column("Listings", justify="right")
    table.add_column("With Price", justify="right")
    table.add_column("With Grade", justify="right")
    table.add_column("With Cert", justify="right")
    for source, s in stats.items():
        n = max(s["count"], 1)
        table.add_row(
            source,
            str(s["count"]),
            f"{s['with_ask_price']} ({100 * s['with_ask_price'] // n}%)",
            f"{s['with_grade']} ({100 * s['with_grade'] // n}%)",
            f"{s['with_cert']} ({100 * s['with_cert'] // n}%)",
        )
    rprint(table)
    rprint(Panel(f"[bold green]Wrote {len(all_listings)} listings → {output}[/bold green]"))
    return all_listings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Marketplace Aggregator — active OTC listing aggregator for graded and raw trading cards",
    )
    parser.add_argument(
        "--sources",
        default=",".join(DEFAULT_SOURCES),
        help=f"Comma-separated sources. Available: {', '.join(ALL_SOURCES)}. Default excludes 'alt' (see ToS note).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Cap each paginated source at N pages (useful for testing). Omit for full run.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output NDJSON path. Default: ./data/{date}/snapshot_{time}.ndjson",
    )
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    if args.output:
        output = args.output
    else:
        now = datetime.now(timezone.utc)
        output = Path("data") / now.strftime("%Y-%m-%d") / f"snapshot_{now.strftime('%H-%M-%S')}.ndjson"

    run(sources, output, max_pages=args.max_pages)


if __name__ == "__main__":
    main()
