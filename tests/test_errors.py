from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import _DB, _SEQ, app


client = TestClient(app)


def test_not_found_item():
    r = client.get("/items/999")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body and body["error"]["code"] == "not_found"


def test_validation_error():
    r = client.post("/items", params={"name": ""})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "validation_error"


# Очистка локального бд сделано для теста
@pytest.fixture(autouse=True)
def clean_state():
    _DB["items"].clear()
    _DB["topics"].clear()
    _SEQ["topic_id"] = 0
    yield


def auth_headers(uid: int = 42):
    return {"X-User": str(uid)}


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_topics_require_auth():
    r = client.get("/topics")  # без X-User
    assert r.status_code == 401
    body = r.json()
    assert body["error"]["code"] == "unauthorized"
    assert "X-User" in body["error"]["message"]  # "missing X-User header"


def test_create_topic_ok():
    due = (date.today() + timedelta(days=3)).isoformat()
    payload = {"title": "Алгебра — лабы", "due_at": due, "status": "todo"}
    r = client.post("/topics", headers=auth_headers(), json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 1
    assert body["owner_id"] == 42
    assert body["title"] == payload["title"]
    assert body["due_at"] == due
    assert body["status"] == "todo"


def test_create_topic_due_in_past_422():
    due = (date.today() - timedelta(days=1)).isoformat()
    payload = {"title": "Просроченная тема", "due_at": due, "status": "todo"}
    r = client.post("/topics", headers=auth_headers(), json=payload)
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "validation_error"


def test_get_topic_owner_only_forbidden():
    # создал пользователь 42
    due = (date.today() + timedelta(days=1)).isoformat()
    create = client.post(
        "/topics",
        headers=auth_headers(42),
        json={"title": "Моя тема", "due_at": due, "status": "todo"},
    )
    assert create.status_code == 201
    tid = create.json()["id"]

    # читает пользователь 7 -> 403
    r = client.get(f"/topics/{tid}", headers=auth_headers(7))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_list_topics_and_filter_by_status():
    due1 = (date.today() + timedelta(days=2)).isoformat()
    due2 = (date.today() + timedelta(days=3)).isoformat()
    due3 = (date.today() + timedelta(days=4)).isoformat()

    # создаём 3 темы с разными статусами
    for title, due, status in [
        ("Т1", due1, "todo"),
        ("Т2", due2, "in_progress"),
        ("Т3", due3, "done"),
    ]:
        r = client.post(
            "/topics",
            headers=auth_headers(100),
            json={"title": title, "due_at": due, "status": status},
        )
        assert r.status_code == 201

    # без фильтра — 3
    r_all = client.get("/topics", headers=auth_headers(100))
    assert r_all.status_code == 200
    arr = r_all.json()
    assert len(arr) == 3

    # статус=todo — 1
    r_todo = client.get("/topics?status=todo", headers=auth_headers(100))
    assert r_todo.status_code == 200
    arr = r_todo.json()
    assert len(arr) == 1
    assert arr[0]["status"] == "todo"

    # статус=done — 1
    r_done = client.get("/topics?status=done", headers=auth_headers(100))
    assert r_done.status_code == 200
    arr = r_done.json()
    assert len(arr) == 1
    assert arr[0]["status"] == "done"


def test_list_topics_invalid_status_422():
    # неверный статус в query => FastAPI выдаёт 422 (RequestValidationError)
    r = client.get("/topics?status=invalid", headers=auth_headers())
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_update_topic_partial_status_only():
    due = (date.today() + timedelta(days=5)).isoformat()
    create = client.post(
        "/topics",
        headers=auth_headers(),
        json={"title": "Тема", "due_at": due, "status": "todo"},
    )
    assert create.status_code == 201
    tid = create.json()["id"]

    r = client.patch(
        f"/topics/{tid}",
        headers=auth_headers(),
        json={"status": "in_progress"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == tid
    assert body["status"] == "in_progress"
    assert body["title"] == "Тема"


def test_delete_topic_204():
    due = (date.today() + timedelta(days=2)).isoformat()
    create = client.post(
        "/topics",
        headers=auth_headers(),
        json={"title": "На удаление", "due_at": due, "status": "todo"},
    )
    assert create.status_code == 201
    tid = create.json()["id"]

    r_del = client.delete(f"/topics/{tid}", headers=auth_headers())
    assert r_del.status_code == 204
    r_get = client.get(f"/topics/{tid}", headers=auth_headers())
    assert r_get.status_code == 404
    assert r_get.json()["error"]["code"] == "not_found"
