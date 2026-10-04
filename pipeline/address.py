"""Normalize street addresses so Ct/Court and similar forms match."""

from __future__ import annotations

import re

STREET_EXPAND = {
    "ct": "court",
    "court": "court",
    "dr": "drive",
    "drive": "drive",
    "st": "street",
    "street": "street",
    "ave": "avenue",
    "avenue": "avenue",
    "blvd": "boulevard",
    "boulevard": "boulevard",
    "ln": "lane",
    "lane": "lane",
    "rd": "road",
    "road": "road",
    "pl": "place",
    "place": "place",
    "cir": "circle",
    "circle": "circle",
    "ter": "terrace",
    "terrace": "terrace",
    "hwy": "highway",
    "highway": "highway",
    "pkwy": "parkway",
    "parkway": "parkway",
    "trl": "trail",
    "trail": "trail",
    "way": "way",
}


def normalize_address(value: str) -> str:
    text = re.sub(r"[.,#]", " ", (value or "").lower())
    return " ".join(text.split())


def canonical_address(value: str) -> str:
    tokens = normalize_address(value).split()
    return " ".join(STREET_EXPAND.get(token, token) for token in tokens)


def query_forms(value: str) -> list[str]:
    forms = []
    seen: set[str] = set()
    for form in (normalize_address(value), canonical_address(value)):
        if form and form not in seen:
            seen.add(form)
            forms.append(form)
    return forms


def address_matches(query: str, address: str, city: str = "") -> bool:
    needle = canonical_address(query)
    if not needle:
        return False
    return needle in canonical_address(f"{address} {city}")
