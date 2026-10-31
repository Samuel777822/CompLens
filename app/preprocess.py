"""Image clean-up before OCR (OpenCV). Pure functions: bytes in, arrays out."""
from typing import Dict, Iterator, List, Tuple

import cv2
import numpy as np

from . import config


def sniff_image_type(data: bytes) -> str:
    """Identify the file by its first bytes, not by what the browser or phone claims."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"heim", b"heis"):
        return "image/heic"
    if data[:2] == b"BM":
        return "image/bmp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    return ""


def decode_image(data: bytes) -> np.ndarray:
    if not data:
        raise ValueError("The uploaded file is empty.")
    if sniff_image_type(data) == "image/heic":
        raise ValueError("HEIC/HEIF photos are not supported. Set the camera to JPG, or share the photo as JPG.")
    arr = np.frombuffer(data, dtype=np.uint8)
    try:
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # honours EXIF rotation
    except cv2.error as e:
        raise ValueError(f"Could not decode image ({e}). Upload a JPG, PNG or WEBP photo.") from e
    if img is None:
        raise ValueError("Could not decode image. Upload a JPG, PNG or WEBP photo.")
    h, w = img.shape[:2]
    if min(h, w) < 20:
        raise ValueError("The image is too small to contain readable text.")
    if h * w > config.MAX_IMAGE_PIXELS:  # keep memory bounded
        scale = (config.MAX_IMAGE_PIXELS / (h * w)) ** 0.5
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img


def _fit(img: np.ndarray, max_side: int, min_side: int) -> np.ndarray:
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest > max_side:
        scale = max_side / longest
        return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    if longest < min_side:
        scale = min_side / longest
        return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return img


def preprocess(img: np.ndarray, max_side: int = 2000, min_side: int = 1000) -> np.ndarray:
    """Grayscale + denoise + local contrast (CLAHE)."""
    img = _fit(img, max_side, min_side)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, h=7, templateWindowSize=7, searchWindowSize=21)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def variants(img: np.ndarray) -> Iterator[Tuple[str, np.ndarray]]:
    """Different clean-ups of the same photo, best guess first. Lazy: later ones cost nothing
    unless the earlier ones did not give a clean report.

    * clean  - the classic grayscale/denoise/CLAHE (good for glare and uneven light)
    * color  - untouched colours, just resized (CLAHE can wreck text on coloured stickers)
    * sharp  - big upscale + unsharp mask (small print on a narrow strip)
    """
    yield "clean", preprocess(img) if config.PREPROCESS else _fit(img, 2000, 1000)
    yield "color", _fit(img, 2400, 1400)
    big = _fit(img, 3000, 2400)
    gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (0, 0), 3)
    yield "sharp", cv2.addWeighted(gray, 1.8, blur, -0.8, 0)


def rotate(img: np.ndarray, quarter_turns: int) -> np.ndarray:
    k = quarter_turns % 4
    if k == 0:
        return img
    return np.ascontiguousarray(np.rot90(img, k=-k))  # k=1 -> 90 degrees clockwise


def quality_report(img: np.ndarray) -> Dict[str, float]:
    """Cheap photo-quality numbers: sharpness (variance of Laplacian), brightness, contrast."""
    small = _fit(img, 1000, 1)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
    return {
        "sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "brightness": float(gray.mean()),
        "contrast": float(gray.std()),
    }


def quality_warnings(img: np.ndarray, name: str = "") -> List[str]:
    q = quality_report(img)
    tag = f"{name}: " if name else ""
    out = []
    if q["sharpness"] < 40:
        out.append(f"{tag}the photo looks blurry. Hold the phone steady and tap to focus on the text.")
    if q["brightness"] < 60:
        out.append(f"{tag}the photo is very dark. Retake in better light.")
    elif q["brightness"] > 215:
        out.append(f"{tag}the photo is washed out or has strong glare. Tilt the pack to avoid reflections.")
    if q["contrast"] < 25:
        out.append(f"{tag}very low contrast between text and background, which makes OCR unreliable.")
    return out
