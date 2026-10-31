"""Field extraction: turns OCR lines into structured findings (regex based).

Everything here works on plain text, so it can be unit tested without images.
Each finder returns a small dataclass; the rules in engine.py decide pass/fail.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from statistics import mean
from typing import List, Optional, Tuple

from .data import GENERAL_GENERIC_WORDS, GENERIC_KEYWORDS, WEAK_GENERIC_WORDS


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


# ---------------------------------------------------------------- OCR text clean-up
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u200e\u200f\u2060\ufeff\u00ad"), None)
_EMAIL_TLD_RE = re.compile(r"(@[\w\-]+(?:\.[\w\-]+)*)[\s,;]+(com|in|org|net|co\.in|co|gov|edu)\b", re.I)
_O_AS_ZERO_RE = re.compile(r"(?<=\d)[Oo](?![A-Za-z])")


def normalize_text(s: str) -> str:
    """Make OCR output regex-friendly.

    * EasyOCR with the Hindi model reads digits as Devanagari / Bengali / Gujarati ... numerals
      (e.g. a price of 60.00 comes back as a string of Devanagari digits). Map every Unicode
      decimal digit to ASCII so the number regexes work.
    * NFKC folds full-width forms, ligatures, no-break spaces and the rupee-letter sign.
    * "yahoo in" -> "yahoo.in" (OCR drops dots), "6o" -> "60" (letter O after a digit).
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s).translate(_ZERO_WIDTH)
    s = "".join(
        str(unicodedata.decimal(ch)) if (ch.isdecimal() and not ch.isascii()) else ch for ch in s
    )
    s = s.replace("\t", " ").replace("\r", " ")
    s = _O_AS_ZERO_RE.sub("0", s)
    s = _EMAIL_TLD_RE.sub(lambda m: f"{m.group(1)}.{m.group(2)}", s)
    return s


class LabelText:
    """All OCR lines joined with newlines, remembering per-line confidence."""

    def __init__(self, lines: List[Line]):
        cleaned = [Line(normalize_text(l.text or "").strip(), l.conf) for l in lines]
        self.lines = [l for l in cleaned if l.text]
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
# length / area declarations (fabric, tiles, wires ...): "Net Qty: 5 m", "Length 2.5 metres", "1.2 sq.m"
_LEN_U = r"(?:millimet(?:re|er)s?|centimet(?:re|er)s?|met(?:re|er)s?|mtrs?|mm|cms?|m)"
AREA_RE = re.compile(rf"(?P<num>{NUM})\s*(?P<unit>sq\.?\s*(?:m|mt|mtr|metres?|meters?|cm|ft|feet)\b|sqm\b|square\s*(?:met(?:re|er)s?|feet|cm)\b)", re.I)
LEN_RE = re.compile(rf"(?P<num>{NUM})\s*(?P<unit>{_LEN_U})\b(?!\s*[x×*]|\s*\d)", re.I)
# Rule 13(4): units that may not be used for the declaration (rulebook example: dozen)
DOZEN_RE = re.compile(rf"(?P<num>{NUM})\s*(?P<unit>dozens?|doz)\b\.?", re.I)
COUNT_RE = re.compile(
    rf"\b(?:contains?|pack\s*of|count|qty|quantity)\b\s*[:.\-]?\s*(?P<num>\d+)\s*"
    r"(?P<unit>pcs?|pieces?|nos?|units?|n|sticks?|bags?|sheets?|tablets?|biscuits?|cookies?|capsules?)?\b",
    re.I,
)


# "140 Pages", "200 sheets", "12 pcs": a count with its own unit word, no "Net Qty" wording needed.
COUNT_UNIT_WORDS = r"pages?|pgs?|leaves|leaf|sheets?|pcs?|pieces?|nos|units?|sticks?|pairs?|sets?|rolls?"
COUNT_AFTER_RE = re.compile(rf"(?<![\d.,/\-])(?P<num>\d{{1,5}})\s*(?P<unit>{COUNT_UNIT_WORDS})\b", re.I)
# "Pages: 140", "No. of pages - 200"
COUNT_BEFORE_RE = re.compile(
    r"\b(?:no\.?\s*of\s*)?(?P<unit>pages?|pgs?|leaves|sheets?)\s*[:=\-]\s*(?P<num>\d{1,5})(?![\d.,]|\s*(?:cm|mm|gsm|x))", re.I
)
_PRE_QUAL_RE = re.compile(r"(?:approx\w*|about|nearly|minimum|min|maximum|max|around|roughly|~)\W{0,3}$", re.I)


