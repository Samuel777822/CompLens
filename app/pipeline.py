"""Photo(s) in, compliance report out.

    decode -> [orientation fix] -> OCR pass 1 -> report -> (clean? stop) -> OCR pass 2 -> ... -> best report

Why several passes: one OCR run can miss a field that a different clean-up or reader would catch
(coloured stickers, tiny print, digits read as Devanagari). Each pass is analysed in two layouts
(row order / column order) and the best report wins. A field is only reported MISSING when every
pass agreed it was not there.

Several photos (front / back / spine) are read separately, then their text is checked as one label.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import config
from .engine import analyze
from .extract import Line
from .models import ScanResult
from .ocr import OcrUnavailable, read_views
from .preprocess import quality_warnings, rotate, variants

log = logging.getLogger("complens.pipeline")

OcrFn = Callable[[np.ndarray, Optional[Sequence[str]]], Dict[str, List[Line]]]
CONTENT_FIELDS = {"manufacturer", "generic_name", "net_quantity", "mfg_date", "mrp", "dimensions", "consumer_care"}


class ScanError(Exception):
    """The photo could be decoded but nothing usable came out of OCR."""


@dataclass
class Attempt:
    label: str
    lines: List[Line]
    result: ScanResult
    found: int
    score: tuple


def _score(res: ScanResult) -> Tuple[int, int, int, float]:
    # "found" = content fields where the checker actually located text. Counting that (rather than
    # fewer FAILs) stops a garbage read from winning just because low confidence turns FAILs into REVIEWs.
    found = sum(1 for f in res.fields if f.field in CONTENT_FIELDS and f.detected_text)
    return (found, -res.summary.get("FAIL", 0), -res.summary.get("REVIEW", 0), res.avg_ocr_confidence or 0.0)


def _attempt(lines: List[Line], label: str, category: str, pack_type: Optional[str]) -> Optional[Attempt]:
    if not lines:
        return None
    res = analyze(lines, category, pack_type, from_ocr=True)
    sc = _score(res)
    return Attempt(label, lines, res, sc[0], sc)


def _readability(atts: List[Attempt]) -> float:
    """How much real text did these attempts read? (letters x confidence, best view)"""
    best = 0.0
    for a in atts:
        best = max(best, sum(sum(c.isalpha() for c in l.text) * l.conf for l in a.lines))
    return best


def _looks_unreadable(best: Optional[Attempt]) -> bool:
    if best is None:
        return True
    letters = sum(c.isalpha() for c in best.result.raw_text)
    return letters < 25 or (best.result.avg_ocr_confidence or 0) < 0.30


def _read_one(
    img: np.ndarray, category: str, pack_type: Optional[str], ocr: OcrFn
) -> Tuple[Attempt, List[str]]:
    notes: List[str] = []
    main = tuple(config.OCR_LANGS)
    extra = tuple(config.OCR_EXTRA_LANGS) or main
    plan = [main, main, extra][: config.OCR_MAX_PASSES]
    errors: List[str] = []

    def do_pass(arr: np.ndarray, langs: Sequence[str], tag: str) -> List[Attempt]:
        try:
            views = ocr(arr, langs)
        except OcrUnavailable:
            raise
        except Exception as e:  # noqa: BLE001 - OOM, torch errors, odd arrays: try the next pass instead
            log.exception("OCR pass %s failed", tag)
            errors.append(f"{tag}: {e}")
            return []
        out = []
        for vname, lines in views.items():
            a = _attempt(lines, f"{tag}/{'+'.join(langs)}/{vname}", category, pack_type)
            if a:
                out.append(a)
        return out

    gen = variants(img)
    name, arr = next(gen)
    atts = do_pass(arr, plan[0], name)

    # Photo taken sideways / upside down without EXIF data: nothing readable comes out. Try the other angles.
    if config.OCR_TRY_ROTATIONS and _looks_unreadable(max(atts, key=lambda a: a.score) if atts else None):
        best_k, best_atts, best_read = 0, atts, _readability(atts)
        for k in (1, 3, 2):
            ra = do_pass(rotate(arr, k), plan[0], f"{name}+rot{k * 90}")
            r = _readability(ra)
            if r > best_read * 1.5 + 10:
                best_k, best_atts, best_read = k, ra, r
        if best_k:
            notes.append(f"The photo was sideways or upside down; it was rotated {best_k * 90} degrees to read it.")
            atts = best_atts
            gen = variants(rotate(img, best_k))
            next(gen)  # first variant already read in this orientation

    best = max(atts, key=lambda a: a.score) if atts else None
    history = [best.found] if best else []
    for langs in plan[1:]:
        if best and best.result.verdict in ("COMPLIANT", "EXEMPT"):
            break
        # plateau: the last pass added nothing and the text is readable, so more passes will not help
        if len(history) >= 2 and history[-1] <= history[-2] and (best.result.avg_ocr_confidence or 0) >= config.MIN_OVERALL_CONF:
            break
        try:
            name, arr = next(gen)
        except StopIteration:
            break
        atts += do_pass(arr, langs, name)
        if atts:
            best = max(atts, key=lambda a: a.score)
            history.append(best.found)

    if best is None:
        if errors:
            raise ScanError("The OCR engine failed on this photo: " + errors[-1])
        raise ScanError("No text could be read from this image. Try a clearer, closer photo with the label flat and in focus.")
    log.info("best OCR attempt: %s score=%s (of %d attempts)", best.label, best.score, len(atts))
    return best, notes


def scan_images(
    images: List[np.ndarray], category: str = "other", pack_type: Optional[str] = None, ocr: OcrFn = read_views
) -> ScanResult:
    if not images:
        raise ScanError("No image was provided.")
    warnings: List[str] = []
    bests: List[Attempt] = []
    for i, img in enumerate(images, 1):
        tag = f"Photo {i}" if len(images) > 1 else ""
        try:
            warnings += quality_warnings(img, tag)
        except Exception:  # noqa: BLE001 - quality hints are optional
            log.exception("quality check failed")
        try:
            best, notes = _read_one(img, category, pack_type, ocr)
        except ScanError as e:
            if len(images) == 1:
                raise
            warnings.append(f"Photo {i}: {e}")
            continue
        bests.append(best)
        warnings += [f"{tag}: {n}" if tag else n for n in notes]

    if not bests:
        raise ScanError("No text could be read from any of the photos. Try clearer, closer photos.")
    if len(bests) == 1:
        result = bests[0].result
    else:
        merged: List[Line] = [l for b in bests for l in b.lines]
        result = analyze(merged, category, pack_type, from_ocr=True)
    result.images_used = len(bests)

    missing = [f.field for f in result.fields if f.status == "FAIL" and f.violation_code == "MISSING"]
    if missing and result.verdict != "EXEMPT" and len(bests) == 1:
        warnings.append(
            "Some declarations were not found in this photo. If they are printed on another part of the pack "
            "(back cover, spine, flap, base), add a photo of that part: you can upload several photos for one check."
        )
    if len(result.raw_text.splitlines()) < 3 and result.verdict != "EXEMPT":
        warnings.append("Very little text was read. The label may be too small in the frame: move closer.")
    result.warnings = list(dict.fromkeys(warnings))  # de-duplicate, keep order
    return result
