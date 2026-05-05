from __future__ import annotations

import time
from collections.abc import Iterator

import httpx

from marketplace_aggregator._utils import infer_franchise, parse_grade_from_name, retry_get
from marketplace_aggregator.models import OTCListing

ACTIVITY_URL = "https://api.beezie.com/activity"

# NOTE: Beezie exposes only a rolling activity feed, not a full open-inventory snapshot.
# order_created + to=None events represent currently open asks.
# Grade/grader are parsed from the name string (e.g. "... PSA 10").


def _normalize(event: dict) -> OTCListing:
    name = event.get("name", "")
    grader, grade = parse_grade_from_name(name)
    ask_usd: float | None = None
    raw_amount = event.get("amount")
    if raw_amount is not None:
        try:
            ask_usd = int(raw_amount) / 1e6  # USDC 6-decimal
        except (ValueError, TypeError):
            pass
    return OTCListing(
        source="beezie",
        listing_id=str(event.get("tokenId") or event.get("id", "")),
        card_name=name,
        set_name=None,
        card_number=None,
        grade=grade,
        grader=grader,
        cert_number=None,
        ask_usd=ask_usd,
        bid_usd=None,
        insured_usd=None,
        listing_url=event.get("marketUrl") or event.get("url"),
        image_url=event.get("imageUrl") or event.get("image"),
        franchise=infer_franchise(name),
        listed_at=event.get("createdAt") or event.get("timestamp"),
    )


def fetch(client: httpx.Client, max_pages: int | None = None) -> Iterator[OTCListing]:
    page = 1
    limit = 50
    while True:
        resp = retry_get(client, ACTIVITY_URL, params={"limit": limit, "page": page}, headers={"Accept": "application/json"})
        body = resp.json()
        events = body.get("activity") or (body if isinstance(body, list) else [])
        if not events:
            break
        for event in events:
            if event.get("type") == "order_created" and event.get("to") is None:
                listing = _normalize(event)
                if listing.franchise is not None and listing.franchise != "pokemon":
                    continue
                yield listing
        if len(events) < limit:
            break
        if max_pages and page >= max_pages:
            break
        page += 1
        time.sleep(0.15)
