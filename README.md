# marketplace_aggregator

Active OTC listing aggregator for graded and raw trading cards across web3 and crypto-native marketplaces.

Fetches open asks (buy-now listings) from multiple platforms, normalizes them into a unified schema, and writes NDJSON output. Designed for 4-hour cadence runs.

## Prerequisites

- **Python 3.10+** — check with `python3 --version`
- **uv** — fast Python package/project manager

Install uv (one command, no Python required first):

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.sh | iex"
```

That's it. uv manages the virtualenv and all dependencies automatically.

## Getting started

```bash
git clone https://github.com/your-org/marketplace_aggregator
cd marketplace_aggregator
uv sync
```

**Get graded card data in ~10 seconds — no API key needed** (7 of 8 sources require none):

```bash
uv run marketplace_aggregator --sources collector_crypt --max-pages 1 --output /tmp/test.ndjson
```

Inspect what came back:

```bash
# count by grader (PSA / BGS / CGC / raw)
jq -r '.grader // "raw"' /tmp/test.ndjson | sort | uniq -c | sort -rn

# top asks, highest first
jq -r '[.card_name, .grader, .grade, .ask_usd] | @tsv' /tmp/test.ndjson \
  | sort -t$'\t' -k4 -rn | head -20
```

## Running all sources

7 of the 8 sources need no credentials. `courtyard` requires an OpenSea key but skips cleanly with a warning if none is set. Run them all at once:

```bash
uv run marketplace_aggregator
```

That runs all 8 sources (`renaiss`, `beezie`, `ready`, `mnstr`, `playkami`, `collector_crypt`, `phygitals`, `courtyard`). Courtyard will print a yellow "skipping" message and yield nothing if `OPENSEA_API_KEY` is unset — every other source proceeds normally.

To cap pages for a fast sanity check across all sources:

```bash
uv run marketplace_aggregator --max-pages 2 --output /tmp/snapshot.ndjson
```

## Enabling Courtyard (OpenSea key)

```bash
cp .env.example .env
# edit .env and set OPENSEA_API_KEY=your_key_here

uv sync --extra dotenv          # installs python-dotenv so .env loads automatically
uv run marketplace_aggregator   # now includes courtyard
```

## Working with the output

Output is NDJSON — one JSON object per line — written to `./data/{date}/snapshot_{time}.ndjson` by default (or `--output <path>`). The CLI also prints a summary table (listing count, % with price, grade, cert) after each run.

**Filter with jq:**

```bash
# graded Pokemon cards only, sorted by ask price
jq 'select(.franchise == "pokemon" and .grade != null)' snapshot.ndjson \
  | jq -r '[.grader, .grade, .ask_usd, .card_name] | @tsv' \
  | sort -t$'\t' -k3 -rn | head -30

# all PSA 10s across every source
jq 'select(.grader == "PSA" and .grade == "10")' snapshot.ndjson
```

**Load into pandas:**

```python
import pandas as pd
df = pd.read_json("snapshot.ndjson", lines=True)
print(df.groupby(["source", "grader"])["ask_usd"].describe())
```

**Query with DuckDB (no import step):**

```sql
-- install once: pip install duckdb
SELECT source, grader, COUNT(*) AS listings, AVG(ask_usd) AS avg_ask
FROM read_ndjson_auto('snapshot.ndjson')
WHERE franchise = 'pokemon'
GROUP BY 1, 2
ORDER BY 3 DESC;
```

## Supported sources

| Key | Platform | Chain | API type | Key required |
|-----|----------|-------|----------|:---:|
| `renaiss` | [Renaiss](https://renaiss.xyz) | BNB Chain | tRPC, public | — |
| `beezie` | [Beezie](https://beezie.com) | Ethereum | REST, public | — |
| `ready` | Ready | — | REST, public | — |
| `mnstr` | MNSTR | — | REST, public | — |
| `playkami` | [PlayKami](https://playkami.com) | — | REST, public | — |
| `collector_crypt` | [Collector Crypt](https://collectorcrypt.io) | Solana | Magic Eden v2 (official public API) | — |
| `phygitals` | [Phygitals](https://phygitals.io) | Solana | Magic Eden v2 (official public API) | — |
| `courtyard` | [Courtyard](https://courtyard.io) | Polygon | OpenSea v2 (official public API) | `OPENSEA_API_KEY` |

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENSEA_API_KEY` | For `courtyard` only | OpenSea API v2 key |

Copy `.env.example` to `.env` and fill in values. With the `dotenv` optional dependency (`uv sync --extra dotenv`), the `.env` file is loaded automatically on each run.

## Security & access posture

Every source in the default run uses a **public, unauthenticated API endpoint** — the same ones each platform's own frontend calls. No credentials are embedded in this repository, no auth tokens are spoofed, and no Cloudflare or bot-detection bypass is attempted.

The HTTP client sends an honest `User-Agent: Mozilla/5.0 (compatible; marketplace_aggregator/0.1)`, uses HTTP/2, and sleeps 150–250 ms between paginated requests to stay well within normal usage rates.

Two sources use **official documented public APIs** with explicit third-party support: Magic Eden v2 (`collector_crypt`, `phygitals`) and OpenSea v2 (`courtyard`). The rest call open REST/tRPC endpoints with no authentication required by the platform.

## Output schema

Each line is a JSON object with these fields:

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

`grade` is `null` for raw/ungraded cards. `grader` is `null` when no grading company is known.

## Adding a source

1. Create `src/marketplace_aggregator/sources/yourplatform.py` with a `fetch(client: httpx.Client, **kwargs) -> Iterator[OTCListing]` function.
2. Register it in `src/marketplace_aggregator/sources/__init__.py`.
3. Add it to `DEFAULT_SOURCES` if it should run by default.

## Development

```bash
uv sync --group dev
uv run pytest
uv run ruff check src/
uv run mypy src/
```

## License

MIT
