import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"      # the web page and its assets; FastAPI serves them
STATIC_DIR = PUBLIC_DIR / "static"
INDEX_FILE = PUBLIC_DIR / "index.html"
SAMPLES_FILE = BASE_DIR / "samples" / "samples.json"


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


OCR_LANGS = [s.strip() for s in os.getenv("OCR_LANGS", "en,hi").split(",") if s.strip()]
OCR_GPU = _bool("OCR_GPU", False)
PREPROCESS = _bool("PREPROCESS", True)

MIN_FIELD_CONF = _float("MIN_FIELD_CONF", 0.40)
MIN_OVERALL_CONF = _float("MIN_OVERALL_CONF", 0.45)
MAX_UPLOAD_BYTES = int(_float("MAX_UPLOAD_MB", 10) * 1024 * 1024)
MAX_IMAGES = int(_float("MAX_IMAGES", 6))              # photos per scan (front, back, spine, ...)
MAX_IMAGE_PIXELS = int(_float("MAX_IMAGE_MP", 60) * 1_000_000)  # bigger photos are shrunk, not rejected
MAX_TEXT_CHARS = int(_float("MAX_TEXT_CHARS", 20000))

# OCR passes: the pipeline re-reads a photo with different clean-ups / readers until the report is
# clean or the passes run out, then keeps the best one. 1 = single pass (fastest).
OCR_MAX_PASSES = max(1, int(_float("OCR_MAX_PASSES", 3)))
# English-only reader used as an extra pass. Reads Latin text and digits better than en+hi.
OCR_EXTRA_LANGS = [s.strip() for s in os.getenv("OCR_EXTRA_LANGS", "en").split(",") if s.strip()]
OCR_TRY_ROTATIONS = _bool("OCR_TRY_ROTATIONS", True)  # retry 90/180/270 degrees when nothing readable comes out

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "label-images")
KEEP_SCANS = 10  # only the latest 10 scans are stored. supabase/schema.sql enforces the same number.

# Where EasyOCR keeps its model files. Empty = EasyOCR's default (~/.EasyOCR), which is where the
# Dockerfile downloads them at build time, so a restart never has to download anything.
MODEL_DIR = os.getenv("EASYOCR_MODEL_DIR") or None

# Load the OCR models in the background as soon as the server starts, so the FIRST photo scan is as
# fast as every other one. Set to false only for tests or tiny machines.
OCR_PRELOAD = _bool("OCR_PRELOAD", True)

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]


def supabase_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)
