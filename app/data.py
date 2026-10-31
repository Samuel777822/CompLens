"""Reference data: categories, generic-name keywords, standard pack sizes (Part C)."""
from typing import Optional, Tuple

CATEGORIES = [
    ("auto", "Auto-detect from the label (recommended)"),
    ("other", "Other / not listed"),
    ("tea", "Tea"),
    ("biscuits", "Biscuits"),
    ("salt", "Salt"),
    ("cement", "Cement"),
    ("white_cement", "White cement"),
    ("toilet_soap", "Toilet soap"),
    ("aerated_drinks", "Aerated / carbonated drinks"),
    ("bedsheet", "Bedsheet"),
    ("towel", "Towel"),
    ("notebook", "Notebook / book / paper stationery (sold by pages)"),
    ("fabric", "Fabric / cloth (sold by length)"),
    ("tiles", "Tiles (sold by area / count)"),
    ("bidi", "Bidi"),
    ("incense", "Incense sticks"),
    ("lpg_cylinder", "LPG cylinder (14.2 kg / 5 kg PSU)"),
    ("fast_food", "Fast food (packed by restaurant/hotel for immediate sale)"),
    ("scheduled_drug", "Scheduled drug formulation"),
    ("agri_produce", "Agricultural produce"),
]
CATEGORY_KEYS = {k for k, _ in CATEGORIES}

# Rule 6(1)(d): month/year of manufacture not required for these
DATE_EXEMPT_CATEGORIES = {"bidi", "incense", "lpg_cylinder"}
# Rule 6(1)(f): dimensions only apply to these
DIMENSION_CATEGORIES = {"bedsheet", "towel", "fabric", "tiles"}
# Rule 26: whole-package exemptions decided by category
FULL_EXEMPT_CATEGORIES = {
    "fast_food": "Packed directly by restaurants/hotels for immediate sale",
    "scheduled_drug": "Scheduled drug formulation (governed by the Drugs (Price Control) Order)",
}

GENERIC_KEYWORDS = {
    "tea": ["tea", "chai"],
    "biscuits": ["biscuit", "cookie", "cracker"],
    "salt": ["salt"],
    "cement": ["cement"],
    "white_cement": ["cement"],
    "toilet_soap": ["soap"],
    "aerated_drinks": ["aerated", "carbonated", "soft drink", "drink", "beverage", "soda", "cola", "juice"],
    "bedsheet": ["bed sheet", "bedsheet", "bed linen", "sheet"],
    "towel": ["towel"],
    "fabric": ["fabric", "cloth", "suiting", "shirting"],
    "tiles": ["tile"],
    "notebook": ["notebook", "note book", "exercise book", "long book", "register", "copy", "diary",
                 "journal", "jotter", "writing pad", "drawing book", "practical book", "graph book",
                 "record book", "composition book", "spiral"],
}
# Only a hint about what the product is (a brand such as "Book Tech" or the word "Pages" does not
# name the commodity). Seen alone, these send the field to a human instead of passing it.
WEAK_GENERIC_WORDS = ["pages", "page", "sheets", "ruled", "unruled", "single line", "double line", "four line", "book"]
# Used for category "other" and as a fallback for every category
GENERAL_GENERIC_WORDS = [
    "biscuit", "cookie", "tea", "coffee", "salt", "sugar", "rice", "flour", "atta", "maida", "suji",
    "oil", "ghee", "butter", "milk", "curd", "juice", "drink", "beverage", "soda", "cola", "water",
    "soap", "shampoo", "detergent", "toothpaste", "cream", "lotion", "powder", "noodles", "pasta",
    "masala", "spice", "snack", "chips", "namkeen", "chocolate", "candy", "sauce", "ketchup", "jam",
    "pickle", "dal", "pulses", "egg", "fruit", "vegetable", "wheat", "mustard", "sunflower", "coconut", "honey", "cereal", "oats", "cornflakes", "bread", "cake", "paneer",
    "notebook", "note book", "exercise book", "register", "diary", "pencil", "pen", "eraser", "sharpener",
    "marker", "crayon", "stapler", "envelope", "paper", "glue", "ink",
    "shampoo", "conditioner", "face wash", "facewash", "hair oil", "deodorant", "perfume", "talcum", "sanitizer",
    "toothbrush", "mouthwash", "shaving", "razor", "sunscreen", "moisturiser", "moisturizer", "serum", "lipstick",
    "cleaner", "phenyl", "disinfectant", "bleach", "dishwash", "agarbatti", "incense", "candle", "matchbox", "matches",
    "battery", "bulb", "cable", "wire", "pipe", "paint", "adhesive", "putty", "plywood", "fevicol", "tape",
    "shoe", "shoes", "sock", "socks", "shirt", "towel", "bedsheet", "pillow", "blanket", "mat", "brush", "bottle", "toy",
    "biscuits", "wafer", "rusk", "muesli", "tea", "coffee", "ghee", "paneer", "yogurt", "lassi", "buttermilk",
    "vinegar", "tomato", "soup", "dalia", "poha", "besan", "jaggery", "gur", "turmeric", "chilli", "cumin", "pepper",
    "fertilizer", "pesticide", "seeds", "cattle feed", "pet food", "vitamin", "supplement", "protein",
]


