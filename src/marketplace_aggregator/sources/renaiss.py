from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator

import httpx

from marketplace_aggregator._utils import infer_franchise, retry_get
from marketplace_aggregator.models import OTCListing

BASE_URL = "https://www.renaiss.xyz/api/trpc/collectible.list"

# Renaiss item names are prefixed with the grade label, e.g.:
# "PSA 10 Gem Mint 2024 Pokemon ..." → strip to "2024 Pokemon ..."
_NAME_PREFIX_RE = re.compile(
    r"^(?:PSA|CGC|BGS|SGC|HGA|TAG)\s+[\d.]+(?:\s+[A-Za-z][A-Za-z+\-]*)*\s+(?=\d{4}\b)",
    re.IGNORECASE,
)


def _normalize(item: dict) -> OTCListing:
    ask_usd: float | None = None
    raw_ask = item.get("askPriceInUSDT")
    if raw_ask is not None:
        try:
            v = int(raw_ask) / 1e18
            ask_usd = v if v > 0 else None
        except (ValueError, TypeError):
            pass

    insured_usd: float | None = None
    raw_fmv = item.get("fmvPriceInUSD")
    if raw_fmv is not None:
        try:
            insured_usd = int(raw_fmv) / 100.0
        except (ValueError, TypeError):
            pass

    # Null out obviously bad USDT prices (seller mis-entered amount in wei).
    if ask_usd is not None and ask_usd > 1_000_000:
        ask_usd = None
    elif ask_usd is not None and insured_usd and insured_usd > 0 and ask_usd / insured_usd > 1000:
        ask_usd = None

    cert_number: str | None = None
    for attr in item.get("attributes") or []:
        if attr.get("trait") == "Serial":
            parts = str(attr.get("value", "")).split("#")
            if len(parts) > 1:
                cert_number = parts[-1].strip()
            break

    raw_name = item.get("name") or ""
    card_name = _NAME_PREFIX_RE.sub("", raw_name) or raw_name

    item_id = str(item.get("id", ""))
    return OTCListing(
        source="renaiss",
        listing_id=item_id,
        card_name=card_name,
        set_name=None,
        card_number=None,
        grade=str(item["grade"]) if item.get("grade") is not None else None,
        grader=item.get("gradingCompany"),
        cert_number=cert_number,
        ask_usd=ask_usd,
        bid_usd=None,
        insured_usd=insured_usd,
        listing_url=f"https://www.renaiss.xyz/collectible/{item_id}" if item_id else None,
        image_url=item.get("imageUrl") or item.get("image"),
        franchise=infer_franchise(card_name),
        listed_at=item.get("listDate") or item.get("createdAt"),
    )


def fetch(client: httpx.Client, max_pages: int | None = None) -> Iterator[OTCListing]:
    limit = 50
    offset = 0
    page = 0
    while True:
        input_json = json.dumps({"json": {
            "limit": limit,
            "offset": offset,
            "sortBy": "listDate",
            "sortOrder": "desc",
            "listedOnly": True,
        }})
        resp = retry_get(client, BASE_URL, params={"input": input_json}, headers={"Accept": "application/json"})
        collection = resp.json().get("result", {}).get("data", {}).get("json", {}).get("collection", [])
        if not collection:
            break
        for item in collection:
            listing = _normalize(item)
            if listing.franchise is not None and listing.franchise != "pokemon":
                continue
            yield listing
        offset += limit
        page += 1
        if len(collection) < limit:
            break
        if max_pages and page >= max_pages:
            break
        time.sleep(0.15)
