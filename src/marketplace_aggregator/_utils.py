from __future__ import annotations

import re
import time

import httpx

_GRADER_GRADE_RE = re.compile(
    r"\b(PSA|BGS|CGC|SGC|HGA|CSG|PCA|GMA|TAG)\s+(\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)

_GRADE_NUMERIC_RE = re.compile(r"^(\d+(?:\.\d+)?)\b")

# Known text-only grade labels → normalized value
_GRADE_TEXT_MAP: dict[str, str] = {
    "gm10": "10",        # CGC Gem Mint 10
    "pristine": "10",    # CGC / BGS Pristine
    "10 pristine": "10",
    "gem mint": "10",    # BGS Gem Mint 10 label without number
    "gem mint 10": "10",
    "mint": "9",         # BGS/PSA Mint label = grade 9
    "near mint+": "8.5", # BGS Near Mint+ label = 8.5
    "near mint": "8",    # BGS Near Mint label = 8
    "excellent+": "6",   # BGS Excellent+ = 6
    "nm/mt+": "8.5",     # SGC Near Mint-Mint+ label
    "authentic": "Auth",
}

# Grader aliases to canonical uppercase names
_GRADER_ALIASES: dict[str, str] = {
    "CGC TRADING CARDS": "CGC",
    "BECKETT": "BGS",
}

# One Piece set/card-number patterns used by infer_franchise
_ONE_PIECE_RE = re.compile(r"\bop\d{2}-", re.IGNORECASE)

# Pokemon character names that commonly appear in graded card names without the
# word "pokemon" — used as a secondary franchise signal in infer_franchise.
_POKEMON_NAMES: frozenset[str] = frozenset({
    "pikachu", "charizard", "mewtwo", "mew", "eevee", "gengar", "snorlax",
    "gyarados", "raichu", "bulbasaur", "squirtle", "venusaur", "blastoise",
    "alakazam", "machamp", "golem", "arcanine", "lapras", "vaporeon",
    "jolteon", "flareon", "espeon", "umbreon", "leafeon", "glaceon", "sylveon",
    "dragonite", "articuno", "zapdos", "moltres", "ditto", "jigglypuff",
    "clefairy", "ninetales", "magneton", "haunter", "electabuzz", "magmar",
    "tauros", "chansey", "kangaskhan", "starmie", "scyther", "jynx",
    "electivire", "magmortar", "lugia", "ho-oh", "togepi", "espeon",
    "suicune", "raikou", "entei", "celebi", "tyranitar",
    "treecko", "torchic", "mudkip", "blaziken", "swampert", "sceptile",
    "gardevoir", "absol", "rayquaza", "deoxys", "kyogre", "groudon",
    "latias", "latios", "jirachi", "turtwig", "chimchar", "piplup",
    "lucario", "garchomp", "luxray", "togekiss", "leafeon", "glaceon",
    "dialga", "palkia", "giratina", "arceus", "darkrai", "shaymin",
    "snivy", "tepig", "oshawott", "samurott", "emboar", "serperior",
    "zoroark", "reshiram", "zekrom", "kyurem", "genesect", "victini",
    "chespin", "fennekin", "froakie", "greninja", "sylveon", "xerneas",
    "yveltal", "zygarde", "diancie", "hoopa", "volcanion",
    "rowlet", "litten", "popplio", "decidueye", "incineroar", "primarina",
    "cosmog", "lunala", "solgaleo", "nihilego", "necrozma",
    "grookey", "scorbunny", "sobble", "zacian", "zamazenta", "eternatus",
    "calyrex", "urshifu", "kubfu",
    "sprigatito", "fuecoco", "quaxly", "koraidon", "miraidon",
    "ting-lu", "chien-pao", "wo-chien", "chi-yu",
    "steelix", "slowking", "magikarp", "milotic", "ivysaur", "haunter",
    "onix", "voltorb", "electrode", "hitmonlee", "hitmonchan", "porygon",
    "kabuto", "aerodactyl", "omanyte", "mewtwo", "nidoking", "nidoqueen",
    "clefable", "wigglytuff", "poliwrath", "kadabra", "rapidash", "dodrio",
    "dewgong", "muk", "cloyster", "hypno", "kingler", "exeggutor",
    "marowak", "lickitung", "weezing", "rhydon", "tangela", "seadra",
    "seaking", "starmie", "mr. mime", "scyther", "electabuzz", "pinsir",
    "tauros", "magikarp", "gyarados", "lapras", "vaporeon", "jolteon",
    "dragonair", "dragonite", "togetic", "flaaffy", "ampharos",
    "bellossom", "marill", "sudowoodo", "politoed", "jumpluff", "yanma",
    "quagsire", "misdreavus", "wobbuffet", "scizor", "heracross",
    "sneasel", "teddiursa", "slugma", "swinub", "corsola", "octillery",
    "delibird", "mantine", "skarmory", "houndoom", "kingdra", "stantler",
    "smeargle", "tyrogue", "miltank", "blissey", "raikou", "entei",
    "lugia", "ho-oh", "celebi",
})


def infer_franchise(name: str, brand: str = "") -> str | None:
    lower = (name + " " + brand).lower()
    if "pokemon" in lower or "pokémon" in lower:
        return "pokemon"
    if "one piece" in lower or _ONE_PIECE_RE.search(lower):
        return "one_piece"
    if any(s in lower for s in ("baseball", "basketball", "football", "soccer", "nfl", "nba", "mlb")):
        return "sports"
    # Secondary: well-known Pokemon character names that appear without "pokemon"
    # in the string (common for set names like "Crown Zenith Lugia EX #17").
    words = re.split(r"[\s\-./,]+", lower)
    if any(w in _POKEMON_NAMES for w in words):
        return "pokemon"
    return None


def parse_grade_from_name(name: str) -> tuple[str | None, str | None]:
    """Return (grader, grade) parsed from a trailing 'PSA 10' pattern."""
    m = _GRADER_GRADE_RE.search(name)
    if m:
        return m.group(1).upper(), m.group(2)
    return None, None


def normalize_grade(raw: str) -> str:
    """Normalize grade to a bare numeric string where possible.

    "10 Gem Mint" → "10", "GM10" → "10", "Pristine" → "10", "9 Mint" → "9", "10.0" → "10".
    Unrecognized text grades (e.g. "MINT", "NM/MT+") are returned unchanged.
    """
    stripped = raw.strip()
    m = _GRADE_NUMERIC_RE.match(stripped)
    if m:
        val = m.group(1)
        return val[:-2] if val.endswith(".0") else val
    return _GRADE_TEXT_MAP.get(stripped.lower(), stripped)


def normalize_grader(raw: str) -> str:
    """Normalize grader to canonical uppercase form ("CGC TRADING CARDS" → "CGC")."""
    upper = raw.strip().upper()
    return _GRADER_ALIASES.get(upper, upper)


def retry_get(client: httpx.Client, url: str, *, max_retries: int = 3, **kwargs) -> httpx.Response:
    """GET with automatic retry on HTTP 429 (exponential back-off: 5 s, 10 s, 20 s)."""
    resp = client.get(url, **kwargs)
    for attempt in range(max_retries):
        if resp.status_code != 429:
            break
        time.sleep(5 * 2 ** attempt)
        resp = client.get(url, **kwargs)
    resp.raise_for_status()
    return resp
