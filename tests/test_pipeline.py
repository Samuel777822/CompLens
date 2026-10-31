import numpy as np
import pytest

from app.extract import Line
from app.pipeline import ScanError, scan_images

IMG = np.full((300, 900, 3), 150, np.uint8)
GOOD = [Line("Cream Biscuits", .9), Line("Net Wt. 150 g", .9), Line("MRP Rs. 30.00 (Inclusive of all taxes)", .9),
        Line("Mfg: 03/2026", .9), Line("Manufactured by: Sunrise Foods Pvt. Ltd., Plot 14, Industrial Area, Nashik - 422010", .9),
        Line("Call 1800-123-4567", .9)]


def ocr_returning(rows, columns=None):
    return lambda arr, langs: {"rows": rows, "columns": columns if columns is not None else rows}


def test_clean_first_pass_stops_early():
    calls = []

    def ocr(arr, langs):
        calls.append(1)
        return {"rows": GOOD, "columns": GOOD}
    r = scan_images([IMG], "biscuits", None, ocr=ocr)
    assert r.verdict == "COMPLIANT" and len(calls) == 1


def test_better_layout_view_wins():
    scrambled = [Line("Cream Biscuits", .9), Line("Net Wt.", .9)]
    r = scan_images([IMG], "biscuits", None, ocr=ocr_returning(scrambled, GOOD))
    assert r.verdict == "COMPLIANT"


def test_later_pass_can_rescue_a_bad_first_pass():
    state = {"n": 0}

    def ocr(arr, langs):
        state["n"] += 1
        return {"rows": [Line("xx", .2)], "columns": [Line("xx", .2)]} if state["n"] == 1 else {"rows": GOOD, "columns": GOOD}
    assert scan_images([IMG], "biscuits", None, ocr=ocr).verdict == "COMPLIANT"


def test_ocr_crash_in_one_pass_does_not_kill_the_scan():
    state = {"n": 0}

    def ocr(arr, langs):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("CUDA out of memory")
        return {"rows": GOOD, "columns": GOOD}
    assert scan_images([IMG], "biscuits", None, ocr=ocr).verdict == "COMPLIANT"


def test_all_passes_failing_raises_scan_error():
    def ocr(arr, langs):
        raise RuntimeError("boom")
    with pytest.raises(ScanError):
        scan_images([IMG], "biscuits", None, ocr=ocr)


def test_no_text_raises_scan_error():
    with pytest.raises(ScanError):
        scan_images([IMG], "biscuits", None, ocr=ocr_returning([]))


def test_two_photos_are_checked_as_one_label():
    front = [Line("Long Note Book", .9), Line("140 Pages", .9), Line("MRP Rs 60 (Incl. of all Taxes)", .9)]
    back = [Line("Mfg: 06/2026", .9), Line("Printed by Bhaskar Book Tech, Plot 4, Industrial Area, Harohalli - 562112", .9),
            Line("Help line 080-29761413", .9)]
    tall = np.full((450, 900, 3), 150, np.uint8)  # different aspect ratio so the fake OCR can tell the photos apart

    def ocr(arr, langs):
        lines = back if arr.shape[0] / arr.shape[1] > 0.4 else front
        return {"rows": lines, "columns": lines}
    r = scan_images([IMG, tall], "auto", None, ocr=ocr)
    assert r.images_used == 2
    f = {x.field: x for x in r.fields}
    assert f["mfg_date"].status == "PASS" and f["net_quantity"].status == "PASS" and f["manufacturer"].status == "PASS"


def test_sideways_photo_is_rotated():
    def ocr(arr, langs):
        upright = arr.shape[0] != 900 and arr.shape[1] > arr.shape[0] * 0 and arr.shape[0] > arr.shape[1]
        return {"rows": GOOD, "columns": GOOD} if upright else {"rows": [Line("..", .1)], "columns": [Line("..", .1)]}
    r = scan_images([IMG], "biscuits", None, ocr=ocr)
    assert any("rotated" in w for w in r.warnings)
