import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
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

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "label-images")

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]


def supabase_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)
