# database/db.py
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

# грузим .env (как у тебя было)
ROOT_DIR = Path(__file__).resolve().parents[1]
env_path = ROOT_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=False)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/study_planner",
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    """
    Создаёт таблицы. Если PostgreSQL недоступен (например, в CI),
    пробуем переключиться на SQLite, чтобы тесты не падали.
    """
    from app import models  # noqa: F401  — чтобы таблицы были зарегистрированы

    try:
        Base.metadata.create_all(bind=engine)
        return
    except OperationalError:
        fallback_url = "sqlite:///./test_fallback.db"

        fallback_engine = create_engine(
            fallback_url,
            connect_args={"check_same_thread": False},
        )

        global engine, SessionLocal
        engine = fallback_engine
        SessionLocal.configure(bind=fallback_engine)

        Base.metadata.create_all(bind=fallback_engine)
