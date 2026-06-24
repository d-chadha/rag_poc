"""
db/session_factory.py
---------------------
SQLAlchemy engine + session factory for the NEXUS employees database.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import EMPLOYEES_DB_URL

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            EMPLOYEES_DB_URL,
            connect_args={"check_same_thread": False},  # SQLite-safe
            echo=False,
        )
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


def get_db_session() -> Session:
    """Return a new SQLAlchemy Session. Caller is responsible for closing it."""
    return get_session_factory()()
