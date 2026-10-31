"""Product understanding: what is this pack, and how is its quantity measured?

The rulebook (Part B) splits commodities by how they are sold:
  Table I  = by weight or volume (food, liquids, powders, cement ...)
  Table II = by length, area or piece count (fabric, tiles, bedsheets, towels, NOTEBOOKS ...)
Rule 7 (numeral height) is skipped for every product by team decision, but the product must still be
recognised: a notebook's net quantity is its number of pages, a bottle's is millilitres, a cloth's is metres.

Order of evidence: the category the user picked > words on the label > the unit of the quantity itself.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

# category -> how its net quantity is declared: weight | volume | count | length | area | None (unknown)
MEASURE: Dict[str, Optional[str]] = {
    "tea": "weight", "biscuits": "weight", "salt": "weight", "cement": "weight", "white_cement": "weight",
    "toilet_soap": "weight", "aerated_drinks": "volume", "lpg_cylinder": "weight", "agri_produce": "weight",
    "bedsheet": "count", "towel": "count", "notebook": "count", "bidi": "count", "incense": "count",
    "fabric": "length", "tiles": "area",
}
MEASURE_UNITS = {
    "weight": "g / kg", "volume": "ml / l", "count": "a plain count (pages, pieces, sheets, pairs, N)",
    "length": "mm / cm / m", "area": "sq cm / sq m",
}
TABLE_FOR = {"weight": "Table I (by net quantity)", "volume": "Table I (by net quantity)",
             "count": "Table II (by display panel area)", "length": "Table II (by display panel area)",
             "area": "Table II (by display panel area)"}

_R = lambda p: re.compile(p, re.I)  # noqa: E731
# (category, pattern). Exemption categories (fast food, scheduled drug, agri produce) are never guessed,
# because a wrong guess would wrongly exempt a pack from every check.
INFER_RULES = [
    ("white_cement", _R(r"white\s*cement")),
    ("cement", _R(r"\bcement\b")),
    ("tea", _R(r"\b(?:tea|chai)\b")),
    ("biscuits", _R(r"\b(?:biscuits?|cookies?|crackers?)\b")),
    ("salt", _R(r"\b(?:iodi[sz]ed|table|rock|sea|common|crystal|free[\s\-]*flow(?:ing)?)\s+salt\b")),
    ("toilet_soap", _R(r"\b(?:toilet|bathing|bath|beauty)\s+soap\b|\bsoap\b(?!.*\b(?:detergent|laundry|washing|dish)\b)")),
    ("aerated_drinks", _R(r"\baerated\b|\bcarbonated\b|soft\s*drinks?|\bcola\b|\bsoda\b")),
    ("bedsheet", _R(r"bed\s*-?\s*sheets?|bed\s*linen")),
    ("towel", _R(r"\btowels?\b")),
    ("bidi", _R(r"\bbidis?\b|\bbeedis?\b")),
    ("incense", _R(r"incense|agar\s*-?\s*bath?ti|\bdhoop\b")),
    ("lpg_cylinder", _R(r"\blpg\b")),
    ("fabric", _R(r"\bfabrics?\b|\bsuiting\b|\bshirting\b|\bcloth\b")),
    ("tiles", _R(r"\btiles?\b")),
    ("notebook", _R(r"note\s*-?\s*books?|exercise\s*books?|long\s*books?|\bregisters?\b|\bdiary\b|\bjotter\b|\bruled\b|\bunruled\b|\bsingle\s*line\b|\bpractical\s*books?\b|\bdrawing\s*books?\b")),
]
_PAGES_RE = re.compile(r"\b\d{1,5}\s*(?:pages?|pgs?|leaves)\b|\b(?:pages?|pgs?)\s*[:=\-]\s*\d{1,5}\b", re.I)


def infer_category(text: str) -> Optional[str]:
    hits: Dict[str, int] = {}
    for cat, rx in INFER_RULES:
        n = len(rx.findall(text))
        if n:
            hits[cat] = n
    if _PAGES_RE.search(text):  # a page count only ever describes books / notebooks / diaries
        hits["notebook"] = hits.get("notebook", 0) + 2
    if "white_cement" in hits:
        hits.pop("cement", None)
    if not hits:
        return None
    return max(hits, key=lambda c: hits[c])  # ties resolve to the earlier rule


def measure_from_quantity(kind: str, base_unit: Optional[str]) -> Optional[str]:
    """When the category is unknown, the declared unit still tells how the product is measured."""
    if kind == "count":
        return "count"
    return {"g": "weight", "ml": "volume", "m": "length", "m2": "area"}.get(base_unit or "")


def product_info(category: str, label: str, source: str, measure: Optional[str]) -> Dict[str, str]:
    info = {"category": category, "category_label": label, "source": source}
    if measure:
        info["measure"] = measure
        info["net_quantity_unit"] = MEASURE_UNITS[measure]
        info["size_table"] = TABLE_FOR[measure]
        info["rule7_note"] = ("Rule 7 numeral height would be checked against " + TABLE_FOR[measure] +
                              "; skipped for every product (team decision: a photo has no real-world scale).")
    return info
