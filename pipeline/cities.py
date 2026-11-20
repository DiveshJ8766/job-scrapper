"""Indian city normalization shared by dedupe (pre-LLM) and LLM post-validation.

The LLM proposes cities; this module maps known spellings to one canonical
name and is used to check that every proposed city is actually supported by
the job's location text or description (anti-hallucination guard).
"""

from __future__ import annotations

import re

# canonical name -> aliases (lowercase). Canonical names follow current official naming.
CITY_ALIASES: dict[str, list[str]] = {
    "Bengaluru": ["bengaluru", "bangalore", "blr", "bengalooru", "banglore"],
    "Mumbai": ["mumbai", "bombay", "navi mumbai", "thane"],
    "Delhi": ["delhi", "new delhi", "delhi ncr"],
    "Gurugram": ["gurugram", "gurgaon"],
    "Noida": ["noida", "greater noida"],
    "Hyderabad": ["hyderabad", "secunderabad", "hitech city", "hitec city"],
    "Chennai": ["chennai", "madras"],
    "Pune": ["pune", "poona", "pimpri", "hinjewadi"],
    "Kolkata": ["kolkata", "calcutta"],
    "Ahmedabad": ["ahmedabad", "amdavad"],
    "Gandhinagar": ["gandhinagar", "gift city"],
    "Jaipur": ["jaipur"],
    "Kochi": ["kochi", "cochin", "ernakulam"],
    "Thiruvananthapuram": ["thiruvananthapuram", "trivandrum"],
    "Coimbatore": ["coimbatore"],
    "Indore": ["indore"],
    "Chandigarh": ["chandigarh", "mohali", "panchkula"],
    "Mysuru": ["mysuru", "mysore"],
    "Mangaluru": ["mangaluru", "mangalore"],
    "Visakhapatnam": ["visakhapatnam", "vizag"],
    "Vadodara": ["vadodara", "baroda"],
    "Surat": ["surat"],
    "Nagpur": ["nagpur"],
    "Lucknow": ["lucknow"],
    "Bhubaneswar": ["bhubaneswar", "bhubaneshwar"],
    "Goa": ["goa", "panaji"],
    "Faridabad": ["faridabad"],
    "Ghaziabad": ["ghaziabad"],
    "Vijayawada": ["vijayawada"],
    "Madurai": ["madurai"],
    "Bhopal": ["bhopal"],
    "Nashik": ["nashik", "nasik"],
    "Dehradun": ["dehradun"],
}

REMOTE_PATTERNS = re.compile(
    r"\b(remote|work from home|wfh|anywhere in india|fully distributed)\b", re.IGNORECASE
)

_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias: canonical for canonical, aliases in CITY_ALIASES.items() for alias in aliases
}
# Longest aliases first so "navi mumbai" wins over "mumbai", "new delhi" over "delhi".
_ALIAS_REGEX = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in sorted(_ALIAS_TO_CANONICAL, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def canonical_city(name: str) -> str | None:
    """Map a single city string to its canonical name, or None if unknown."""
    key = re.sub(r"\s+", " ", (name or "").strip().lower())
    if key in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[key]
    for canonical in CITY_ALIASES:
        if canonical.lower() == key:
            return canonical
    return None


def find_cities(text: str | None) -> list[str]:
    """All canonical cities mentioned in text, in order of first appearance."""
    if not text:
        return []
    seen: list[str] = []
    for m in _ALIAS_REGEX.finditer(text):
        c = _ALIAS_TO_CANONICAL[m.group(1).lower()]
        if c not in seen:
            seen.append(c)
    return seen


def mentions_remote(text: str | None) -> bool:
    return bool(text and REMOTE_PATTERNS.search(text))


def city_supported_by(city: str, *texts: str | None) -> bool:
    """True if `city` (canonical or not) is mentioned in any of the texts via any alias."""
    canonical = canonical_city(city) or city.strip()
    aliases = [a for a, c in _ALIAS_TO_CANONICAL.items() if c == canonical] or [canonical.lower()]
    pattern = re.compile(r"\b(" + "|".join(re.escape(a) for a in aliases) + r")\b", re.IGNORECASE)
    return any(t and pattern.search(t) for t in texts)
