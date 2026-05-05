from __future__ import annotations

import re
import time

import httpx

_GRADER_GRADE_RE = re.compile(
    r"\b(PSA|BGS|CGC|SGC|HGA|CSG|PCA|GMA)\s+(\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)

_GRADE_NUMERIC_RE = re.compile(r"^(\d+(?:\.\d+)?)\b")

# Known text-only grade labels → normalized value
_GRADE_TEXT_MAP: dict[str, str] = {
    "gm10": "10",       # CGC Gem Mint 10
    "pristine": "10",   # CGC / BGS Pristine
    "10 pristine": "10",
    "authentic": "Auth",
}

# Grader aliases to canonical uppercase names
_GRADER_ALIASES: dict[str, str] = {
    "CGC TRADING CARDS": "CGC",
    "BECKETT": "BGS",
}

# One Piece set/card-number patterns used by infer_franchise
_ONE_PIECE_RE = re.compile(r"\bop\d{2}-", re.IGNORECASE)


def infer_franchise(name: str, brand: str = "") -> str | None:
    lower = (name + " " + brand).lower()
    if "pokemon" in lower or "pokémon" in lower:
        return "pokemon"
    if "one piece" in lower or _ONE_PIECE_RE.search(lower):
        return "one_piece"
    if any(s in lower for s in ("baseball", "basketball", "football", "soccer", "nfl", "nba", "mlb")):
        return "sports"
    return None


def parse_grade_from_name(name: str) -> tuple[str | None, str | None]:
    """Return (grader, grade) parsed from a trailing 'PSA 10' pattern."""
    m = _GRADER_GRADE_RE.search(name)
    if m:
        return m.group(1).upper(), m.group(2)
    return None, None


def normalize_grade(raw: str) -> str:
    """Normalize grade to a bare numeric string where possible.

    "10 Gem Mint" → "10", "GM10" → "10", "Pristine" → "10", "9 Mint" → "9", "10.0" → "10".
    Unrecognized text grades (e.g. "MINT", "NM/MT+") are returned unchanged.
    """
    stripped = raw.strip()
    m = _GRADE_NUMERIC_RE.match(stripped)
    if m:
        val = m.group(1)
        return val[:-2] if val.endswith(".0") else val
    return _GRADE_TEXT_MAP.get(stripped.lower(), stripped)


def normalize_grader(raw: str) -> str:
    """Normalize grader to canonical uppercase form ("CGC TRADING CARDS" → "CGC")."""
    upper = raw.strip().upper()
    return _GRADER_ALIASES.get(upper, upper)


def retry_get(client: httpx.Client, url: str, *, max_retries: int = 3, **kwargs) -> httpx.Response:
    """GET with automatic retry on HTTP 429 (exponential back-off: 5 s, 10 s, 20 s)."""
    resp = client.get(url, **kwargs)
    for attempt in range(max_retries):
        if resp.status_code != 429:
            break
        time.sleep(5 * 2 ** attempt)
        resp = client.get(url, **kwargs)
    resp.raise_for_status()
    return resp
