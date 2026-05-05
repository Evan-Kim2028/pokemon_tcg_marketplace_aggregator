# pokemon_tcg_marketplace_aggregator

Live OTC listings aggregator for graded Pokemon TCG cards across web3 and crypto-native marketplaces.

**How it works:** Every 4 hours a cron job fetches all active buy-now listings from 7+ sources and writes a timestamped NDJSON snapshot to `./data/`. Run `merge` to collapse any window of snapshots into one deduped dataset. The longer it runs, the richer the picture.

All sources are **live-only** — these platforms expose current inventory, not transaction history. There is no historical API to backfill from. The snapshot cadence *is* the history.

---

## Prerequisites

- **Python 3.10+** — check with `python3 --version`
- **uv** — fast Python package manager (manages virtualenv and deps automatically)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.sh | iex"
```

---

## Quick start

```bash
git clone https://github.com/Evan-Kim2028/pokemon_tcg_marketplace_aggregator
cd pokemon_tcg_marketplace_aggregator
uv sync
```

Run your first snapshot:

```bash
uv run pokemon_tcg_marketplace_aggregator
```

This fetches all 7 no-key-required sources and writes to `./data/{date}/snapshot_{time}.ndjson`. You'll see a summary table with listing counts, % with price, grade, and cert.

Spot-check the output:

```bash
# count by grader across all sources
jq -r '.grader // "raw"' data/**/*.ndjson | sort | uniq -c | sort -rn

# top asks, highest price first
jq -r '[.card_name, .grader, .grade, .ask_usd] | @tsv' data/**/*.ndjson \
  | sort -t$'\t' -k4 -rn | head -20
```

---

## Setting up the 4-hour schedule

This is the step that makes the tool useful. Without a schedule you have a single point-in-time snapshot. With a schedule you get price history, new listings over time, and enough volume for meaningful analysis.

### Option A — background daemon (simplest)

A daemon script is included. It runs a snapshot, sleeps 4 hours, repeats indefinitely:

```bash
# Start collecting (writes PID to data/daemon.pid, logs to data/cron.log)
nohup uv run python scripts/collect_daemon.py >> data/cron.log 2>&1 &
echo $! > data/daemon.pid

# Watch it run
tail -f data/cron.log

# Stop it
kill $(cat data/daemon.pid)
```

### Option B — cron (survives reboots)

```bash
# 1. Find your uv path
which uv

# 2. Open your crontab
crontab -e

# 3. Paste this line (replace paths with your actual values)
0 */4 * * * cd /path/to/pokemon_tcg_marketplace_aggregator && /path/to/uv run pokemon_tcg_marketplace_aggregator >> data/cron.log 2>&1
```

Common path examples:

```
# macOS (Homebrew uv)
0 */4 * * * cd ~/pokemon_tcg_marketplace_aggregator && /opt/homebrew/bin/uv run pokemon_tcg_marketplace_aggregator >> data/cron.log 2>&1

# Linux
0 */4 * * * cd ~/pokemon_tcg_marketplace_aggregator && ~/.local/bin/uv run pokemon_tcg_marketplace_aggregator >> data/cron.log 2>&1
```

After a few days `data/` looks like:

```
data/
  2026-05-05/
    snapshot_19-28-22.ndjson     ← first run
    snapshot_23-28-10.ndjson
  2026-05-06/
    snapshot_03-28-08.ndjson
    snapshot_07-28-14.ndjson
    ...
  cron.log
```

---

## Building a rolling dataset with `merge`

Once you have multiple snapshots, collapse them into one deduped file:

```bash
uv run pokemon_tcg_marketplace_aggregator merge --days 7
# → data/merged_YYYY-MM-DD_last7d.ndjson
```

```
--days N          Rolling window in days (default: 7)
--data-dir PATH   Where snapshots live (default: ./data)
--output PATH     Output path (default: data/merged_{date}_last{N}d.ndjson)
```

**How dedup works:** The stable identity for a graded card is its cert number (globally unique per physical slab). Dedup key is `(source, cert_number)` where cert exists, else `(source, listing_id)`. When the same card appears in multiple snapshots the most recent `fetched_at` wins, so prices stay current and sold cards naturally drop out as they stop appearing.

A card that's listed for a week at one price will appear in 42 snapshots but only once in the merge output — at its latest observed price.

---

## Working with the data

Output is NDJSON — one JSON object per line. Works directly with jq, pandas, DuckDB.

**jq:**

```bash
# all PSA 10s across every source
jq 'select(.grader == "PSA" and .grade == "10")' data/merged_*.ndjson

