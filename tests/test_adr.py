import io
import os

import pytest
from fastapi.testclient import TestClient

from app.main import _DB, _SEQ, app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state(tmp_path, monkeypatch):
    _DB["items"].clear()
    _DB["topics"].clear()
    _SEQ["topic_id"] = 0
    monkeypatch.setenv("QUARANTINE_DIR", str(tmp_path / "quarantine"))
    monkeypatch.setenv("CSV_MAX_BYTES", "1048576")
    yield


def auth_headers(uid=42):
    return {"X-User": str(uid)}


# --- ADR-001: correlation_id присутствует в ошибках и заголовках ---
def test_adr001_error_contains_correlation_id_and_header():
    r = client.post("/items", params={"name": ""})
    assert r.status_code == 422
    body = r.json()
    assert "correlation_id" in body
    assert r.headers.get("X-Request-Id") == body["correlation_id"]
    assert body["status"] == 422
    assert body["title"] == "validation_error"


# --- ADR-002: rate limit /auth/login: 5/мин на IP ---
def test_adr002_rate_limit_login_429_after_5_attempts():
    headers = {"X-Forwarded-For": "203.0.113.10"}
    for _ in range(5):
        r = client.post(
            "/auth/login", headers=headers, params={"username": "u", "password": "p"}
        )
        assert r.status_code in (401, 429)
        if r.status_code == 429:
            break
    r = client.post(
        "/auth/login", headers=headers, params={"username": "u", "password": "p"}
    )
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"


# --- ADR-003: secure CSV upload (успешный минимальный CSV) ---
def test_adr003_import_csv_accepts_minimal_csv(tmp_path):
    content = b"col1,col2\n1,2\n"
    files = {"file": ("data.csv", io.BytesIO(content), "text/csv")}
    r = client.post("/topics/import", headers=auth_headers(), files=files)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    assert body["quarantine"] is True
    assert body["size"] == len(content)
    # файл реально существует
    qdir = os.getenv("QUARANTINE_DIR")
    assert os.path.exists(os.path.join(qdir, body["stored_filename"]))


# --- ADR-003: не CSV (бинарь) отклоняется ---
def test_adr003_import_csv_rejects_non_text():
    content = b"\x89PNG\x0D\x0A\x1A\x0A" + b"X" * 100
    files = {"file": ("image.png", io.BytesIO(content), "application/octet-stream")}
    r = client.post("/topics/import", headers=auth_headers(), files=files)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_upload"


# --- ADR-003: слишком большой файл ( > 1 MiB ) ---
def test_adr003_import_csv_rejects_too_large(monkeypatch):
    monkeypatch.setenv("CSV_MAX_BYTES", "1024")  # 1 KiB для теста
    content = b"a,b\n" + (b"x,y\n" * 600)  # чуть больше 1 KiB
    files = {"file": ("big.csv", io.BytesIO(content), "text/csv")}
    r = client.post("/topics/import", headers=auth_headers(), files=files)
    assert r.status_code in (400, 413)
    assert r.json()["error"]["code"] in (
        "bad_upload",
        "validation_error",
        "http_error",
        "rate_limited",
        "bad_upload",
    )
