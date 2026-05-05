from __future__ import annotations

from marketplace_aggregator.models import OTCListing
from marketplace_aggregator._utils import infer_franchise, parse_grade_from_name


class TestOTCListing:
    def test_to_dict_roundtrip(self):
        listing = OTCListing(
            source="test",
            listing_id="abc123",
            card_name="Charizard",
            set_name="Base Set",
            card_number="4",
            grade="10",
            grader="PSA",
            cert_number="12345678",
            ask_usd=9500.0,
            bid_usd=None,
            insured_usd=None,
            listing_url="https://example.com",
            image_url=None,
            franchise="pokemon",
            listed_at=None,
        )
        d = listing.to_dict()
        assert d["source"] == "test"
        assert d["ask_usd"] == 9500.0
        assert d["grade"] == "10"
        assert d["grader"] == "PSA"
        assert "fetched_at" in d

    def test_null_grade_for_raw(self):
        listing = OTCListing(
            source="test",
            listing_id="raw1",
            card_name="Pikachu",
            set_name=None,
            card_number=None,
            grade=None,
            grader=None,
            cert_number=None,
            ask_usd=50.0,
            bid_usd=None,
            insured_usd=None,
            listing_url=None,
            image_url=None,
            franchise=None,
            listed_at=None,
        )
        assert listing.grade is None
        assert listing.grader is None


class TestParseGradeFromName:
    def test_psa_10(self):
        grader, grade = parse_grade_from_name("Charizard Holo 1st Edition PSA 10")
        assert grader == "PSA"
        assert grade == "10"

    def test_bgs_95(self):
        grader, grade = parse_grade_from_name("Blastoise BGS 9.5")
        assert grader == "BGS"
        assert grade == "9.5"

    def test_cgc_grader(self):
        grader, grade = parse_grade_from_name("Mewtwo CGC 8")
        assert grader == "CGC"
        assert grade == "8"

    def test_no_match(self):
        grader, grade = parse_grade_from_name("Raw Charizard ungraded")
        assert grader is None
        assert grade is None

    def test_case_insensitive(self):
        grader, grade = parse_grade_from_name("Card psa 10")
        assert grader == "PSA"
        assert grade == "10"


class TestInferFranchise:
    def test_pokemon(self):
        assert infer_franchise("Charizard Pokemon Card") == "pokemon"

    def test_pokemon_accented(self):
        assert infer_franchise("Pokémon Base Set") == "pokemon"

    def test_sports_nba(self):
        assert infer_franchise("LeBron James NBA Rookie") == "sports"

    def test_unknown(self):
        assert infer_franchise("Mystery Item") is None


class TestSourceRegistry:
    def test_registry_has_all_sources(self):
        from marketplace_aggregator.sources import REGISTRY
        assert "renaiss" in REGISTRY
        assert "beezie" in REGISTRY
        assert "courtyard" in REGISTRY
        assert "collector_crypt" in REGISTRY
        assert "phygitals" in REGISTRY
        assert "playkami" in REGISTRY
        assert "mnstr" in REGISTRY
        assert "ready" in REGISTRY

    def test_all_sources_complete(self):
        from marketplace_aggregator.sources import REGISTRY, ALL_SOURCES
        assert set(ALL_SOURCES) == set(REGISTRY.keys())