def _pre_qualifier(t: str, start: int) -> Optional[str]:
    m = _PRE_QUAL_RE.search(t[max(0, start - 14): start])
    return m.group(0).strip(" .:-") if m else None


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


def _len_area(lab: LabelText, measure: Optional[str]) -> Optional[NetQty]:
    """Length / area quantity. Accepted only next to 'Net Qty/Length' wording, or when the product is
    known to be sold by length / area, so '30 x 18 cm' sizes and stray centimetres are never taken."""
    t = lab.text
    want = measure in ("length", "area")
    for rx, base in ((AREA_RE, "m2"), (LEN_RE, "m")):
        for m in rx.finditer(t):
            labelled = bool(NET_KW_RE.search(t[max(0, m.start() - 45): m.start()])) or bool(
                re.search(r"\b(?:length|area)\s*[:\-]?\s*$", t[max(0, m.start() - 12): m.start()], re.I))
            if not (labelled or want):
                continue
            v = parse_num(m.group("num"))
            u = m.group("unit").lower().replace(" ", "")
            if base == "m2":
                f = 1e-4 if u.endswith("cm") else (0.092903 if "f" in u else 1.0)
                return NetQty("std", lab.hit(m.start(), m.end()), v, "m2", v * f, "m2", _pre_qualifier(t, m.start()), labelled)
            f = 0.001 if u.startswith("mm") or u.startswith("milli") else (0.01 if u.startswith("c") else 1.0)
            return NetQty("std", lab.hit(m.start(), m.end()), v, "m", v * f, "m", _pre_qualifier(t, m.start()), labelled)
    return None


def find_net_quantity(lab: LabelText, measure: Optional[str] = None) -> NetQty:
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

    la = _len_area(lab, measure)
    if la and la.labelled:
        return la

    dz = DOZEN_RE.search(t)
    if dz:
        v = parse_num(dz.group("num"))
        return NetQty("dozen", lab.hit(dz.start(), dz.end()), v, "dozen", v, "dozen",
                      _pre_qualifier(t, dz.start()))

    ct = COUNT_RE.search(t) or COUNT_AFTER_RE.search(t) or COUNT_BEFORE_RE.search(t)
    if ct:
        v = float(ct.group("num"))
        return NetQty("count", lab.hit(ct.start(), ct.end()), v, "count", v, "count",
                      _pre_qualifier(t, ct.start()), labelled=True)

    if measure in ("length", "area") and la:
        return la
    if cands:
        return _std(lab, cands[0][1], False)
    return NetQty("none")


# ---------------------------------------------------------------- MRP
# OCR often misreads digits as look-alike letters (60 -> G0, 100 -> lOO); accept them, then validate.
_AMT_CH = r"[\dOoIlSBG]"
AMT = rf"(?=[\dOoIlSBG.,]*\d){_AMT_CH}{{1,7}}(?:[.,]{_AMT_CH}{{1,2}})?(?![A-Za-z])"  # token needs a real digit
_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "B": "8", "G": "6"})
CUR = r"(?:\b(?:rs|inr)\b|\brupees?\b|₹|₨)"
PRICE_RE = re.compile(
    rf"(?:{CUR}\.?\s*[:\-]?\s*(?P<a>{AMT})(?:\s*/-)?|(?P<b>{AMT})\s*(?:/-|₹|\brs\b))",
    re.I,
)
MRP_KW = (r"\bm\.?\s*r\.?\s*p\b\.?|maximum\s*retail\s*price|max\.?\s*retail\s*price"
          r"|retail\s*(?:sale\s*)?price|\bprice\b")
# keyword, then up to 12 junk characters (":", "₹", a misread rupee sign, ...), then the amount
MRP_BARE_RE = re.compile(rf"(?:{MRP_KW})[^\d\n]{{0,12}}?(?P<c>{AMT})", re.I)
# keyword, then the tax wording, then the amount:  "MRP (Incl. of all taxes) Rs. 60"
MRP_TAXFIRST_RE = re.compile(rf"(?:{MRP_KW})\s*\(?\s*inc[^\d\n]{{0,40}}?(?P<c>{AMT})", re.I)
MRP_KW_RE = re.compile(MRP_KW, re.I)
# accepted wordings of the mandatory tax-inclusion phrase ("all" is optional, see tax_has_all)
TAX_RE = re.compile(
    r"inc(?:l(?:uding|usive|uded)?)?\.?\s*(?:of\s*)?(?:all\s*)?(?:local\s*)?(?:taxes|tax|gst)\b"
    r"|(?:all\s*)?(?:taxes|gst)\s*(?:are\s*)?incl(?:uded|usive)?",
    re.I,
)


