from __future__ import annotations

from collections.abc import Callable, Iterator

from marketplace_aggregator.models import OTCListing
from marketplace_aggregator.sources import (
    beezie,
    collector_crypt,
    courtyard,
    mnstr,
    phygitals,
    playkami,
    ready,
    renaiss,
)

SourceFn = Callable[..., Iterator[OTCListing]]

REGISTRY: dict[str, SourceFn] = {
    "renaiss": renaiss.fetch,
    "beezie": beezie.fetch,
    "ready": ready.fetch,
    "mnstr": mnstr.fetch,
    "playkami": playkami.fetch,
    "collector_crypt": collector_crypt.fetch,
    "phygitals": phygitals.fetch,
    "courtyard": courtyard.fetch,
}

DEFAULT_SOURCES = ["renaiss", "beezie", "ready", "mnstr", "playkami", "collector_crypt", "phygitals", "courtyard"]

# All available source names
ALL_SOURCES = list(REGISTRY)
