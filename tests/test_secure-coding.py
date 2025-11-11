import io

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def auth_headers():
    return {"X-User": "42"}


def test_rfc7807_error_envelope_and_request_id():
    # провоцируем validation_error (имя пустое)
    r = client.post(
        "/items", params={"name": ""}, headers={"X-Request-Id": "test-rid-123"}
    )
    assert r.status_code == 422
    body = r.json()

    # RFC 7807 поля
    assert body["type"].startswith("https://httpstatuses.com/")
    assert body["title"] == "validation_error"
    assert body["status"] == 422
    assert body["correlation_id"] == "test-rid-123"
    assert "instance" in body

    # старый формат ошибки сохранился
    assert body["error"]["code"] == "validation_error"

    # заголовок X-Request-Id тоже проброшен
    assert r.headers.get("X-Request-Id") == "test-rid-123"


def test_import_csv_accepts_minimal_csv(tmp_path, monkeypatch):
    # перенаправляем карантин в tmp-папку
    qdir = tmp_path / "quarantine"
    monkeypatch.setenv("QUARANTINE_DIR", str(qdir))

    from importlib import reload

    import app.main as main_module

    reload(main_module)  # чтобы перечитать QUARANTINE_DIR из env
    local_client = TestClient(main_module.app)

    content = b"col1,col2\n1,2\n"
    files = {"file": ("data.csv", io.BytesIO(content), "text/csv")}

    r = local_client.post("/topics/import", headers=auth_headers(), files=files)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    assert body["quarantine"] is True
    assert body["size"] == len(content)

    stored = body["stored_filename"]
    assert stored.endswith(".csv")

    stored_path = qdir / stored
    assert stored_path.exists()
    assert stored_path.read_bytes() == content


def test_import_csv_rejects_too_large(monkeypatch):
    monkeypatch.setenv("CSV_MAX_BYTES", "1024")  # 1 KiB
    from importlib import reload

    import app.main as main_module

    reload(main_module)
    local_client = TestClient(main_module.app)

    content = b"a,b\n" + (b"x,y\n" * 600)  # немного больше 1 KiB
    files = {"file": ("big.csv", io.BytesIO(content), "text/csv")}

    r = local_client.post("/topics/import", headers=auth_headers(), files=files)
    assert r.status_code in (400, 413)
    body = r.json()
    assert body["error"]["code"] in (
        "file_too_large",
        "validation_error",
        "file_too_large",
    )


def test_error_does_not_leak_database_url(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg2://study_user:qwerty1234@db:5432/study_planner",
    )

    # провоцируем ApiError (нет X-User)
    r = client.get("/topics")
    body = r.json()
    text = r.text

    assert r.status_code == 401
    assert body["error"]["code"] == "unauthorized"

    # ни URL, ни пароль в ответ не должны попасть
    assert "supersecret" not in text
    assert "very_secret_db" not in text
    assert "postgresql+psycopg2://" not in text
