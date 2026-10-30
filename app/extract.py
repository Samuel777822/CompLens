"""Field extraction: turns OCR lines into structured findings (regex based).

Everything here works on plain text, so it can be unit tested without images.
Each finder returns a small dataclass; the rules in engine.py decide pass/fail.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import mean
from typing import List, Optional, Tuple

from .data import GENERAL_GENERIC_WORDS, GENERIC_KEYWORDS


@dataclass
class Line:
    text: str
    conf: float = 1.0


@dataclass
class Hit:
    text: str
    start: int
    end: int
    conf: float


class LabelText:
    """All OCR lines joined with newlines, remembering per-line confidence."""

    def __init__(self, lines: List[Line]):
        self.lines = [Line(l.text.strip(), l.conf) for l in lines if l.text and l.text.strip()]
        self.text = "\n".join(l.text for l in self.lines)
        self._spans: List[Tuple[int, int, float]] = []
        pos = 0
        for l in self.lines:
            self._spans.append((pos, pos + len(l.text), l.conf))
            pos += len(l.text) + 1
        self.avg_conf = round(mean(l.conf for l in self.lines), 3) if self.lines else 0.0

    @classmethod
    def from_text(cls, text: str) -> "LabelText":
        return cls([Line(t) for t in text.splitlines()])

    def conf_at(self, start: int, end: int) -> float:
        cs = [c for s, e, c in self._spans if s < end and e > start]
        return round(mean(cs), 3) if cs else self.avg_conf

    def hit(self, start: int, end: int) -> Hit:
        end = min(end, len(self.text))
        return Hit(" ".join(self.text[start:end].split()), start, end, self.conf_at(start, end))


# ---------------------------------------------------------------- numbers / units
NUM = r"\d+(?:[.,]\d+)?"
UNITS = r"kilograms?|kgs?|grams?|gms?|g|millilit(?:re|er)s?|ml|lit(?:re|er)s?|ltrs?|l"

QTY_RE = re.compile(
    rf"(?:(?P<q>\b(?:approx\w*|about|nearly|minimum|min|maximum|max|around|roughly)\b|~)\.?\s*[:\-]?\s*)?"
    rf"(?P<num>{NUM})\s*(?P<unit>{UNITS})\b"
    rf"(?:\s*(?P<q2>\bapprox\w*|\bminimum\b|\bnearly\b|\bmin\b))?",
    re.I,
)
NET_KW_RE = re.compile(
    r"net\s*(?:wt|weight|qty|quantity|content|contents|vol|volume)\b|\bnet\b|\bn\.?\s*wt\b"
    r"|\bcontents?\b|\bcontains?\b|\bquantity\b|\bqty\b",
    re.I,
)
# Rule 13(4): units that may not be used for the declaration (rulebook example: dozen)
DOZEN_RE = re.compile(rf"(?P<num>{NUM})\s*(?P<unit>dozens?|doz)\b\.?", re.I)
COUNT_RE = re.compile(
    rf"\b(?:contains?|pack\s*of|count|qty|quantity)\b\s*[:.\-]?\s*(?P<num>\d+)\s*"
    r"(?P<unit>pcs?|pieces?|nos?|units?|n|sticks?|bags?|sheets?|tablets?|biscuits?|cookies?|capsules?)?\b",
    re.I,
)


def parse_num(s: str) -> float:
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", s):  # 1,000 -> thousands separator
        return float(s.replace(",", ""))
    return float(s.replace(",", "."))


def norm_unit(u: str) -> str:
    u = u.lower()
    if u.startswith("kilo") or u.startswith("kg"):
        return "kg"
    if u.startswith("milli") or u == "ml":
        return "ml"
    if u.startswith("lit") or u.startswith("ltr") or u == "l":
        return "l"
    return "g"


@dataclass
class NetQty:
    kind: str  # "std" | "count" | "dozen" | "none"
    hit: Optional[Hit] = None
    value: Optional[float] = None
    unit: Optional[str] = None  # g kg ml l count dozen
    base_value: Optional[float] = None  # in g / ml / count
    base_unit: Optional[str] = None  # g / ml / count
    qualifier: Optional[str] = None
    labelled: bool = False


def _std(lab: LabelText, m: re.Match, labelled: bool) -> NetQty:
    value = parse_num(m.group("num"))
    unit = norm_unit(m.group("unit"))
    base_value, base_unit = value, unit
    if unit == "kg":
        base_value, base_unit = value * 1000, "g"
    elif unit == "l":
        base_value, base_unit = value * 1000, "ml"
    q = m.group("q") or m.group("q2")
    return NetQty("std", lab.hit(m.start(), m.end()), value, unit, base_value, base_unit, q, labelled)


def find_net_quantity(lab: LabelText) -> NetQty:
    t = lab.text
    cands = []
    for m in QTY_RE.finditer(t):
        if re.search(r"per\s*$", t[max(0, m.start() - 8): m.start()], re.I):
            continue  # nutrition table: "per 100 g"
        labelled = bool(NET_KW_RE.search(t[max(0, m.start() - 45): m.start()]))
        cands.append((labelled, m))

    labelled_c = [m for lbl, m in cands if lbl]
    if labelled_c:
        return _std(lab, labelled_c[0], True)

    dz = DOZEN_RE.search(t)
    if dz:
        v = parse_num(dz.group("num"))
        return NetQty("dozen", lab.hit(dz.start(), dz.end()), v, "dozen", v, "dozen")

    ct = COUNT_RE.search(t)
    if ct:
        v = float(ct.group("num"))
        return NetQty("count", lab.hit(ct.start(), ct.end()), v, "count", v, "count", labelled=True)

    if cands:
        return _std(lab, cands[0][1], False)
    return NetQty("none")


# ---------------------------------------------------------------- MRP
AMT = r"\d+(?:[.,]\d{1,2})?"
PRICE_RE = re.compile(
    rf"(?:(?:\b(?:rs|inr)|₹)\.?\s*[:\-]?\s*(?P<a>{AMT})(?:\s*/-)?|(?P<b>{AMT})\s*(?:/-|₹|\brs\b))",
    re.I,
)
MRP_KW = r"\bm\.?\s*r\.?\s*p\.?|maximum\s*retail\s*price|retail\s*sale\s*price"
MRP_BARE_RE = re.compile(rf"(?:{MRP_KW})\W{{0,10}}(?P<c>{AMT})", re.I)
MRP_KW_RE = re.compile(MRP_KW, re.I)
# accepted wordings of the mandatory tax-inclusion phrase
TAX_RE = re.compile(r"inc(?:l(?:usive)?)?\.?\s*of\s*all\s*tax(?:es)?|all\s*tax(?:es)?\s*incl(?:uded|usive)?", re.I)


@dataclass
class Mrp:
    found: bool
    hit: Optional[Hit] = None
    amount: Optional[float] = None
    tax_phrase: bool = False
    has_mrp_keyword: bool = False


def find_mrp(lab: LabelText) -> Mrp:
    t = lab.text
    best = None
    for rx in (PRICE_RE, MRP_BARE_RE):
        m = rx.search(t)
        if m and (best is None or m.start() < best.start()):
            best = m
    if best is None:
        return Mrp(False)
    amt = next(g for g in (best.groupdict().get("a"), best.groupdict().get("b"), best.groupdict().get("c")) if g)
    ws, we = max(0, best.start() - 80), min(len(t), best.end() + 120)
    window = t[ws:we]
    tax = TAX_RE.search(window)
    kw_from = max(0, best.start() - 20)
    kw = MRP_KW_RE.search(t[kw_from: best.end()])
    start = kw_from + kw.start() if kw else best.start()
    end = ws + tax.end() if tax else best.end()
    return Mrp(True, lab.hit(start, end), parse_num(amt), bool(tax), bool(kw))


# ---------------------------------------------------------------- manufacturer
MFR_RE = re.compile(
    r"\b(?:(?:manufactured|mfd?\.?|mfg\.?|packed|pkd\.?|produced|made)\s*(?:and|&|/)?\s*"
    r"(?:(?:marketed|distributed|packed|packaged)\s*)?(?:by|at)\b|(?:manufacturer|packer|packaged\s*by)\s*[:\-])",
    re.I,
)
IMPORT_RE = re.compile(r"\bimported\s*by\b|\bimporter\s*[:\-]", re.I)
MARKET_RE = re.compile(r"\b(?:marketed|distributed|sold|marketing)\s*(?:and|&|/)?\s*(?:marketed|distributed)?\s*by\b", re.I)
PIN_RE = re.compile(r"\b[1-9]\d{2}\s?\d{3}\b")


@dataclass
class Manufacturer:
    has_manufacturer: bool
    has_importer: bool
    has_marketer: bool
    has_address: bool
    hit: Optional[Hit] = None


def find_manufacturer(lab: LabelText) -> Manufacturer:
    t = lab.text
    mfr, imp, mkt = MFR_RE.search(t), IMPORT_RE.search(t), MARKET_RE.search(t)
    anchor = mfr or imp or mkt
    if not anchor:
        return Manufacturer(False, False, False, False)
    ws = anchor.start()
    we = min(len(t), anchor.end() + 220)
    pin = PIN_RE.search(t[ws:we])
    hit = lab.hit(ws, ws + pin.end() if pin else min(len(t), anchor.end() + 120))
    return Manufacturer(bool(mfr), bool(imp), bool(mkt), bool(pin), hit)


# ---------------------------------------------------------------- generic name
@dataclass
class Generic:
    found: bool
    keyword: Optional[str] = None
    hit: Optional[Hit] = None


def find_generic_name(lab: LabelText, category: str) -> Generic:
    words = list(GENERIC_KEYWORDS.get(category, [])) + GENERAL_GENERIC_WORDS
    for w in words:
        m = re.search(rf"\b{re.escape(w)}(?:s|es)?\b", lab.text, re.I)
        if m:
            return Generic(True, w, lab.hit(m.start(), m.end()))
    return Generic(False)


# ---------------------------------------------------------------- manufacture date
MONTHS = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
DATE_ALPHA_RE = re.compile(rf"\b(?:{MONTHS})\b\.?[\s.,'\-/]*(?:20\d{{2}}|\d{{2}})(?!\d)", re.I)
DATE_NUM_RE = re.compile(
    r"(?<![\d.])(?:0?[1-9]|1[0-2])\s*[/\-]\s*(?:20\d{2}|\d{2})(?!\d)"
    r"|(?<![\d.])(?:0?[1-9]|1[0-2])\s*\.\s*20\d{2}(?!\d)"
)
EXPIRY_KW_RE = re.compile(r"(?:exp\w*|best\s*before|use\s*(?:by|before))\W{0,12}$", re.I)
MFG_KW_RE = re.compile(
    r"(?:mfg|mfd|manufactur\w*|pkd|pack\w*|month\s*(?:&|and)\s*year)\b(?:\W|date|dt|of|on)*$", re.I
)


@dataclass
class MfgDate:
    found: bool
    hit: Optional[Hit] = None
    near_keyword: bool = False
    only_expiry: bool = False


def find_mfg_date(lab: LabelText) -> MfgDate:
    t = lab.text
    cands = []
    for rx in (DATE_ALPHA_RE, DATE_NUM_RE):
        for m in rx.finditer(t):
            before = t[max(0, m.start() - 28): m.start()]
            cands.append((m, bool(EXPIRY_KW_RE.search(before)), bool(MFG_KW_RE.search(before))))
    good = sorted((c for c in cands if not c[1]), key=lambda c: (not c[2], c[0].start()))
    if good:
        m, _, kw = good[0]
        return MfgDate(True, lab.hit(m.start(), m.end()), kw)
    return MfgDate(False, only_expiry=bool(cands))


# ---------------------------------------------------------------- dimensions
_DU = r"(?:cm|mm|m|inches|inch|in|ft|feet)"
DIM_RE = re.compile(rf"\d+(?:\.\d+)?\s*{_DU}?\s*[x×*]\s*\d+(?:\.\d+)?\s*{_DU}\b", re.I)


def find_dimensions(lab: LabelText) -> Optional[Hit]:
    m = DIM_RE.search(lab.text)
    return lab.hit(m.start(), m.end()) if m else None


# ---------------------------------------------------------------- consumer care
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?91[\s\-]?)?(?:1800[\s\-]?\d{2,3}[\s\-]?\d{3,4}|1860[\s\-]?\d{3}[\s\-]?\d{4}"
    r"|[6-9]\d{4}[\s\-]?\d{5}|0\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4})(?!\d)"
)
CARE_KW_RE = re.compile(r"customer\s*care|consumer\s*(?:care|complaint)s?|complaints?|for\s*(?:queries|feedback)", re.I)


def find_consumer_care(lab: LabelText) -> Optional[Hit]:
    t = lab.text
    for rx in (PHONE_RE, EMAIL_RE):
        m = rx.search(t)
        if m:
            return lab.hit(m.start(), m.end())
    kw = CARE_KW_RE.search(t)
    if kw:
        window_end = min(len(t), kw.end() + 200)
        pin = PIN_RE.search(t[kw.start():window_end])
        if pin:  # a dedicated care address
            return lab.hit(kw.start(), kw.start() + pin.end())
    return None


# ---------------------------------------------------------------- language (Rule 9)
def script_counts(text: str) -> Tuple[int, int, int]:
    """(latin letters, devanagari letters, letters in any other script)"""
    lat = dev = oth = 0
    for ch in text:
        if not ch.isalpha():
            continue
        o = ord(ch)
        if o < 0x250:
            lat += 1
        elif 0x0900 <= o <= 0x097F:
            dev += 1
        else:
            oth += 1
    return lat, dev, oth
