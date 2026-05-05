from __future__ import annotations

from collections.abc import Iterator

import httpx

from marketplace_aggregator._utils import infer_franchise, retry_get
from marketplace_aggregator.models import OTCListing

COLLECTION_URL = "https://api.mnstr.xyz/mnstr/collection"


def _normalize(item: dict) -> OTCListing:
    slug = item.get("slug", "")

    ask_usd: float | None = None
    try:
        ask_usd = float(item["listPriceUsd"]) if item.get("listPriceUsd") is not None else None
    except (ValueError, TypeError):
        pass

    insured_usd: float | None = None
    try:
        insured_usd = float(item["fmv"]) if item.get("fmv") is not None else None
    except (ValueError, TypeError):
        pass

    grader = item.get("gradingCompany")
    if grader:
        grader = grader.upper()

    # grading = "PSA 10" / "BGS 9.5" — last token is the numeric grade
    grade: str | None = None
    raw_grading = item.get("grading")
    if raw_grading:
        parts = str(raw_grading).split()
        grade = parts[-1] if len(parts) > 1 else raw_grading

    title = item.get("title") or item.get("name") or ""
    franchise = item.get("category") or infer_franchise(title)

    return OTCListing(
        source="mnstr",
        listing_id=str(item.get("remoteId") or slug or ""),
        card_name=title or item.get("name", ""),
        set_name=item.get("set"),
        card_number=item.get("cardNumber"),
        grade=grade,
        grader=grader,
        cert_number=str(item["serialNumber"]) if item.get("serialNumber") else None,
        ask_usd=ask_usd,
        bid_usd=None,
        insured_usd=insured_usd,
        listing_url=f"https://mnstr.xyz/card/{slug}" if slug else None,
        image_url=item.get("image") or item.get("imageUrl"),
        franchise=franchise,
        listed_at=item.get("listedAt") or item.get("createdAt"),
    )


def fetch(client: httpx.Client, **_kwargs) -> Iterator[OTCListing]:
    resp = retry_get(client, COLLECTION_URL, headers={"Accept": "application/json"})
    body = resp.json()
    items = body.get("data") or body.get("items") or (body if isinstance(body, list) else [])
    for item in items:
        if item.get("canBeSold") and item.get("listPriceUsd") is not None:
            listing = _normalize(item)
            if listing.franchise is not None and listing.franchise != "pokemon":
                continue
            yield listing
