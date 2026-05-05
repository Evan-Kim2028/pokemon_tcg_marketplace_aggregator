from __future__ import annotations

import json
import time
from collections.abc import Iterator

import httpx

from marketplace_aggregator._utils import infer_franchise, retry_get
from marketplace_aggregator.models import OTCListing

BASE_URL = "https://www.renaiss.xyz/api/trpc/collectible.list"


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

    cert_number: str | None = None
    for attr in item.get("attributes") or []:
        if attr.get("trait") == "Serial":
            parts = str(attr.get("value", "")).split("#")
            if len(parts) > 1:
                cert_number = parts[-1].strip()
            break

    item_id = str(item.get("id", ""))
    return OTCListing(
        source="renaiss",
        listing_id=item_id,
        card_name=item.get("name", ""),
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
        franchise=infer_franchise(item.get("name", "")),
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
            yield _normalize(item)
        offset += limit
        page += 1
        if len(collection) < limit:
            break
        if max_pages and page >= max_pages:
            break
        time.sleep(0.15)
