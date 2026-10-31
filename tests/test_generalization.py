"""The checker must understand ANY product: what it is, and how its net quantity is declared."""
import pytest

from app.classify import infer_category
from app.engine import analyze_text
from app.extract import LabelText, find_manufacturer, find_mrp, find_net_quantity, normalize_text

NOTEBOOK = ("Bhaskar Book Tech\nPlot No. 267/16A, Kiadb Industrial Area,\n2nd Road, Ramanagar District,\n"
            "Harohalli - 562112\nE-mail: bhaskarbook@yahoo.in\nHelp line : 080-29761413\n"
            "140 Pages - MRP: Rs 60.00\n(Incl. of Taxes)\nSize 30x18 Cms\nMfg: Jun 2026\nLong Note Book")


def f(r, name):
    return next(x for x in r.fields if x.field == name)


def test_notebook_is_recognised_and_pages_are_the_net_quantity():
    r = analyze_text(NOTEBOOK, "auto")
    assert r.product["category"] == "notebook" and r.product["measure"] == "count"
    assert "Table II" in r.product["size_table"]
    assert f(r, "net_quantity").status == "PASS" and f(r, "net_quantity").detected_text.lower().startswith("140 pages")
    assert r.verdict == "COMPLIANT", [(x.field, x.status, x.detail) for x in r.fields if x.status != "PASS"]


def test_notebook_without_any_net_quantity_still_fails():
    r = analyze_text(NOTEBOOK.replace("140 Pages - ", ""), "notebook")
    assert f(r, "net_quantity").violation_code == "MISSING"


def test_approximate_page_count_is_vague():
    r = analyze_text(NOTEBOOK.replace("140 Pages", "approx 140 Pages"), "auto")
    assert f(r, "net_quantity").violation_code == "VAGUE_LANGUAGE"


@pytest.mark.parametrize("text,cat,measure", [
    ("Aqua Drinking Water\nNet Vol. 1 L", "other", "volume"),
    ("Sunrich Oil\nNet Qty: 910 ml", "other", "volume"),
    ("Cotton Shirting Fabric\nNet Qty: 2.5 m", "fabric", "length"),
    ("Floor Tiles\nNet Qty: 1.44 sq.m", "tiles", "area"),
    ("Camel Pencils\nContains 10 pcs", "other", "count"),
    ("Cream Biscuits\nNet Wt. 150 g", "biscuits", "weight"),
])
def test_any_product_gets_a_measure_and_a_passing_quantity(text, cat, measure):
    r = analyze_text(text + "\nMRP Rs 10 incl. of all taxes", "auto")
    assert r.product["category"] == cat and r.product["measure"] == measure
    assert f(r, "net_quantity").status == "PASS"


def test_unknown_product_measure_comes_from_the_unit():
    r = analyze_text("Mystery Thing\nNet Wt. 70 g\nMRP Rs 5 incl. of all taxes", "auto")
    assert r.product["category"] == "other" and r.product["measure"] == "weight"


def test_salt_in_chips_is_not_a_salt_pack():
    assert infer_category("Salt & Vinegar Chips") is None


def test_exemption_categories_are_never_guessed():
    assert infer_category("Hot Fast Food Burger") is None


def test_wrong_user_category_gets_a_warning():
    r = analyze_text("Cola Carbonated Drink\nNet Vol 300 ml", "tea")
    assert any("looks like" in w for w in r.warnings)


def test_rule7_is_noted_not_checked():
    r = analyze_text(NOTEBOOK, "auto")
    assert "skipped" in r.product["rule7_note"]
    assert not any("height" in (x.detail or "").lower() for x in r.fields)


# ---- the exact OCR text from the failing notebook photo
OCR_TEXT = ("Plot No. ২৬৭/১৬A ২৬৭/১৬B, Kiadb Industrial Area, ২৪০ Pages MRP: ₹ ৬0.0০\n"
            "২nd Road, ২nd Phase, Ramanagar District, (Incl. of Taxes)\n"
            "Harohalli - 562112, (Inclusive of both end sheets)\n"
            "BDOK BHASKAR TECH Help line : 080-29761413 Email: bhaskarbook@yahoo in Size ৩0x18Cms 0 700721 644803")


def test_real_ocr_text_from_the_notebook_photo():
    r = analyze_text(OCR_TEXT, "auto")
    assert r.product["category"] == "notebook"
    assert f(r, "net_quantity").status == "PASS"
    assert f(r, "mrp").status == "PASS" and f(r, "manufacturer").status == "PASS"
    assert f(r, "consumer_care").status == "PASS"
    assert f(r, "mfg_date").violation_code == "MISSING"  # genuinely not on this strip


def test_devanagari_and_bengali_digits_become_ascii():
    assert normalize_text("₹ ६०.००, २४० ৩০") == "₹ 60.00, 240 30"
    assert normalize_text("mail@yahoo in") == "mail@yahoo.in"


@pytest.mark.parametrize("t", ["MRP: ₹ G0.0o (Incl. of Taxes)", "MRP: T 60.00 Incl. of Taxes", "M.R.P. : Rs.60/- incl. of taxes",
                               "MRP (Incl. of all taxes) Rs. 60.00"])
def test_mrp_survives_ocr_noise(t):
    m = find_mrp(LabelText.from_text(t))
    assert m.found and m.amount == 60.0 and m.tax_phrase


def test_manufacturer_by_address_block_only():
    m = find_manufacturer(LabelText.from_text("ACME Books\nPlot 4, Industrial Estate, Phase 2,\nHosur - 635109"))
    assert m.implicit and m.has_address


def test_barcode_digits_are_not_a_pin_code():
    m = find_manufacturer(LabelText.from_text("Size 30x18\n0 700721 644803"))
    assert not m.implicit and not m.has_address


@pytest.mark.parametrize("d", ["15.07.2026", "15/07/2026", "2026-07", "Jul-26", "Mfg 0726"])
def test_more_date_formats(d):
    r = analyze_text(f"Notebook 100 Pages\nMfg: {d}" if "Mfg 0726" != d else "Notebook 100 Pages\nMfg 0726", "notebook")
    assert f(r, "mfg_date").status == "PASS", d


def test_a_crashing_check_becomes_review_not_a_500(monkeypatch=None):
    from app import engine
    original = engine.CHECKS["mrp"]
    engine.CHECKS["mrp"] = lambda ctx: 1 / 0
    try:
        r = analyze_text("Tea\nNet Wt. 100 g", "tea")
    finally:
        engine.CHECKS["mrp"] = original
    assert f(r, "mrp").status == "REVIEW" and f(r, "mrp").sub_case == "CHECK_ERROR"
