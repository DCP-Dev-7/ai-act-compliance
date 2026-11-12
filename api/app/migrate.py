"""평범한 SQL 마이그레이션 실행기. migrations/NNN_*.sql 을 순서대로 한 번씩 적용한다.

PostgreSQL 이 아닌 DB(테스트용 SQLite)는 ORM 메타데이터로 테이블을 만든다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

from . import models  # noqa: F401  (메타데이터 등록)
from .db import Base, get_engine

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def schema_sql() -> str:
    """ORM 모델에서 PostgreSQL DDL 을 생성한다(001_init.sql 생성·드리프트 검사용)."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    parts = []
    for table in Base.metadata.sorted_tables:
        parts.append(str(CreateTable(table).compile(dialect=postgresql.dialect())).strip() + ";")
    return "-- ORM 모델에서 생성됨 (python -m app.migrate --print-schema). 직접 수정하지 말 것.\n\n" + "\n\n".join(parts) + "\n"


def migrate() -> list[str]:
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        Base.metadata.create_all(engine)
        return ["(non-postgres) create_all"]
    applied = []
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())"))
        conn.execute(text("SELECT pg_advisory_xact_lock(724001)"))
        done = {r[0] for r in conn.execute(text("SELECT name FROM schema_migrations"))}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            conn.exec_driver_sql(path.read_text(encoding="utf-8"))
            conn.execute(text("INSERT INTO schema_migrations (name) VALUES (:n)"), {"n": path.name})
            applied.append(path.name)
    return applied


if __name__ == "__main__":
    if "--print-schema" in sys.argv:
        sys.stdout.write(schema_sql())
    else:
        print("적용된 마이그레이션:", migrate() or "없음(최신)")
