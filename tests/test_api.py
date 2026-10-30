import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_and_static():
    assert client.get("/health").json()["status"] == "ok"
    assert "PackCheck" in client.get("/").text


def test_categories_and_samples():
    assert any(c["key"] == "tea" for c in client.get("/api/categories").json())
    assert len(client.get("/api/samples").json()) >= 3


def test_check_text_returns_schema():
    r = client.post("/api/check-text", json={"text": "Tea\nNet Wt. approx 120g", "category": "tea"})
    assert r.status_code == 200
    body = r.json()
    nq = next(f for f in body["fields"] if f["field"] == "net_quantity")
    assert nq["violation_code"] == "VAGUE_LANGUAGE" and nq["rule_reference"] == "Rule 6(1)(c)"
    assert body["verdict"] == "NON_COMPLIANT"


def test_validation_errors():
    assert client.post("/api/check-text", json={"text": "x", "category": "nope"}).status_code == 422
    assert client.post("/api/check-text", json={"text": "  "}).status_code == 422
    assert client.post("/api/check-text", json={"text": "x", "pack_type": "jar"}).status_code == 422


def test_scan_rejects_non_image():
    r = client.post("/api/scan", files={"file": ("a.txt", b"hello", "text/plain")}, data={"category": "tea"})
    assert r.status_code == 415


def test_scan_rejects_corrupt_image():
    pytest.importorskip("cv2")
    r = client.post("/api/scan", files={"file": ("a.jpg", b"not an image", "image/jpeg")}, data={"category": "tea"})
    assert r.status_code in (400, 503)


def test_history_without_supabase():
    assert client.get("/api/history").json() == {"enabled": False, "scans": []}
    assert client.get("/api/scans/abc").status_code == 404
