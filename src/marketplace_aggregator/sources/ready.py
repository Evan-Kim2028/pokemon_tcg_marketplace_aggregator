from __future__ import annotations

import time
from collections.abc import Iterator

import httpx

from marketplace_aggregator._utils import infer_franchise, retry_get
from marketplace_aggregator.models import OTCListing

BASE_URL = "https://api.ready.cards/api/v1/nft/listNftForUser"


def _normalize(doc: dict) -> OTCListing:
    nft_id = str(doc.get("id") or doc.get("tokenId") or "")
    listing_price = doc.get("listingPrice")
    market_price = doc.get("marketPrice") or doc.get("fmv")
    name = doc.get("name") or doc.get("title", "")
    return OTCListing(
        source="ready",
        listing_id=nft_id,
        card_name=name,
        set_name=doc.get("setName"),
        card_number=doc.get("cardNumber"),
        grade=str(doc["gradeNum"]) if doc.get("gradeNum") is not None else doc.get("grade"),
        grader=doc.get("department") or doc.get("gradingCompany"),
        cert_number=str(doc["certNumber"]) if doc.get("certNumber") else None,
        ask_usd=float(listing_price) if listing_price is not None else None,
        bid_usd=None,
        insured_usd=float(market_price) if market_price is not None else None,
        listing_url=f"https://ready.cards/nft/{nft_id}" if nft_id else None,
        image_url=doc.get("imageUrl") or doc.get("image"),
        franchise=infer_franchise(name),
        listed_at=doc.get("listedAt") or doc.get("createdAt"),
    )


def fetch(client: httpx.Client, max_pages: int | None = None) -> Iterator[OTCListing]:
    page = 1
    limit = 1000
    while True:
        resp = retry_get(client, BASE_URL, params={"limit": limit, "page": page}, headers={"Accept": "application/json"})
        body = resp.json()
        docs = body.get("result", {}).get("docs") or body.get("docs") or body.get("data") or []
        if isinstance(body, list):
            docs = body
        if not docs:
            break
        for doc in docs:
            if doc.get("isListed") and doc.get("listingPrice") is not None:
                yield _normalize(doc)
        if len(docs) < limit:
            break
        if max_pages and page >= max_pages:
            break
        page += 1
        time.sleep(0.15)
