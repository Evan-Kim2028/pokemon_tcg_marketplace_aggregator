from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
from rich import print as rprint

from marketplace_aggregator._utils import retry_get
from marketplace_aggregator.models import OTCListing

CONTRACT = "0x251be3a17af4892035c37ebf5890f4a4d889dcad"
LISTINGS_URL = "https://api.opensea.io/api/v2/listings/collection/courtyard-nft/all"
NFT_URL = f"https://api.opensea.io/api/v2/chain/matic/contract/{CONTRACT}/nfts"

# Disk cache for NFT traits — persists across runs so only new listings need API calls
_DEFAULT_CACHE_PATH = Path.home() / ".cache" / "marketplace_aggregator" / "courtyard_traits.json"
_TRAIT_CACHE: dict[str, dict] = {}
_cache_path: Path = _DEFAULT_CACHE_PATH


def configure_cache(path: Path) -> None:
    global _cache_path
    _cache_path = path


def _load_cache() -> None:
    global _TRAIT_CACHE
    if _TRAIT_CACHE:
        return
    if _cache_path.exists():
        try:
            _TRAIT_CACHE = json.loads(_cache_path.read_text())
        except Exception:
            _TRAIT_CACHE = {}


def _save_cache() -> None:
    _cache_path.parent.mkdir(parents=True, exist_ok=True)
    _cache_path.write_text(json.dumps(_TRAIT_CACHE))


def _attr(traits: list[dict], trait: str) -> str | None:
    for t in traits:
        if t.get("trait_type") == trait:
            v = t.get("value")
            return str(v) if v is not None else None
    return None


def _normalize(token_id: str, price_usd: float, nft: dict) -> OTCListing:
    traits: list[dict] = nft.get("traits") or []
    name = nft.get("name") or ""

    # "10 PRISTINE" / "9 MINT+" — first token is the numeric grade
    grade_raw = _attr(traits, "Grade")
    grade: str | None = None
    if grade_raw:
        parts = grade_raw.split()
        grade = parts[0] if parts else grade_raw

    grader = _attr(traits, "Grader")
    if grader:
        grader = grader.upper()

    insured_raw = _attr(traits, "Insured Value")
    insured_usd: float | None = None
    if insured_raw:
        try:
            insured_usd = float(insured_raw)
        except (ValueError, TypeError):
            pass

    return OTCListing(
        source="courtyard",
        listing_id=token_id,
        card_name=_attr(traits, "Card Name") or name,
        set_name=_attr(traits, "Set"),
        card_number=_attr(traits, "Card Number"),
        grade=grade,
        grader=grader,
        cert_number=_attr(traits, "Serial"),
        ask_usd=price_usd,
        bid_usd=None,
        insured_usd=insured_usd,
        listing_url=nft.get("opensea_url"),
        image_url=nft.get("image_url") or nft.get("display_image_url"),
        franchise="pokemon",
        listed_at=None,
    )


def _api_key() -> str | None:
    return os.getenv("OPENSEA_API_KEY")


def fetch(client: httpx.Client, max_pages: int | None = None) -> Iterator[OTCListing]:
    # Traits are not inline in the listings response — each new token needs a separate
    # NFT fetch. Results are cached to avoid redundant calls on subsequent runs.
    api_key = _api_key()
    if not api_key:
        rprint("[yellow]  courtyard: OPENSEA_API_KEY not set — skipping[/yellow]")
        return

    os_headers = {"Accept": "application/json", "X-API-KEY": api_key}
    _load_cache()
    hits = misses = 0

    cursor: str | None = None
    page = 0
    try:
        while True:
            params: dict = {"limit": 100}
            if cursor:
                params["next"] = cursor
            resp = retry_get(client, LISTINGS_URL, params=params, headers=os_headers)
            body = resp.json()
            listings = body.get("listings", [])
            cursor = body.get("next")

            for listing in listings:
                price_info = listing.get("price", {}).get("current", {})
                raw_val = price_info.get("value")
                if raw_val is None:
                    continue
                price_usd = int(raw_val) / (10 ** price_info.get("decimals", 6))

                offer = listing.get("protocol_data", {}).get("parameters", {}).get("offer", [])
                if not offer:
                    continue
                token_id = str(offer[0].get("identifierOrCriteria", ""))

                if token_id in _TRAIT_CACHE:
                    nft_data = _TRAIT_CACHE[token_id]
                    hits += 1
                else:
                    r2 = client.get(f"{NFT_URL}/{token_id}", headers=os_headers, timeout=20)
                    for _attempt in range(3):
                        if r2.status_code != 429:
                            break
                        time.sleep(5 * 2 ** _attempt)
                        r2 = client.get(f"{NFT_URL}/{token_id}", headers=os_headers, timeout=20)
                    if r2.status_code != 200:
                        continue
                    nft_data = r2.json().get("nft") or r2.json()
                    _TRAIT_CACHE[token_id] = nft_data
                    misses += 1
                    time.sleep(0.15)

                traits = nft_data.get("traits") or []
                category = _attr(traits, "Category") or ""
                if "pok" not in category.lower():
                    continue

                yield _normalize(token_id, price_usd, nft_data)

            page += 1
            if not cursor or not listings:
                break
            if max_pages and page >= max_pages:
                break
            time.sleep(0.25)
    finally:
        if misses > 0:
            _save_cache()
        if hits or misses:
            rprint(f"  [dim]courtyard trait cache: {hits} hits, {misses} misses[/dim]")
