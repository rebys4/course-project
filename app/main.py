import os
import time
import uuid
from collections import defaultdict, deque
from typing import List, Optional

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas import TopicCreate, TopicOut, TopicStatus, TopicUpdate

app = FastAPI(title="SecDev Course App", version="0.3.0")


# =========================
# Errors + Correlation ID
# =========================
class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        details: Optional[dict] = None,
    ):
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    return response


def _problem_response(
    status: int, code: str, message: str, request: Request, details=None
) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    body = {
        "type": f"https://httpstatuses.com/{status}",
        "title": code,
        "status": status,
        "detail": message,
        "instance": str(request.url),
        "correlation_id": rid,
        "error": {"code": code, "message": message, "details": details or []},
    }
    return JSONResponse(status_code=status, content=body)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return _problem_response(exc.status, exc.code, exc.message, request, exc.details)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "http_error"
    return _problem_response(exc.status_code, "http_error", detail, request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # sanitize details: turn Exception in ctx["error"] into str(...)
    def _sanitize(errors):
        out = []
        for e in errors:
            e = dict(e)
            ctx = e.get("ctx")
            if (
                isinstance(ctx, dict)
                and "error" in ctx
                and isinstance(ctx["error"], Exception)
            ):
                ctx = dict(ctx)
                ctx["error"] = str(ctx["error"])
                e["ctx"] = ctx
            out.append(e)
        return out

    return _problem_response(
        422, "validation_error", "invalid_request", request, _sanitize(exc.errors())
    )


@app.get("/health")
def health():
    return {"status": "ok"}


# =========================
# Auth / Rate limit (ADR-002)
# =========================
_RATE_WINDOW_SEC = 60
_RATE_LIMIT = 5
_RATE_BUCKET = defaultdict(lambda: deque(maxlen=100))


def _client_ip(request: Request) -> str:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_check(ip: str) -> bool:
    now = time.time()
    dq = _RATE_BUCKET[ip]
    while dq and now - dq[0] > _RATE_WINDOW_SEC:
        dq.popleft()
    if len(dq) >= _RATE_LIMIT:
        return False
    dq.append(now)
    return True


@app.post("/auth/login")
def auth_login(request: Request, username: str, password: str):
    ip = _client_ip(request)
    if not _rate_check(ip):
        raise ApiError(code="rate_limited", message="Too Many Requests", status=429)
    # Заглушка: логин не реализован
    raise ApiError(code="unauthorized", message="Invalid credentials", status=401)


# =========================
# Auth helper
# =========================
def get_current_user_id(x_user: Optional[str]) -> int:
    if not x_user:
        raise ApiError(code="unauthorized", message="missing X-User header", status=401)
    try:
        uid = int(x_user)
    except ValueError:
        raise ApiError(
            code="unauthorized", message="X-User must be integer", status=401
        )
    if uid <= 0:
        raise ApiError(
            code="unauthorized", message="X-User must be positive integer", status=401
        )
    return uid


# =========================
# In-memory store
# =========================
_DB = {
    "items": [],
    "topics": [],
}
_SEQ = {"topic_id": 0}


def _next_topic_id() -> int:
    _SEQ["topic_id"] += 1
    return _SEQ["topic_id"]


def _find_topic(topic_id: int) -> Optional[dict]:
    return next((t for t in _DB["topics"] if t["id"] == topic_id), None)


def _require_owned(topic_id: int, owner_id: int) -> dict:
    t = _find_topic(topic_id)
    if not t:
        raise ApiError(code="not_found", message="topic not found", status=404)
    if t["owner_id"] != owner_id:
        raise ApiError(
            code="forbidden", message="topic not owned by current user", status=403
        )
    return t


# =========================
# Items demo endpoints
# =========================
@app.post("/items")
def create_item(name: str):
    if not name or len(name) > 100:
        raise ApiError(
            code="validation_error", message="name must be 1..100 chars", status=422
        )
    item = {"id": len(_DB["items"]) + 1, "name": name}
    _DB["items"].append(item)
    return item


@app.get("/items/{item_id}")
def get_item(item_id: int):
    for it in _DB["items"]:
        if it["id"] == item_id:
            return it
    raise ApiError(code="not_found", message="item not found", status=404)


# =========================
# Topics endpoints
# =========================
@app.post("/topics", response_model=TopicOut, status_code=201)
def create_topic(
    payload: TopicCreate, x_user: Optional[str] = Header(default=None, alias="X-User")
):
    user_id = get_current_user_id(x_user)
    topic = {
        "id": _next_topic_id(),
        "owner_id": user_id,
        "title": payload.title.strip(),
        "due_at": payload.due_at,
        "status": payload.status,
    }
    _DB["topics"].append(topic)
    return TopicOut(**topic)


@app.get("/topics", response_model=List[TopicOut])
def list_topics(
    status: Optional[TopicStatus] = None,
    x_user: Optional[str] = Header(default=None, alias="X-User"),
):
    user_id = get_current_user_id(x_user)
    rows = [t for t in _DB["topics"] if t["owner_id"] == user_id]
    if status:
        rows = [t for t in rows if t["status"] == status]
    return [TopicOut(**t) for t in rows]


@app.get("/topics/{topic_id}", response_model=TopicOut)
def get_topic(
    topic_id: int, x_user: Optional[str] = Header(default=None, alias="X-User")
):
    user_id = get_current_user_id(x_user)
    t = _require_owned(topic_id, user_id)
    return TopicOut(**t)


@app.patch("/topics/{topic_id}", response_model=TopicOut)
def update_topic(
    topic_id: int,
    payload: TopicUpdate,
    x_user: Optional[str] = Header(default=None, alias="X-User"),
):
    user_id = get_current_user_id(x_user)
    t = _require_owned(topic_id, user_id)

    if payload.title is not None:
        t["title"] = payload.title.strip()
    if payload.due_at is not None:
        t["due_at"] = payload.due_at
    if payload.status is not None:
        t["status"] = payload.status

    return TopicOut(**t)


@app.delete("/topics/{topic_id}", status_code=204)
def delete_topic(
    topic_id: int, x_user: Optional[str] = Header(default=None, alias="X-User")
):
    user_id = get_current_user_id(x_user)
    t = _require_owned(topic_id, user_id)
    _DB["topics"].remove(t)
    return JSONResponse(status_code=204, content=None)


# =========================
# Secure CSV upload (ADR-003)
# =========================


def _get_max_csv_bytes() -> int:
    # читаем env динамически (тесты могут monkeypatch os.environ)
    try:
        return int(os.getenv("CSV_MAX_BYTES", str(1 * 1024 * 1024)))
    except ValueError:
        return 1 * 1024 * 1024  # безопасное значение по умолчанию (1 MiB)


def _get_quarantine_dir() -> str:
    return os.getenv("QUARANTINE_DIR", "./quarantine")


def _looks_like_csv(head: bytes) -> bool:
    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return ("," in text) or (";" in text) or ("\t" in text)


@app.post("/topics/import", status_code=202)
async def import_topics_csv(
    x_user: Optional[str] = Header(default=None, alias="X-User"),
    file: UploadFile = File(...),
):
    get_current_user_id(x_user)

    max_bytes = _get_max_csv_bytes()
    qdir = _get_quarantine_dir()

    # читаем ограниченно "голову" файла
    head = await file.read(min(max_bytes + 1, 4096))
    if len(head) == 0:
        raise ApiError(code="bad_upload", message="empty file", status=400)
    if not _looks_like_csv(head):
        raise ApiError(code="bad_upload", message="not a CSV/plain text", status=400)

    total = len(head)
    if total > max_bytes:
        raise ApiError(code="bad_upload", message="file too large", status=413)

    os.makedirs(qdir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.csv"
    fpath = os.path.join(qdir, fname)

    with open(fpath, "wb") as out:
        out.write(head)
        # дочитываем строго до лимита
        while True:
            chunk = await file.read(min(65536, max_bytes - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ApiError(code="bad_upload", message="file too large", status=413)
            out.write(chunk)

    return {
        "status": "accepted",
        "stored_filename": fname,
        "size": total,
        "quarantine": True,
    }
