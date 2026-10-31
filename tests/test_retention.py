"""The 11th scan pushes the 1st one out, together with its stored photo."""
import types

from app import config, db


class _Resp:
    def __init__(self, data=None): self._d = data if data is not None else []; self.is_success = True; self.text = ""
    def raise_for_status(self): pass
    def json(self): return self._d


class FakeSupabase:
    rows, files, n = [], set(), 0
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def post(self, url, headers=None, json=None, content=None, **k):
        if "/storage/" in url: FakeSupabase.files.add(url.rsplit("/", 1)[1])
        else: FakeSupabase.n += 1; FakeSupabase.rows.append({**json, "_t": FakeSupabase.n})
        return _Resp()
    def get(self, url, headers=None, params=None, **k):
        rows = sorted(FakeSupabase.rows, key=lambda r: -r["_t"])[int(params["offset"]):]
        return _Resp([{"id": r["id"], "image_path": r["image_path"]} for r in rows])
    def delete(self, url, headers=None, params=None, **k):
        if "/storage/" in url: FakeSupabase.files.discard(url.rsplit("/", 1)[1])
        else:
            ids = params["id"][4:-1].split(",")
            FakeSupabase.rows = [r for r in FakeSupabase.rows if r["id"] not in ids]
        return _Resp()


def test_only_last_ten_kept(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_SERVICE_KEY", "k")
    monkeypatch.setattr(db.httpx, "Client", FakeSupabase)
    ids = []
    for _ in range(12):
        res = types.SimpleNamespace(category="food", pack_type=None, input_mode="image", raw_text="", avg_ocr_confidence=.9,
                                    verdict="COMPLIANT", summary={}, model_dump=lambda mode=None: {})
        ids.append(db.save_scan(res, b"img", "image/jpeg"))
    assert len(FakeSupabase.rows) == 10 and len(FakeSupabase.files) == 10
    kept = {r["id"] for r in FakeSupabase.rows}
    assert kept == set(ids[2:]) and not kept & set(ids[:2])