@dataclass
class Mrp:
    found: bool
    hit: Optional[Hit] = None
    amount: Optional[float] = None
    tax_phrase: bool = False
    has_mrp_keyword: bool = False
    tax_has_all: bool = False
    keyword_without_amount: bool = False


def parse_amount(raw: Optional[str]) -> Optional[float]:
    """'6O.OO' -> 60.0. Needs at least one real digit so plain words never pass as prices."""
    if not raw or not any(c.isdigit() for c in raw):
        return None
    try:
        return parse_num(raw.translate(_DIGIT_FIX))
    except ValueError:
        return None


def find_mrp(lab: LabelText) -> Mrp:
    t = lab.text
    cands = []  # (priority, start, match, amount); keyword-anchored matches beat bare "Rs 10"
    for pri, rx in ((0, MRP_BARE_RE), (0, MRP_TAXFIRST_RE), (1, PRICE_RE)):
        for m in rx.finditer(t):
            g = m.groupdict()
            amt = parse_amount(g.get("a") or g.get("b") or g.get("c"))
            if amt is not None:
                cands.append((pri, m.start(), m, amt))
    if not cands:
        return Mrp(False, keyword_without_amount=bool(MRP_KW_RE.search(t)))
    _, _, best, amount = min(cands, key=lambda c: (c[0], c[1]))
    ws, we = max(0, best.start() - 80), min(len(t), best.end() + 120)
    window = t[ws:we]
    tax = TAX_RE.search(window)
    kw_from = max(0, best.start() - 20)
    kw = MRP_KW_RE.search(t[kw_from: best.end()])
    start = kw_from + kw.start() if kw else best.start()
    end = best.end()
    if tax and 0 <= ws + tax.start() - best.end() <= 20:  # tax wording right after the price
        end = ws + tax.end()
    return Mrp(True, lab.hit(start, end), amount, bool(tax), bool(kw),
               bool(tax and re.search(r"\ball\b", tax.group(0), re.I)))


# ---------------------------------------------------------------- manufacturer
MFR_RE = re.compile(
    r"\b(?:(?:manufactured|mfd?\.?|mfg\.?|packed|pkd\.?|produced|made)\s*(?:and|&|/)?\s*"
    r"(?:(?:marketed|distributed|packed|packaged)\s*)?(?:by|at)\b|(?:manufacturer|packer|mfr|packaged\s*by)\s*[:\-])",
    re.I,
)
IMPORT_RE = re.compile(r"\bimported\s*by\b|\bimporter\s*[:\-]", re.I)
MARKET_RE = re.compile(r"\b(?:marketed|distributed|sold|marketing)\s*(?:and|&|/)?\s*(?:marketed|distributed)?\s*by\b", re.I)
PIN_RE = re.compile(r"\b[1-9]\d{2}\s?\d{3}\b")
# words that make a block of text look like a postal address
ADDR_RE = re.compile(
    r"\b(?:plot|door|flat|floor|bldg|building|block|sector|phase|road|rd|street|lane|cross|main|layout|nagar"
    r"|colony|industrial|industries|estate|village|taluk|dist|district|post|near|opp|behind|pvt|ltd|limited"
    r"|private|enterprises|works|factory|unit|survey|kiadb|midc|gidc|sidco|complex|tower|house|area|city|state)\b"
    r"|\bno\.",
    re.I,
)


def _pin_ok(t: str, m: re.Match) -> bool:
    """A PIN code is not part of a longer digit run (barcode groups, phone numbers)."""
    if re.match(r"[ \-]?\d", t[m.end(): m.end() + 2]):
        return False
    return not re.search(r"\d[ \-]$", t[max(0, m.start() - 2): m.start()])


def find_pin(text: str, start: int = 0, end: Optional[int] = None) -> Optional[re.Match]:
    for m in PIN_RE.finditer(text, start, len(text) if end is None else end):
        if _pin_ok(text, m):
            return m
    return None


@dataclass
class Manufacturer:
    has_manufacturer: bool
    has_importer: bool
    has_marketer: bool
    has_address: bool
    hit: Optional[Hit] = None
    implicit: bool = False  # name + address printed with no "Manufactured by" wording


