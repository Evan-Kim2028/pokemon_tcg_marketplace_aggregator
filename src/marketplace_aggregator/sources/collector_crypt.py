from __future__ import annotations

import time
from collections.abc import Iterator

import httpx

from marketplace_aggregator._utils import retry_get
from marketplace_aggregator.models import OTCListing

ME_LISTINGS_URL = "https://api-mainnet.magiceden.dev/v2/collections/collector_crypt/listings"
_SOL_USD_CACHE: dict = {}


def _get_sol_usd(client: httpx.Client) -> float:
    if _SOL_USD_CACHE:
        return _SOL_USD_CACHE["price"]
    try:
        r = client.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "solana", "vs_currencies": "usd"},
            timeout=10,
        )
        price = r.json()["solana"]["usd"]
    except Exception:
        price = 150.0
    _SOL_USD_CACHE["price"] = price
    return price


def _attr(attrs: list[dict], trait: str) -> str | None:
    for a in attrs:
        if a.get("trait_type") == trait:
            v = a.get("value")
            return str(v) if v is not None else None
    return None


def _normalize(listing: dict, sol_usd: float) -> OTCListing:
    token: dict = listing.get("token") or {}
    attrs: list[dict] = token.get("attributes") or []
    name = token.get("name") or ""
    price_sol = listing.get("price")

    # "GEM MINT 10" / "NEAR MINT 9" — last token is the grade value
    grade_raw = _attr(attrs, "The Grade")
    grade: str | None = None
    if grade_raw:
        parts = grade_raw.split()
        grade = parts[-1] if parts else grade_raw

    grader = _attr(attrs, "Grading Company")
    if grader:
        grader = grader.upper()

    insured_raw = _attr(attrs, "Insured Value")
    insured_usd: float | None = None
    if insured_raw:
        try:
            insured_usd = float(insured_raw)
        except (ValueError, TypeError):
            pass

    token_addr = listing.get("tokenAddress") or ""
    return OTCListing(
        source="collector_crypt",
        listing_id=token_addr or listing.get("pdaAddress", ""),
        card_name=_attr(attrs, "Card Name") or name,
        set_name=_attr(attrs, "Set"),
        card_number=None,
        grade=grade,
        grader=grader,
        cert_number=_attr(attrs, "Grading ID"),
        ask_usd=price_sol * sol_usd if price_sol is not None else None,
        bid_usd=None,
        insured_usd=insured_usd,
        listing_url=f"https://magiceden.io/item-details/{token_addr}" if token_addr else None,
        image_url=token.get("image") or listing.get("extra", {}).get("img"),
        franchise="pokemon",
        listed_at=None,
    )


def fetch(client: httpx.Client, max_pages: int | None = None) -> Iterator[OTCListing]:
    sol_usd = _get_sol_usd(client)
    offset = 0
    limit = 100
    page = 0
    while True:
        resp = retry_get(client, ME_LISTINGS_URL, params={"offset": offset, "limit": limit})
        listings = resp.json()
        if not listings:
            break
        for listing in listings:
            token = listing.get("token") or {}
            attrs = token.get("attributes") or []
            category = _attr(attrs, "Category") or ""
            if "pokemon" not in category.lower():
                continue
            yield _normalize(listing, sol_usd)
        offset += limit
        page += 1
        if len(listings) < limit:
            break
        if max_pages and page >= max_pages:
            break
        time.sleep(0.2)
