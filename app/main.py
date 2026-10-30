import json
import logging
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .data import CATEGORIES, CATEGORY_KEYS
from .engine import analyze, analyze_text
from .models import ScanResult, TextCheckRequest

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="PackCheck", version="1.0.0",
              description="Label compliance checker for the Legal Metrology (Packaged Commodities) Rules, 2011")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

PACK_TYPES = {"can", "bottle", "other"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _check_inputs(category: str, pack_type: Optional[str]) -> Optional[str]:
    if category not in CATEGORY_KEYS:
        raise HTTPException(422, f"Unknown category '{category}'. See GET /api/categories.")
    pack_type = (pack_type or "").strip().lower() or None
    if pack_type and pack_type not in PACK_TYPES:
        raise HTTPException(422, f"pack_type must be one of {sorted(PACK_TYPES)}")
    return pack_type


@app.get("/")
def index():
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "supabase": config.supabase_enabled(), "ocr_langs": config.OCR_LANGS}


@app.get("/api/categories")
def categories():
    return [{"key": k, "label": v} for k, v in CATEGORIES]


@app.get("/api/samples")
def samples():
    return json.loads(config.SAMPLES_FILE.read_text(encoding="utf-8"))


@app.post("/api/check-text", response_model=ScanResult)
def check_text(req: TextCheckRequest):
    """Run the rules engine on pasted label text (no OCR). Handy for demos and testing."""
    pack_type = _check_inputs(req.category, req.pack_type)
    if not req.text.strip():
        raise HTTPException(422, "text is empty")
    result = analyze_text(req.text, req.category, pack_type)
    result.scan_id = db.save_scan(result)
    return result


@app.post("/api/scan", response_model=ScanResult)
def scan(
    file: UploadFile = File(...),
    category: str = Form("other"),
    pack_type: Optional[str] = Form(None),
):
    """Photo in, compliance report out: preprocess -> EasyOCR -> extract -> rules."""
    pack_type = _check_inputs(category, pack_type)
    if file.content_type not in IMAGE_TYPES:
        raise HTTPException(415, "Upload a JPG, PNG or WEBP image.")
    data = file.file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Image is larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

    try:
        from .ocr import read_label
        from .preprocess import decode_image, preprocess

        img = decode_image(data)
        if config.PREPROCESS:
            img = preprocess(img)
        lines = read_label(img)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except ImportError as e:
        raise HTTPException(503, f"OCR dependencies are not installed: {e}")

    if not lines:
        raise HTTPException(422, "No text could be read from this image. Try a clearer, closer photo.")
    result = analyze(lines, category, pack_type, from_ocr=True)
    result.scan_id = db.save_scan(result, data, file.content_type)
    return result


@app.get("/api/history")
def history(limit: int = 20):
    return {"enabled": config.supabase_enabled(), "scans": db.list_scans(max(1, min(limit, 100)))}


@app.get("/api/scans/{scan_id}", response_model=ScanResult)
def get_scan(scan_id: str):
    row = db.get_scan(scan_id)
    if not row:
        raise HTTPException(404, "Scan not found (or Supabase is not configured).")
    return row
