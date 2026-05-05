from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from marketplace_aggregator._utils import normalize_grade, normalize_grader


@dataclass
class OTCListing:
    source: str               # "mnstr" | "renaiss" | "ready" | "collector_crypt" | ...
    listing_id: str
    card_name: str
    set_name: str | None
    card_number: str | None
    grade: str | None         # "10", "9.5", "Auth", etc.  None = ungraded/raw
    grader: str | None        # "PSA" | "BGS" | "CGC" | None
    cert_number: str | None
    ask_usd: float | None
    bid_usd: float | None
    insured_usd: float | None # seller-declared insured value or platform FMV
    listing_url: str | None
    image_url: str | None
    franchise: str | None     # "pokemon" | "sports" | None
    listed_at: str | None     # ISO-8601 or None
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

    def __post_init__(self) -> None:
        if self.grade is not None:
            self.grade = normalize_grade(self.grade)
        if self.grader is not None:
            self.grader = normalize_grader(self.grader)
        if self.franchise is not None:
            self.franchise = self.franchise.lower().replace(" ", "_")

    def to_dict(self) -> dict:
        return asdict(self)
