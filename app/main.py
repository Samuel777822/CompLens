import json
import logging
import threading
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .data import CATEGORIES, CATEGORY_KEYS
from .engine import analyze_text
from .models import ScanResult, TextCheckRequest

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("complens.api")


def _warm_up_ocr() -> None:
    try:  # heavy imports stay optional: the text checker works without OCR installed
        from .ocr import warm_up
    except ImportError:
        log.warning("OCR libraries are not installed; photo scans are disabled, text checks still work.")
        return
    warm_up()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """On server start, load the OCR models in a background thread. The server answers requests
    straight away (the page and text checks work at once); photo scans wait for the models if they
    arrive before loading has finished."""
    if config.OCR_PRELOAD:
        threading.Thread(target=_warm_up_ocr, name="ocr-warm-up", daemon=True).start()
    yield


app = FastAPI(title="CompLens", version="3.1.0", lifespan=lifespan,
              description="Label compliance checker for the Legal Metrology (Packaged Commodities) Rules, 2011")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
if config.STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.middleware("http")
async def no_stale_ui(request: Request, call_next):
    """Always revalidate the page and its assets, so a phone never keeps showing an old UI."""
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp

PACK_TYPES = {"can", "bottle", "other"}
OK_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"}


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    """Whatever goes wrong, the client gets JSON with a readable message, never an HTML stack trace."""
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"Unexpected server error: {type(exc).__name__}. "
                                                            "The details are in the server log."})


def _check_inputs(category: Optional[str], pack_type: Optional[str]):
    category = (category or "auto").strip().lower() or "auto"
    if category not in CATEGORY_KEYS:
        raise HTTPException(422, f"Unknown category '{category}'. See GET /api/categories.")
    pack_type = (pack_type or "").strip().lower() or None
    if pack_type and pack_type not in PACK_TYPES:
        raise HTTPException(422, f"pack_type must be one of {sorted(PACK_TYPES)}")
    return category, pack_type


@app.get("/")
def index():
    return FileResponse(config.INDEX_FILE)


@app.get("/health")
def health():
    """Always answers fast. `ocr` is idle / loading / ready / failed (photo scans need `ready`,
    or will simply wait for the models to finish loading)."""
    try:
        from .ocr import ocr_status
        ocr = ocr_status()
    except ImportError:
        ocr = {"status": "unavailable", "error": "OCR libraries are not installed", "seconds": None}
    return {"status": "ok", "supabase": config.supabase_enabled(), "ocr_langs": config.OCR_LANGS, "ocr": ocr}


@app.get("/api/categories")
def categories():
    return [{"key": k, "label": v} for k, v in CATEGORIES]


@app.get("/api/samples")
def samples():
    return json.loads(config.SAMPLES_FILE.read_text(encoding="utf-8"))


@app.post("/api/check-text", response_model=ScanResult)
def check_text(req: TextCheckRequest):
    """Run the rules engine on pasted label text (no OCR). Handy for demos and testing."""
    category, pack_type = _check_inputs(req.category, req.pack_type)
    if not req.text.strip():
        raise HTTPException(422, "text is empty")
    if len(req.text) > config.MAX_TEXT_CHARS:
        raise HTTPException(413, f"Text is longer than {config.MAX_TEXT_CHARS} characters.")
    result = analyze_text(req.text, category, pack_type)
    result.scan_id = db.save_scan(result)
    return result


@app.post("/api/scan", response_model=ScanResult)
def scan(
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None),  # single-photo clients keep working
    category: str = Form("auto"),
    pack_type: Optional[str] = Form(None),
):
    """Photo(s) in, compliance report out. Send several photos of the same pack (front, back, spine)
    as repeated `files` fields and they are checked together as one label."""
    category, pack_type = _check_inputs(category, pack_type)
    uploads = [u for u in [*(files or []), *([file] if file else [])] if u is not None]
    if not uploads:
        raise HTTPException(422, "Upload at least one photo in the 'files' field.")
    if len(uploads) > config.MAX_IMAGES:
        raise HTTPException(422, f"At most {config.MAX_IMAGES} photos per check.")

    try:  # heavy imports live here so the rest of the app runs without OpenCV / EasyOCR installed
        from .ocr import OcrUnavailable
        from .pipeline import ScanError, scan_images
        from .preprocess import decode_image, sniff_image_type
    except ImportError as e:
        raise HTTPException(503, f"OCR dependencies are not installed: {e}")

    raw: List[bytes] = []
    for u in uploads:
        data = u.file.read(config.MAX_UPLOAD_BYTES + 1)
        name = u.filename or "photo"
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"{name} is larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
        kind = sniff_image_type(data)  # trust the bytes, not the browser's content-type
        if kind == "image/heic":
            raise HTTPException(415, f"{name} is a HEIC photo. Set the camera to JPG, or share the photo as JPG.")
        if kind not in OK_IMAGE_TYPES:
            raise HTTPException(415, f"{name} is not a JPG, PNG or WEBP image.")
        raw.append(data)

    try:
        images = [decode_image(d) for d in raw]
        result = scan_images(images, category, pack_type)
    except ValueError as e:  # undecodable / empty / too small image
        raise HTTPException(400, str(e))
    except ScanError as e:  # decoded fine, but no text could be read
        raise HTTPException(422, str(e))
    except OcrUnavailable as e:
        raise HTTPException(503, str(e))
    except MemoryError:
        raise HTTPException(413, "The photo is too large to process. Use a smaller photo.")

    result.scan_id = db.save_scan(result, raw[0], sniff_image_type(raw[0]))
    return result


@app.get("/api/history")
def history(limit: int = config.KEEP_SCANS):
    return {"enabled": config.supabase_enabled(), "scans": db.list_scans(max(1, min(limit, config.KEEP_SCANS)))}


@app.get("/api/scans/{scan_id}", response_model=ScanResult)
def get_scan(scan_id: str):
    row = db.get_scan(scan_id)
    if not row:
        raise HTTPException(404, "Scan not found (or Supabase is not configured).")
    return row
