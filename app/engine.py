"""Compliance rules engine (Legal Metrology (Packaged Commodities) Rules, 2011).

One check function per rule; every result carries a rule_reference.
Order of work (rulebook Part E): exemptions first, then Rule 9, then Rule 6, then Rule 5.
Rule 7 / Rule 8 are deliberately NOT implemented (team decision, see LIMITATIONS).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from . import config
from .data import (
    CATEGORY_KEYS,
    DATE_EXEMPT_CATEGORIES,
    DIMENSION_CATEGORIES,
    FULL_EXEMPT_CATEGORIES,
    LIMITATIONS,
    SIZE_TABLE_UNIT,
    is_standard_size,
)
from .extract import (
    LabelText,
    Line,
    NetQty,
    find_consumer_care,
    find_dimensions,
    find_generic_name,
    find_manufacturer,
    find_mfg_date,
    find_mrp,
    find_net_quantity,
    script_counts,
)
from .models import FieldResult, ScanResult

REF = {
    "legibility": "Rule 9",
    "language": "Rule 9",
    "manufacturer": "Rule 6(1)(a)",
    "generic_name": "Rule 6(1)(b)",
    "net_quantity": "Rule 6(1)(c)",
    "mfg_date": "Rule 6(1)(d)",
    "mrp": "Rule 6(1)(e)",
    "dimensions": "Rule 6(1)(f)",
    "consumer_care": "Rule 6(2)",
    "pack_size": "Rule 5 / Second Schedule",
}
FIELD_ORDER = [
    "legibility", "language", "manufacturer", "generic_name", "net_quantity",
    "mfg_date", "mrp", "dimensions", "consumer_care", "pack_size",
]
MIN_READABLE_LETTERS = 15  # Latin + Devanagari letters needed to call the label readable


@dataclass
class Ctx:
    lab: LabelText
    category: str
    pack_type: Optional[str]
    qty: NetQty
    from_ocr: bool


# ------------------------------------------------------------------ helpers
def _res(field, status, code=None, hit=None, detail=None, sub_case=None, ref=None) -> FieldResult:
    return FieldResult(
        field=field,
        status=status,
        violation_code=code,
        detected_text=hit.text if hit else None,
        rule_reference=ref or REF[field],
        detail=detail,
        sub_case=sub_case,
        confidence=hit.conf if hit else None,
    )


def _fin(r: FieldResult, ctx: Ctx) -> FieldResult:
    """If we found the text but OCR was unsure about it, send to human review."""
    if ctx.from_ocr and r.confidence is not None and r.confidence < config.MIN_FIELD_CONF \
            and r.status in ("PASS", "FAIL"):
        was = r.status + (f"/{r.violation_code}" if r.violation_code else "")
        r.detail = f"OCR confidence {r.confidence:.2f} is too low to trust this (would have been {was}). " + (r.detail or "")
        r.status, r.violation_code = "REVIEW", "LOW_CONFIDENCE"
    return r


def _absent(ctx: Ctx, field: str, detail: str, sub_case: str = None) -> FieldResult:
    if ctx.from_ocr and ctx.lab.avg_conf < config.MIN_OVERALL_CONF:
        return FieldResult(
            field=field, status="REVIEW", violation_code="LOW_CONFIDENCE", rule_reference=REF[field],
            detail=f"Not found, but overall OCR confidence is low ({ctx.lab.avg_conf:.2f}), so the text may "
                   f"simply not have been read. {detail}",
            sub_case=sub_case, confidence=ctx.lab.avg_conf,
        )
    return FieldResult(field=field, status="FAIL", violation_code="MISSING", rule_reference=REF[field],
                       detail=detail, sub_case=sub_case)


def _na(field, detail) -> FieldResult:
    return FieldResult(field=field, status="NOT_APPLICABLE", rule_reference=REF[field], detail=detail)


def _exempt(field, detail) -> FieldResult:
    return FieldResult(field=field, status="EXEMPT", rule_reference="Rule 26", detail=detail)


# ------------------------------------------------------------------ Rule 9
def check_legibility(ctx: Ctx) -> FieldResult:
    if not ctx.from_ocr:
        return _na("legibility", "Text input: there is no OCR confidence to judge legibility from.")
    c = ctx.lab.avg_conf
    if c < config.MIN_OVERALL_CONF:
        return FieldResult(field="legibility", status="REVIEW", violation_code="LOW_CONFIDENCE",
                           rule_reference=REF["legibility"], confidence=c,
                           detail=f"Average OCR confidence {c:.2f} is below {config.MIN_OVERALL_CONF}. "
                                  "Blur, glare or low contrast likely. Retake the photo.")
    return FieldResult(field="legibility", status="PASS", rule_reference=REF["legibility"], confidence=c,
                       detail=f"Average OCR confidence {c:.2f}.")


def check_language(ctx: Ctx) -> FieldResult:
    lat, dev, oth = script_counts(ctx.lab.text)
    if lat + dev >= MIN_READABLE_LETTERS:
        return _res("language", "PASS", detail=f"English letters: {lat}, Devanagari letters: {dev}.")
    if oth > 0:
        return _res("language", "FAIL", "LANGUAGE_ERROR",
                    detail="Text is in another script with no (or almost no) Hindi or English. "
                           "Declarations must be in Hindi (Devanagari) or English.")
    return FieldResult(field="language", status="REVIEW", violation_code="LOW_CONFIDENCE",
                       rule_reference=REF["language"],
                       detail="Too little readable text to judge the language.")


# ------------------------------------------------------------------ Rule 6
def check_manufacturer(ctx: Ctx) -> FieldResult:
    m = find_manufacturer(ctx.lab)
    if not (m.has_manufacturer or m.has_importer or m.has_marketer):
        return _absent(ctx, "manufacturer", "No manufacturer / packer / importer name found.")
    if not m.has_manufacturer and not m.has_importer:
        return _fin(_res("manufacturer", "FAIL", "FORMAT_ERROR", m.hit, sub_case="MARKETED_BY_ONLY",
                         detail="Only 'Marketed/Distributed by' is stated. That is not the same as the "
                                "manufacturer or packer."), ctx)
    if m.has_importer and not m.has_manufacturer:
        return _fin(_res("manufacturer", "FAIL", "FORMAT_ERROR", m.hit, sub_case="IMPORTER_ONLY",
                         detail="Importer is stated but the foreign manufacturer is not. Both are required."), ctx)
    if not m.has_address:
        return _fin(_res("manufacturer", "FAIL", "FORMAT_ERROR", m.hit, sub_case="ADDRESS_INCOMPLETE",
                         detail="Name found but no complete address (no PIN code found near it)."), ctx)
    return _fin(_res("manufacturer", "PASS", hit=m.hit), ctx)


def check_generic_name(ctx: Ctx) -> FieldResult:
    g = find_generic_name(ctx.lab, ctx.category)
    if g.found:
        return _fin(_res("generic_name", "PASS", hit=g.hit, detail=f"Matched '{g.keyword}'."), ctx)
    if ctx.category == "other":
        return FieldResult(
            field="generic_name", status="REVIEW", violation_code="LOW_CONFIDENCE",
            rule_reference=REF["generic_name"], sub_case="CATEGORY_UNKNOWN",
            detail="No common product word recognised and the category is 'other'. "
                   "A person should confirm the label states what the product is, apart from the brand.")
    return _absent(ctx, "generic_name",
                   "No plain-language product name found, only a brand name may be present.")


def check_net_quantity(ctx: Ctx) -> FieldResult:
    q = ctx.qty
    if q.kind == "none":
        return _absent(ctx, "net_quantity", "No net quantity found.")
    if q.kind == "dozen":
        return _fin(_res("net_quantity", "FAIL", "UNIT_ERROR", q.hit, ref="Rule 6(1)(c) / Rule 13(4)",
                         detail="Declared in 'dozen', which is not a permitted unit for net quantity."), ctx)
    if q.qualifier:
        return _fin(_res("net_quantity", "FAIL", "VAGUE_LANGUAGE", q.hit,
                         detail=f"Banned qualifier '{q.qualifier}'. Net quantity must be a definite number."), ctx)
    note = None if q.labelled else "No 'Net Wt / Net Qty' wording found next to this quantity."
    return _fin(_res("net_quantity", "PASS", hit=q.hit, detail=note), ctx)


def check_mfg_date(ctx: Ctx) -> FieldResult:
    if ctx.category in DATE_EXEMPT_CATEGORIES:
        return FieldResult(field="mfg_date", status="EXEMPT", rule_reference=REF["mfg_date"],
                           detail="Month/year of manufacture is not required for this category.")
    d = find_mfg_date(ctx.lab)
    if not d.found:
        if d.only_expiry:
            return _absent(ctx, "mfg_date", "Only an expiry / best-before date was found.",
                           sub_case="ONLY_EXPIRY_DATE")
        return _absent(ctx, "mfg_date", "No month + year of manufacture or packing found.")
    note = None if d.near_keyword else "Date found but no Mfg/Pkd wording next to it; it could be another date."
    return _fin(_res("mfg_date", "PASS", hit=d.hit, detail=note), ctx)


def check_mrp(ctx: Ctx) -> FieldResult:
    m = find_mrp(ctx.lab)
    if not m.found:
        return _absent(ctx, "mrp", "No retail price found.")
    if not m.tax_phrase:
        return _fin(_res("mrp", "FAIL", "FORMAT_ERROR", m.hit, sub_case="MISSING_TAX_PHRASE",
                         detail="Price is present but 'inclusive of all taxes' is not stated next to it."), ctx)
    return _fin(_res("mrp", "PASS", hit=m.hit), ctx)


def check_dimensions(ctx: Ctx) -> FieldResult:
    if ctx.category not in DIMENSION_CATEGORIES:
        return _na("dimensions", "Dimensions are only required for size-dependent goods (bedsheets, towels).")
    h = find_dimensions(ctx.lab)
    if not h:
        return _absent(ctx, "dimensions", "No dimensions (e.g. 90 cm x 180 cm) found.")
    return _fin(_res("dimensions", "PASS", hit=h), ctx)


def check_consumer_care(ctx: Ctx) -> FieldResult:
    h = find_consumer_care(ctx.lab)
    if not h:
        return _absent(ctx, "consumer_care", "No phone number, email or care address found.")
    return _fin(_res("consumer_care", "PASS", hit=h), ctx)


# ------------------------------------------------------------------ Rule 5


def check_pack_size(ctx: Ctx) -> FieldResult:
    import re

    cat, q = ctx.category, ctx.qty
    if cat not in SIZE_TABLE_UNIT:
        return _na("pack_size", "No standard pack size table for this category.")
    if q.kind != "std" or q.base_value is None:
        return _na("pack_size", "No usable net quantity to compare against the standard sizes.")
    if q.base_unit != SIZE_TABLE_UNIT[cat]:
        return _na("pack_size", f"Quantity is in {q.base_unit}, table is in {SIZE_TABLE_UNIT[cat]}.")
    ok, note = is_standard_size(cat, q.base_value, ctx.pack_type)
    if ok:
        return _res("pack_size", "PASS", hit=q.hit, detail=note)
    disclaimer = re.search(r"non[\s\-]*standard", ctx.lab.text, re.I)
    if disclaimer:
        return _res("pack_size", "PASS", hit=q.hit, detail="Non-standard size, but the disclaimer is present.")
    return _fin(_res("pack_size", "FAIL", "NONSTANDARD_PACK", q.hit,
                     detail=("Not a standard size for this category and no 'Non-standard size' disclaimer found. "
                             + (note or ""))), ctx)


CHECKS = {
    "legibility": check_legibility, "language": check_language, "manufacturer": check_manufacturer,
    "generic_name": check_generic_name, "net_quantity": check_net_quantity, "mfg_date": check_mfg_date,
    "mrp": check_mrp, "dimensions": check_dimensions, "consumer_care": check_consumer_care,
    "pack_size": check_pack_size,
}


# ------------------------------------------------------------------ Rule 26
def exemption_level(category: str, qty: NetQty) -> Tuple[Optional[str], Optional[str]]:
    """Returns ('FULL'|'REDUCED'|None, reason)."""
    if category in FULL_EXEMPT_CATEGORIES:
        return "FULL", FULL_EXEMPT_CATEGORIES[category]
    if qty.kind == "std" and qty.base_value is not None and qty.base_unit in ("g", "ml"):
        v, u = qty.base_value, qty.base_unit
        if v <= 10:
            return "FULL", f"Net quantity {v:g}{u} is 10{u} or less (very small package)"
        if v <= 20:
            return "REDUCED", f"Net quantity {v:g}{u} is between 10 and 20{u} (only MRP and net quantity are required)"
        if category == "agri_produce" and u == "g" and v > 50000:
            return "FULL", "Agricultural produce package above 50 kg"
    return None, None


# ------------------------------------------------------------------ main entry
def analyze(
    lines: List[Line],
    category: str = "other",
    pack_type: Optional[str] = None,
    from_ocr: bool = False,
) -> ScanResult:
    if category not in CATEGORY_KEYS:
        raise ValueError(f"Unknown category '{category}'")
    lab = LabelText(lines)
    ctx = Ctx(lab, category, pack_type, find_net_quantity(lab), from_ocr)

    level, reason = exemption_level(category, ctx.qty)
    results: List[FieldResult] = []
    for name in FIELD_ORDER:
        if level == "FULL":
            results.append(_exempt(name, reason))
        elif level == "REDUCED" and name not in ("net_quantity", "mrp", "language", "legibility"):
            results.append(_exempt(name, reason))
        else:
            results.append(CHECKS[name](ctx))

    summary = {s: sum(1 for r in results if r.status == s)
               for s in ("PASS", "FAIL", "REVIEW", "NOT_APPLICABLE", "EXEMPT")}
    if level == "FULL":
        verdict = "EXEMPT"
    elif summary["FAIL"]:
        verdict = "NON_COMPLIANT"
    elif summary["REVIEW"]:
        verdict = "NEEDS_REVIEW"
    else:
        verdict = "COMPLIANT"

    return ScanResult(
        input_mode="image" if from_ocr else "text",
        category=category,
        pack_type=pack_type,
        verdict=verdict,
        summary=summary,
        exemption={"level": level, "reason": reason} if level else None,
        fields=results,
        limitations=LIMITATIONS,
        raw_text=lab.text,
        avg_ocr_confidence=lab.avg_conf if from_ocr else None,
    )


def analyze_text(text: str, category: str = "other", pack_type: Optional[str] = None) -> ScanResult:
    return analyze(LabelText.from_text(text).lines, category, pack_type, from_ocr=False)
