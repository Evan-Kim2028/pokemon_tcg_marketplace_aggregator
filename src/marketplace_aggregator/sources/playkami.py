from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import httpx

from marketplace_aggregator._utils import infer_franchise
from marketplace_aggregator.models import OTCListing

LISTINGS_URL = "https://be.playkami.io/api/marketplace/listings"


def _attr(attrs: list[dict], trait: str) -> str | None:
    for a in attrs:
        if a.get("trait_type") == trait:
            v = a.get("value")
            return str(v) if v is not None else None
    return None


def _normalize(item: dict) -> OTCListing:
    meta: dict = item.get("metadata") or {}
    attrs: list[dict] = meta.get("attributes") or []
    name = meta.get("name") or ""
    image = meta.get("image") or ""

    grade_raw = _attr(attrs, "Grade")
    grade: str | None = None
    if grade_raw:
        parts = grade_raw.split()
        grade = parts[-1] if parts else grade_raw

    grader = _attr(attrs, "Grader")
    if grader:
        grader = grader.upper()

    ask_usd: float | None = None
    raw_price = item.get("price")
    if raw_price is not None:
        try:
            ask_usd = int(raw_price) / 1e6  # USDC 6-decimal
        except (ValueError, TypeError):
            pass

    created_at = item.get("created_at")
    listed_at = (
        datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat()
        if isinstance(created_at, (int, float))
        else created_at
    )

    franchise_raw = _attr(attrs, "Category")
    franchise = franchise_raw.lower() if franchise_raw else infer_franchise(name)

    return OTCListing(
        source="playkami",
        listing_id=str(item.get("id", "")),
        card_name=name,
        set_name=_attr(attrs, "Set"),
        card_number=_attr(attrs, "Card Number"),
        grade=grade,
        grader=grader,
        cert_number=_attr(attrs, "Serial"),
        ask_usd=ask_usd,
        bid_usd=None,
        insured_usd=None,
        listing_url=None,
        image_url=image or None,
        franchise=franchise,
        listed_at=listed_at,
    )


def fetch(client: httpx.Client, **_kwargs) -> Iterator[OTCListing]:
    resp = client.post(
        LISTINGS_URL,
        json={},
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    resp.raise_for_status()
    body = resp.json()
    items = body.get("data") or body.get("listings") or (body if isinstance(body, list) else [])
    for item in items:
        meta = item.get("metadata") or {}
        if meta.get("product_type") == "GRADED_CARD":
            listing = _normalize(item)
            if listing.franchise is not None and listing.franchise != "pokemon":
                continue
            yield listing
