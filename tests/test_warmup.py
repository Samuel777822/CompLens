"""The OCR warm-up that runs when the server starts. Uses a fake EasyOCR, so no models are needed."""
import threading
import types

import pytest

from app import config, ocr


@pytest.fixture
def fake_easyocr(monkeypatch):
    calls = []

    class FakeReader:
        def __init__(self, langs, gpu=False, **kw):
            calls.append(("init", tuple(langs)))

        def readtext(self, img, **kw):
            calls.append(("read", img.shape))
            return []

    mod = types.ModuleType("easyocr")
    mod.Reader = FakeReader
    monkeypatch.setitem(__import__("sys").modules, "easyocr", mod)
    monkeypatch.setattr(ocr, "_readers", {})
    monkeypatch.setattr(ocr, "_state", {"status": "idle", "error": None, "seconds": None})
    monkeypatch.setattr(config, "OCR_MAX_PASSES", 3)
    return mod, calls


def test_default_loads_both_readers_then_ready(fake_easyocr):
    _, calls = fake_easyocr
    assert ocr.ocr_status()["status"] == "idle"
    ocr.warm_up()
    st = ocr.ocr_status()
    assert st["status"] == "ready" and st["error"] is None and st["seconds"] is not None
    assert [c[1] for c in calls if c[0] == "init"] == [("en", "hi"), ("en",)]  # main + extra reader
    assert len([c for c in calls if c[0] == "read"]) == 2


def test_single_pass_loads_only_one_reader(fake_easyocr, monkeypatch):
    _, calls = fake_easyocr
    monkeypatch.setattr(config, "OCR_MAX_PASSES", 1)
    ocr.warm_up()
    assert [c[1] for c in calls if c[0] == "init"] == [("en", "hi")]


def test_failure_is_recorded_not_raised(fake_easyocr):
    mod, _ = fake_easyocr

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("no internet")

    mod.Reader = Boom
    ocr.warm_up()  # must not raise
    st = ocr.ocr_status()
    assert st["status"] == "failed" and "no internet" in st["error"]


def test_scan_during_loading_shares_the_same_reader(fake_easyocr):
    """A scan that arrives while the models load waits for them; it never loads a second copy."""
    _, calls = fake_easyocr
    t = threading.Thread(target=ocr.warm_up)
    t.start()
    ocr.get_reader()
    t.join()
    assert [c for c in calls if c[0] == "init"].count(("init", ("en", "hi"))) == 1
