from __future__ import annotations

import httpx


def make_client(**kwargs) -> httpx.Client:
    # http2 required for Cloudflare-fronted sources (MNSTR) — httpcore hangs without it.
    return httpx.Client(
        http2=True,
        timeout=httpx.Timeout(60.0, connect=15.0),
        headers={"User-Agent": "Mozilla/5.0 (compatible; marketplace_aggregator/0.1)"},
        follow_redirects=True,
        **kwargs,
    )
