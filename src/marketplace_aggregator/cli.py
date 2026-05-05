from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
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


def merge(data_dir: Path, days: int, output: Path | None) -> None:
    """Merge all snapshots from the past N days into one deduped NDJSON."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    snapshots = sorted(data_dir.glob("**/*.ndjson"))
    # Exclude any previously merged files so we don't double-count
    snapshots = [p for p in snapshots if not p.name.startswith("merged_")]

    if not snapshots:
        rprint(f"[yellow]No snapshot files found in {data_dir}[/yellow]")
        return

    rprint(f"\n[bold cyan]Scanning {len(snapshots)} snapshot file(s) in {data_dir}…[/bold cyan]")

    total_raw = 0
    files_used = 0
    # key → best (most-recent fetched_at) record
    best: dict[tuple[str, str], dict] = {}

    for snap in snapshots:
        file_count = 0
        try:
            for line in snap.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                fa = d.get("fetched_at", "")
                if fa:
                    try:
                        dt = datetime.fromisoformat(fa.replace("Z", "+00:00"))
                        if dt < cutoff:
                            continue
                    except ValueError:
                        pass

                total_raw += 1
                file_count += 1
                src = d.get("source", "")
                cert = d.get("cert_number") or ""
                lid = d.get("listing_id", "")
                # Prefer cert as stable identity; fall back to listing_id
                key: tuple[str, str] = (src, cert) if cert else (src, lid)

                existing = best.get(key)
                if existing is None or (fa and fa > existing.get("fetched_at", "")):
                    best[key] = d
        except Exception as e:
            rprint(f"[yellow]  Skipping {snap.name}: {e}[/yellow]")
            continue
        if file_count:
            files_used += 1

    merged = list(best.values())
    deduped = total_raw - len(merged)

    if output is None:
        now = datetime.now(timezone.utc)
        output = data_dir / f"merged_{now.strftime('%Y-%m-%d')}_last{days}d.ndjson"

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as f:
        for d in merged:
            f.write(json.dumps(d) + "\n")

    table = Table(title=f"Merged Window: last {days} day(s)", show_header=True)
    table.add_column("Source")
    table.add_column("Unique listings", justify="right")
    table.add_column("With cert", justify="right")
    table.add_column("With grade", justify="right")
    for source, count in sorted(Counter(d["source"] for d in merged).items()):
        src_rows = [d for d in merged if d["source"] == source]
        with_cert  = sum(1 for d in src_rows if d.get("cert_number"))
        with_grade = sum(1 for d in src_rows if d.get("grade"))
        table.add_row(source, str(count),
                      f"{with_cert} ({100*with_cert//max(count,1)}%)",
                      f"{with_grade} ({100*with_grade//max(count,1)}%)")
    rprint(table)
    rprint(Panel(
        f"[bold green]{files_used} snapshot file(s) · {total_raw} raw rows · "
        f"{deduped} deduplicated · {len(merged)} unique listings → {output}[/bold green]"
    ))


def main() -> None:
    # Dispatch "merge" subcommand before the main fetch parser so that
    # the existing fetch interface (bare flags, no subcommand) stays unchanged.
    if len(sys.argv) > 1 and sys.argv[1] == "merge":
        _merge_main(sys.argv[2:])
        return
    _fetch_main(sys.argv[1:])


def _fetch_main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="pokemon_tcg_marketplace_aggregator",
        description="Fetch active OTC listings from all configured sources.",
    )
    parser.add_argument(
        "--sources",
        default=",".join(DEFAULT_SOURCES),
        help=f"Comma-separated sources. Available: {', '.join(ALL_SOURCES)}.",
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
    args = parser.parse_args(argv)

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    if args.output:
        output = args.output
    else:
        now = datetime.now(timezone.utc)
        output = Path("data") / now.strftime("%Y-%m-%d") / f"snapshot_{now.strftime('%H-%M-%S')}.ndjson"

    run(sources, output, max_pages=args.max_pages)


def _merge_main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="pokemon_tcg_marketplace_aggregator merge",
        description=(
            "Merge all snapshots from the past N days into one deduped NDJSON. "
            "Dedup key is (source, cert_number) where available, else (source, listing_id). "
            "For each card the most-recent fetched_at observation wins."
        ),
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Rolling window in days (default: 7).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Directory containing dated snapshot subdirectories (default: ./data).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path. Default: {data-dir}/merged_{date}_last{days}d.ndjson",
    )
    args = parser.parse_args(argv)
    merge(args.data_dir, args.days, args.output)


if __name__ == "__main__":
    main()