# graded Pokemon only, sorted by ask price descending
jq 'select(.franchise == "pokemon" and .grade != null)' data/merged_*.ndjson \
  | jq -r '[.grader, .grade, .ask_usd, .card_name] | @tsv' \
  | sort -t$'\t' -k3 -rn | head -30
```

**pandas:**

```python
import pandas as pd

df = pd.read_json("data/merged_2026-05-05_last7d.ndjson", lines=True)
print(df.groupby(["source", "grader"])["ask_usd"].describe())
print(df[df.grade == "10"].sort_values("ask_usd", ascending=False).head(20))
```

**DuckDB (no import step, queries ndjson directly):**

```sql
SELECT source, grader, COUNT(*) AS listings, ROUND(AVG(ask_usd), 2) AS avg_ask
FROM read_ndjson_auto('data/merged_*.ndjson')
WHERE franchise = 'pokemon'
GROUP BY 1, 2
ORDER BY 3 DESC;
```

---

## Sources

All 7 default sources require no API key. `courtyard` is opt-in (requires an OpenSea key).

| Key | Platform | Chain | API |
|-----|----------|-------|-----|
| `renaiss` | [Renaiss](https://renaiss.xyz) | BNB Chain | tRPC, public |
| `beezie` | [Beezie](https://beezie.com) | Ethereum | REST, public |
| `ready` | Ready | — | REST, public |
| `mnstr` | MNSTR | — | REST, public |
| `playkami` | [PlayKami](https://playkami.com) | — | REST, public |
| `collector_crypt` | [Collector Crypt](https://collectorcrypt.io) | Solana | Magic Eden v2 |
| `phygitals` | [Phygitals](https://phygitals.io) | Solana | Magic Eden v2 |
| `courtyard` | [Courtyard](https://courtyard.io) | Polygon | OpenSea v2 |

**Why live-only?** None of these platforms expose historical listing data via their APIs. They return current inventory state. This is a fundamental constraint of the data layer, not a design choice — the only path to historical data is snapshot accumulation over time.

---

## Enabling Courtyard (OpenSea key)

```bash
cp .env.example .env
# edit .env: OPENSEA_API_KEY=your_key_here

uv sync --extra dotenv   # installs python-dotenv
uv run pokemon_tcg_marketplace_aggregator   # now includes courtyard
```

---

## Rate limits and `--max-pages`

`--max-pages N` caps each paginated source at N pages — useful for quick checks.

| Source | Page size | Notes |
|---|---|---|
| `collector_crypt`, `phygitals` | 100 | Magic Eden public API, ~200 ms between pages |
| `renaiss`, `beezie` | 50 | ~150 ms between pages |
| `ready` | 1000 | Large pages, very few requests for full inventory |
| `courtyard` | 100 + 1 per new NFT | First run is slow (trait fetches); warms after that |
| `mnstr`, `playkami` | Single request | `--max-pages` has no effect |

All sources retry HTTP 429 up to 3× with exponential back-off (5 s → 10 s → 20 s).

| Goal | Command |
|---|---|
| Quick check | `--max-pages 1` |
| Broad sweep | `--max-pages 5` |
| Full inventory | omit `--max-pages` |

---

## Output schema

```json
{
  "source": "mnstr",
  "listing_id": "abc123",
  "card_name": "Charizard 1st Edition",
  "set_name": "Base Set",
  "card_number": "4",
  "grade": "10",
  "grader": "PSA",
  "cert_number": "12345678",
  "ask_usd": 9500.0,
  "bid_usd": null,
  "insured_usd": null,
  "listing_url": "https://...",
  "image_url": "https://...",
  "franchise": "pokemon",
  "listed_at": "2024-01-15T12:00:00+00:00",
  "fetched_at": "2024-01-15T16:00:00+00:00"
}
```

`listed_at` is null for most sources — the platform APIs don't expose listing timestamps. `fetched_at` is always set and marks when this observation was recorded.

---

## Security & access posture

Every source calls the same public endpoints the platform's own frontend uses. No auth tokens are spoofed, no Cloudflare bypass is attempted. The HTTP client sends an honest `User-Agent`, uses HTTP/2, and sleeps 150–250 ms between paginated pages.

Magic Eden v2 (`collector_crypt`, `phygitals`) and OpenSea v2 (`courtyard`) are official documented public APIs with explicit third-party support.

---

## Development

```bash
uv sync --group dev
uv run pytest
uv run ruff check src/
uv run mypy src/
```

## Adding a source

1. Create `src/marketplace_aggregator/sources/yourplatform.py` with `fetch(client: httpx.Client, **kwargs) -> Iterator[OTCListing]`.
2. Register in `src/marketplace_aggregator/sources/__init__.py`.
3. Add to `DEFAULT_SOURCES`.

## License

MIT
