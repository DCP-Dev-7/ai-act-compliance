from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine(url: str | None = None, **kwargs):
    """엔진을 (재)초기화한다. 테스트에서는 SQLite URL을 넘긴다."""
    global _engine, _SessionLocal
    url = url or get_settings().database_url
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool

        kwargs.setdefault("connect_args", {"check_same_thread": False})
        kwargs.setdefault("poolclass", StaticPool)
    else:
        kwargs.setdefault("pool_pre_ping", True)
    _engine = create_engine(url, **kwargs)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine():
    if _engine is None:
        init_engine()
    return _engine


def session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Iterator[Session]:
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()
