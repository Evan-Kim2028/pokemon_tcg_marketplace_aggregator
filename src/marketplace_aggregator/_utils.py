from __future__ import annotations

import re
import time

import httpx

_GRADER_GRADE_RE = re.compile(
    r"\b(PSA|BGS|CGC|SGC|HGA|CSG|PCA|GMA)\s+(\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)


def infer_franchise(name: str, brand: str = "") -> str | None:
    lower = (name + " " + brand).lower()
    if "pokemon" in lower or "pokémon" in lower:
        return "pokemon"
    if any(s in lower for s in ("baseball", "basketball", "football", "soccer", "nfl", "nba", "mlb")):
        return "sports"
    return None


def parse_grade_from_name(name: str) -> tuple[str | None, str | None]:
    """Return (grader, grade) parsed from a trailing 'PSA 10' pattern."""
    m = _GRADER_GRADE_RE.search(name)
    if m:
        return m.group(1).upper(), m.group(2)
    return None, None


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
