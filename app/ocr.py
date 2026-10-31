"""EasyOCR wrapper. Models load lazily on first use (first call downloads weights).

EasyOCR returns word/phrase boxes. Two ways of turning them into lines are provided, because
labels are laid out in columns (logo | address | price | size) and a plain "same row" merge glues
unrelated columns together:

* group_rows     - merge every box on the same visual row (left to right)
* group_columns  - split rows at big horizontal gaps, then read column by column

The pipeline analyses both views and keeps whichever one yields the better report.
"""
from __future__ import annotations

import logging
import threading
from statistics import mean, median
from typing import Dict, List, Sequence, Tuple

import numpy as np

from . import config
from .extract import Line

log = logging.getLogger("complens.ocr")

_readers: Dict[Tuple[str, ...], object] = {}
_reader_lock = threading.Lock()
_infer_lock = threading.Lock()  # one OCR inference at a time: EasyOCR/PyTorch is not safe to share


class OcrUnavailable(RuntimeError):
    """EasyOCR is not installed, or its model weights could not be loaded or downloaded."""


_state: Dict[str, object] = {"status": "idle", "error": None, "seconds": None}  # idle | loading | ready | failed


def ocr_status() -> Dict[str, object]:
    """Where the OCR engine is: idle (not started), loading, ready, or failed. Shown on /health."""
    return dict(_state)


def warm_up() -> None:
    """Load every OCR reader the pipeline can use and run one tiny dummy read, so the first real
    scan does not pay for loading PyTorch and the models. Never raises: failure is recorded in the
    status and the first real scan simply tries again."""
    import time

    _state.update(status="loading", error=None, seconds=None)
    started = time.time()
    try:
        main = tuple(config.OCR_LANGS)
        extra = tuple(config.OCR_EXTRA_LANGS) or main
        needed = list(dict.fromkeys([main, main, extra][: config.OCR_MAX_PASSES]))  # same plan as pipeline.py
        blank = np.full((96, 320, 3), 255, dtype=np.uint8)
        for langs in needed:
            reader = get_reader(langs)
            with _infer_lock:
                reader.readtext(blank)  # first inference is slower (PyTorch allocates its buffers)
        _state.update(status="ready", seconds=round(time.time() - started, 1))
        log.info("OCR warm-up finished in %.1f s (%s)", time.time() - started, ["+".join(n) for n in needed])
    except Exception as e:  # noqa: BLE001 - must never crash the server
        _state.update(status="failed", error=str(e))
        log.exception("OCR warm-up failed; the first scan will try to load the models itself")


def get_reader(langs: Sequence[str] = None):
    langs = tuple(langs or config.OCR_LANGS)
    with _reader_lock:
        if langs not in _readers:
            try:
                import easyocr  # imported here so the rest of the app works without it
            except ImportError as e:
                raise OcrUnavailable(f"EasyOCR is not installed ({e}). Run: pip install -r requirements.txt") from e
            try:
                extra = {"model_storage_directory": config.MODEL_DIR, "user_network_directory": config.MODEL_DIR} if config.MODEL_DIR else {}
                _readers[langs] = easyocr.Reader(list(langs), gpu=config.OCR_GPU, **extra)
            except Exception as e:  # model download / load failure; do not cache, so a retry can succeed
                raise OcrUnavailable(
                    f"Could not load the OCR model for {list(langs)}: {e}. "
                    "The first run needs internet to download the model files."
                ) from e
        return _readers[langs]


def _items(results) -> List[dict]:
    items = []
    for bbox, text, conf in results:
        text = (text or "").strip()
        if not text:
            continue
        xs = [float(p[0]) for p in bbox]
        ys = [float(p[1]) for p in bbox]
        items.append({"text": text, "conf": float(conf), "x": min(xs), "x2": max(xs),
                      "yc": (min(ys) + max(ys)) / 2, "h": max(max(ys) - min(ys), 1.0)})
    items.sort(key=lambda i: i["yc"])
    return items


def _rows(items: List[dict]) -> List[dict]:
    rows: List[dict] = []
    for it in items:
        if rows and abs(it["yc"] - rows[-1]["yc"]) < 0.6 * max(it["h"], rows[-1]["h"]):
            row = rows[-1]
            row["items"].append(it)
            row["yc"] = mean(i["yc"] for i in row["items"])
            row["h"] = max(row["h"], it["h"])
        else:
            rows.append({"items": [it], "yc": it["yc"], "h": it["h"]})
    for row in rows:
        row["items"].sort(key=lambda i: i["x"])
    return rows


def _line(parts: List[dict]) -> Line:
    return Line(" ".join(i["text"] for i in parts), round(mean(i["conf"] for i in parts), 3))


def group_rows(results) -> List[Line]:
    """Merge boxes on the same visual row (left to right) so 'Net Wt.' and '100g' share a line."""
    return [_line(row["items"]) for row in _rows(_items(results))]


def group_columns(results, gap_factor: float = 2.5) -> List[Line]:
    """Like group_rows, but a row is cut wherever two neighbouring boxes are more than
    `gap_factor` text-heights apart, and the pieces are then read column by column.
    Falls back to plain row order when the label has no clear columns."""
    rows = _rows(_items(results))
    if not rows:
        return []
    segs: List[dict] = []
    for row in rows:
        cur = [row["items"][0]]
        for it in row["items"][1:]:
            if it["x"] - cur[-1]["x2"] > gap_factor * row["h"]:
                segs.append({"parts": cur, "yc": row["yc"], "x": cur[0]["x"], "x2": max(i["x2"] for i in cur)})
                cur = [it]
            else:
                cur.append(it)
        segs.append({"parts": cur, "yc": row["yc"], "x": cur[0]["x"], "x2": max(i["x2"] for i in cur)})

    # columns = groups of segments whose horizontal extents overlap (or nearly touch)
    tol = 0.5 * median(r["h"] for r in rows)
    span = max(s["x2"] for s in segs) - min(s["x"] for s in segs)
    narrow = [s for s in segs if (s["x2"] - s["x"]) < 0.6 * span] or segs  # wide banners must not fuse columns
    cols: List[List[float]] = []  # [x_min, x_max]
    for s in sorted(narrow, key=lambda s: s["x"]):
        if cols and s["x"] <= cols[-1][1] + tol:
            cols[-1][1] = max(cols[-1][1], s["x2"])
        else:
            cols.append([s["x"], s["x2"]])
    if len(cols) < 2:
        return [_line(s["parts"]) for s in segs]

    def col_of(s: dict) -> int:
        centre = (s["x"] + s["x2"]) / 2
        return min(range(len(cols)), key=lambda i: 0 if cols[i][0] <= centre <= cols[i][1]
                   else min(abs(centre - cols[i][0]), abs(centre - cols[i][1])))

    ordered = sorted(segs, key=lambda s: (col_of(s), s["yc"]))
    return [_line(s["parts"]) for s in ordered]


def read_views(image: np.ndarray, langs: Sequence[str] = None, mag_ratio: float = 1.0) -> Dict[str, List[Line]]:
    """Run OCR once, return the same boxes as {'rows': [...], 'columns': [...]}."""
    reader = get_reader(langs)
    with _infer_lock:
        results = reader.readtext(image, mag_ratio=mag_ratio)
    return {"rows": group_rows(results), "columns": group_columns(results)}


def read_label(image: np.ndarray) -> List[Line]:
    return read_views(image)["rows"]