def _is_mult(v: float, k: float) -> bool:
    q = v / k
    return v > 0 and abs(q - round(q)) < 1e-9


def _in(v: float, values) -> bool:
    return any(abs(v - x) < 1e-9 for x in values)


# category -> unit the table is expressed in (after normalising to g / ml)
SIZE_TABLE_UNIT = {
    "tea": "g", "biscuits": "g", "salt": "g", "toilet_soap": "g",
    "cement": "g", "white_cement": "g", "aerated_drinks": "ml",
}


def is_standard_size(
    category: str, value: float, pack_type: Optional[str] = None
) -> Tuple[Optional[bool], Optional[str]]:
    """value is in g or ml (see SIZE_TABLE_UNIT). Returns (is_standard, note).
    (None, None) means the category has no table."""
    if category == "tea":
        return _in(value, [25, 50, 100, 125, 250, 500]) or (value >= 1000 and _is_mult(value, 1000)), None
    if category == "biscuits":
        return _in(value, [25, 50, 75, 100, 150, 200, 250, 300]) or (value > 300 and _is_mult(value, 100)), None
    if category == "salt":
        if value < 50:
            return _is_mult(value, 10), None
        return _in(value, [50, 100, 200, 500, 750, 1000, 2000, 5000]) or (value > 5000 and _is_mult(value, 5000)), None
    if category in ("cement", "white_cement"):
        kg = value / 1000.0
        if _in(kg, [40]) and category != "white_cement":
            return False, "40 kg is a standard size for white cement only"
        allowed = [1, 2, 5, 10, 20, 25, 50] + ([40] if category == "white_cement" else [])
        return _in(kg, allowed), None
    if category == "toilet_soap":
        return _in(value, [25, 50, 75, 100, 125, 150]) or (value > 150 and _is_mult(value, 50)), None
    if category == "aerated_drinks":
        if _in(value, [330]):
            if pack_type is None:
                return True, "330 ml is standard for cans only; pack type was not given, assumed can"
            return pack_type == "can", "330 ml is standard for cans only"
        return _in(value, [65, 100, 125, 150, 200, 250, 300, 500, 750, 1000, 1500, 2000, 3000, 4000, 5000]), None
    return None, None


LIMITATIONS = [
    "Rule 7 (numeral height) is not checked: a photo has no real-world scale. This is a stated team decision.",
    "Rule 8 (clear space around the net quantity) is not checked.",
    "Language (Rule 9) is checked on the whole label, not per declaration.",
    "Legibility and contrast are approximated from OCR confidence, not measured directly.",
    "Results depend on OCR quality; low-confidence fields are sent to human review instead of being passed or failed.",
]