def _implicit_address(lab: LabelText) -> Optional[Hit]:
    """Many packs (notebooks, stationery) print logo + company name + address with no 'Mfd. by'.
    Rule 6(1)(a) asks for the name and address, not for the words, so accept an address block
    (>= 2 address words followed by a valid PIN code)."""
    t = lab.text
    for m in PIN_RE.finditer(t):
        if not _pin_ok(t, m):
            continue
        window = t[max(0, m.start() - 220): m.start()]
        if len({w.lower() for w in ADDR_RE.findall(window)}) >= 2:
            line_start = t.rfind("\n", 0, m.start()) + 1
            for _ in range(3):  # include up to three lines above: the company name sits there
                if line_start == 0:
                    break
                line_start = t.rfind("\n", 0, line_start - 1) + 1
            return lab.hit(line_start, m.end())
    return None


def find_manufacturer(lab: LabelText) -> Manufacturer:
    t = lab.text
    mfr, imp, mkt = MFR_RE.search(t), IMPORT_RE.search(t), MARKET_RE.search(t)
    anchor = mfr or imp or mkt
    if not anchor:
        implicit = _implicit_address(lab)
        if implicit:
            return Manufacturer(False, False, False, True, implicit, implicit=True)
        return Manufacturer(False, False, False, False)
    ws = anchor.start()
    we = min(len(t), anchor.end() + 220)
    pin = find_pin(t, ws, we)
    hit = lab.hit(ws, pin.end() if pin else min(len(t), anchor.end() + 120))
    return Manufacturer(bool(mfr), bool(imp), bool(mkt), bool(pin), hit)


# ---------------------------------------------------------------- generic name
@dataclass
class Generic:
    found: bool
    keyword: Optional[str] = None
    hit: Optional[Hit] = None
    weak: bool = False  # only a hint such as "Pages" was seen, not a product name


def _word_re(w: str) -> re.Pattern:
    return re.compile(rf"\b{re.escape(w).replace(chr(92) + ' ', r'[\s\-]*')}(?:s|es)?\b", re.I)


def find_generic_name(lab: LabelText, category: str) -> Generic:
    words = list(GENERIC_KEYWORDS.get(category, [])) + GENERAL_GENERIC_WORDS
    for w in words:
        m = _word_re(w).search(lab.text)
        if m:
            return Generic(True, w, lab.hit(m.start(), m.end()))
    for w in WEAK_GENERIC_WORDS:
        m = _word_re(w).search(lab.text)
        if m:
            return Generic(False, w, lab.hit(m.start(), m.end()), weak=True)
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
# 15.07.2025 / 15-07-25 / 15/07/2025
DATE_FULL_RE = re.compile(
    r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])\s*[./\-]\s*(?:0?[1-9]|1[0-2])\s*[./\-]\s*(?:20\d{2}|\d{2})(?!\d)"
)
# 2025-07 / 2025/07
DATE_ISO_RE = re.compile(r"(?<!\d)20\d{2}\s*[\-/.]\s*(?:0?[1-9]|1[0-2])(?![\d/.\-])")
# "Mfg 0725" / "Pkd: 072025" (only trusted when the keyword is right there)
DATE_COMPACT_RE = re.compile(
    r"(?:mfg|mfd|pkd|pack\w*|manufactur\w*)\b[\W]{0,12}?(?:date|dt|of|on)?\W{0,6}(?P<d>(?:0[1-9]|1[0-2])(?:20)?\d{2})(?!\d)", re.I
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
    for rx in (DATE_ALPHA_RE, DATE_NUM_RE, DATE_FULL_RE, DATE_ISO_RE):
        for m in rx.finditer(t):
            before = t[max(0, m.start() - 28): m.start()]
            cands.append((m, bool(EXPIRY_KW_RE.search(before)), bool(MFG_KW_RE.search(before))))
    for m in DATE_COMPACT_RE.finditer(t):
        before = t[max(0, m.start("d") - 28): m.start("d")]
        cands.append((m, bool(EXPIRY_KW_RE.search(before)), True))
    good = sorted((c for c in cands if not c[1]), key=lambda c: (not c[2], c[0].start()))
    if good:
        m, _, kw = good[0]
        return MfgDate(True, lab.hit(m.start(), m.end()), kw)
    return MfgDate(False, only_expiry=bool(cands))


# ---------------------------------------------------------------- dimensions
_DU = r"(?:cm|mm|m|inches|inch|in|ft|feet)"
DIM_RE = re.compile(rf"\d+(?:\.\d+)?\s*{_DU}?\s*[x×*]\s*\d+(?:\.\d+)?\s*{_DU}\b", re.I)


DIM_WORD_RE = re.compile(rf"\b(?:width|length|breadth|height|size|dimensions?)\s*[:\-]?\s*\d+(?:\.\d+)?\s*{_DU}\b", re.I)


def find_dimensions(lab: LabelText) -> Optional[Hit]:
    m = DIM_RE.search(lab.text) or DIM_WORD_RE.search(lab.text)
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
