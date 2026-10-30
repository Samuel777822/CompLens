"""EasyOCR wrapper. The model is loaded lazily on first use (first call downloads weights)."""
from __future__ import annotations

import threading
from statistics import mean
from typing import List

import numpy as np

from . import config
from .extract import Line

_reader = None
_lock = threading.Lock()


def get_reader():
    global _reader
    with _lock:
        if _reader is None:
            import easyocr  # imported here so the rest of the app works without it

            _reader = easyocr.Reader(config.OCR_LANGS, gpu=config.OCR_GPU)
    return _reader


def group_rows(results) -> List[Line]:
    """EasyOCR returns word/phrase boxes. Merge boxes on the same visual row into one line
    (left to right) so 'Net Wt.' and '100g' end up on the same line."""
    items = []
    for bbox, text, conf in results:
        text = (text or "").strip()
        if not text:
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        items.append({"text": text, "conf": float(conf), "x": min(xs),
                      "yc": (min(ys) + max(ys)) / 2, "h": max(ys) - min(ys)})
    items.sort(key=lambda i: i["yc"])

    rows: list = []
    for it in items:
        if rows and abs(it["yc"] - rows[-1]["yc"]) < 0.6 * max(it["h"], rows[-1]["h"]):
            row = rows[-1]
            row["items"].append(it)
            row["yc"] = mean(i["yc"] for i in row["items"])
            row["h"] = max(row["h"], it["h"])
        else:
            rows.append({"items": [it], "yc": it["yc"], "h": it["h"]})

    lines = []
    for row in rows:
        row["items"].sort(key=lambda i: i["x"])
        lines.append(Line(" ".join(i["text"] for i in row["items"]),
                          round(mean(i["conf"] for i in row["items"]), 3)))
    return lines


def read_label(image: np.ndarray) -> List[Line]:
    results = get_reader().readtext(image)
    return group_rows(results)
