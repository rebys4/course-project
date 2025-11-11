from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.models import Item as ItemModel
from app.models import Topic as TopicModel
from app.schemas import TopicCreate, TopicOut, TopicStatus, TopicUpdate
from database.db import SessionLocal, init_db

app = FastAPI(title="SecDev Course App", version="0.3.0")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


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
    return JSONResponse(
        status_code=exc.status,
        content={
            "error": {"code": exc.code, "message": exc.message, "details": exc.details}
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "http_error"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": detail}},
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

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "invalid_request",
                "details": _sanitize(exc.errors()),
            }
        },
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
# Подключение к БД (SQLAlchemy)
# -----------------------------


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _topic_to_out(t: TopicModel) -> TopicOut:
    return TopicOut(
        id=t.id,
        owner_id=t.owner_id,
        title=t.title,
        due_at=t.due_at,
        status=t.status,  # type: ignore[arg-type]
    )


def _require_owned(db: Session, topic_id: int, owner_id: int) -> TopicModel:
    t = db.query(TopicModel).filter(TopicModel.id == topic_id).first()
    if not t:
        raise ApiError(code="not_found", message="topic not found", status=404)
    if t.owner_id != owner_id:
        raise ApiError(
            code="forbidden", message="topic not owned by current user", status=403
        )
    return t


# -----------------------------
#  Endpoints /items (через БД)
# -----------------------------


@app.post("/items")
def create_item(name: str, db: Session = Depends(get_db)):
    if not name or len(name) > 100:
        raise ApiError(
            code="validation_error", message="name must be 1..100 chars", status=422
        )

    item = ItemModel(name=name)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "name": item.name}


@app.get("/items/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(ItemModel).filter(ItemModel.id == item_id).first()
    if not item:
        raise ApiError(code="not_found", message="item not found", status=404)
    return {"id": item.id, "name": item.name}


# -----------------------------
# Topic endpoints (через БД)
# -----------------------------


@app.post("/topics", response_model=TopicOut, status_code=201)
def create_topic(
    payload: TopicCreate,
    x_user: Optional[str] = Header(default=None, alias="X-User"),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(x_user)

    topic = TopicModel(
        owner_id=user_id,
        title=payload.title.strip(),
        due_at=payload.due_at,
        status=payload.status,
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return _topic_to_out(topic)


@app.get("/topics", response_model=List[TopicOut])
def list_topics(
    status: Optional[TopicStatus] = None,
    x_user: Optional[str] = Header(default=None, alias="X-User"),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(x_user)
    q = db.query(TopicModel).filter(TopicModel.owner_id == user_id)
    if status is not None:
        q = q.filter(TopicModel.status == status)
    rows = q.all()
    return [_topic_to_out(t) for t in rows]


@app.get("/topics/{topic_id}", response_model=TopicOut)
def get_topic(
    topic_id: int,
    x_user: Optional[str] = Header(default=None, alias="X-User"),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(x_user)
    t = _require_owned(db, topic_id, user_id)
    return _topic_to_out(t)


@app.patch("/topics/{topic_id}", response_model=TopicOut)
def update_topic(
    topic_id: int,
    payload: TopicUpdate,
    x_user: Optional[str] = Header(default=None, alias="X-User"),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(x_user)
    t = _require_owned(db, topic_id, user_id)

    if payload.title is not None:
        t.title = payload.title.strip()
    if payload.due_at is not None:
        t.due_at = payload.due_at
    if payload.status is not None:
        t.status = payload.status

    db.add(t)
    db.commit()
    db.refresh(t)
    return _topic_to_out(t)


@app.delete("/topics/{topic_id}", status_code=204)
def delete_topic(
    topic_id: int,
    x_user: Optional[str] = Header(default=None, alias="X-User"),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(x_user)
    t = _require_owned(db, topic_id, user_id)
    db.delete(t)
    db.commit()
    return JSONResponse(status_code=204, content=None)
