import uuid
from typing import List, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse

from app.schemas import TopicCreate, TopicOut, TopicStatus, TopicUpdate

app = FastAPI(title="SecDev Course App", version="0.2.0")


def _is_probably_csv(sample: bytes) -> bool:
    if not sample:
        return False
    try:
        text = sample.decode("utf-8", errors="ignore")
    except Exception:
        return False
    if any(sep in text for sep in [",", ";", "\t"]):
        return True
    return False


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    request.state.request_id = rid

    try:
        response = await call_next(request)
    except ApiError as exc:
        response = _problem_response(
            status=exc.status,
            code=exc.code,
            message=exc.message,
            request=request,
            details=exc.details,
        )

    response.headers["X-Request-Id"] = rid
    return response


def _problem_response(
    status: int,
    code: str,
    message: str,
    request: Request,
    details=None,
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


class ApiError(Exception):
    def __init__(
        self, code: str, message: str, status: int = 400, details: Optional[dict] = None
    ):
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return _problem_response(
        status=exc.status,
        code=exc.code,
        message=exc.message,
        request=request,
        details=exc.details,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "http_error"
    return _problem_response(
        status=exc.status_code,
        code="http_error",
        message=detail,
        request=request,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
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
        status=422,
        code="validation_error",
        message="invalid_request",
        request=request,
        details=_sanitize(exc.errors()),
    )


@app.get("/health")
def health():
    return {"status": "ok"}


# -----------------------------
# Авторизация
# -----------------------------


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


# -----------------------------
# Демо-данные с бд
# -----------------------------

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


# -----------------------------
#  Endpoints
# -----------------------------


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


# -----------------------------
# Topic endpoints
# -----------------------------


# Создать тему
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


# Получить список тем (+ фильтрация по статусу)
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


# Получить тему по id (owner-only)
@app.get("/topics/{topic_id}", response_model=TopicOut)
def get_topic(
    topic_id: int, x_user: Optional[str] = Header(default=None, alias="X-User")
):
    user_id = get_current_user_id(x_user)
    t = _require_owned(topic_id, user_id)
    return TopicOut(**t)


# Изменить тему
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


# Удалить тему по id
@app.delete("/topics/{topic_id}", status_code=204)
def delete_topic(
    topic_id: int, x_user: Optional[str] = Header(default=None, alias="X-User")
):
    user_id = get_current_user_id(x_user)
    t = _require_owned(topic_id, user_id)
    _DB["topics"].remove(t)
    return JSONResponse(status_code=204, content=None)
