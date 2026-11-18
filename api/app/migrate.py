"""평범한 SQL 마이그레이션 실행기. migrations/NNN_*.sql 을 순서대로 한 번씩 적용한다.

PostgreSQL 이 아닌 DB(테스트용 SQLite)는 ORM 메타데이터로 테이블을 만든다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from sqlalchemy import text

from . import models  # noqa: F401  (메타데이터 등록)
from .db import Base, get_engine

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# 001 이후 마이그레이션이 추가한 컬럼. 이미 배포된 001_init.sql 은 고치지 않으므로(기존 DB 보존)
# 001 과 모델의 드리프트 검사에서는 이 컬럼들을 빼고 비교한다. 스키마 변경은 항상 "추가"만 한다.
ADDED_COLUMNS: dict[str, dict[str, list[str]]] = {
    "002_customer_registration.sql": {"customers": ["industry", "scenario"]},
}


def schema_sql() -> str:
    """ORM 모델에서 001_init.sql 시점의 PostgreSQL DDL 을 생성한다(드리프트 검사용, 이후 추가 컬럼 제외)."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    later: dict[str, list[str]] = {}
    for tables in ADDED_COLUMNS.values():
        for t, cols in tables.items():
            later.setdefault(t, []).extend(cols)
    parts = []
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect())).strip()
        for col in later.get(table.name, []):
            ddl = re.sub(rf"\n\t{re.escape(col)} [^\n]*", "", ddl)
        parts.append(ddl + ";")
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


def check_live_schema() -> list[str]:
    """실제 DB 의 테이블·컬럼이 ORM 모델과 같은지 비교한다. 차이 목록을 돌려준다(없으면 빈 목록)."""
    from sqlalchemy import inspect

    insp = inspect(get_engine())
    problems = []
    live_tables = set(insp.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in live_tables:
            problems.append(f"테이블 없음: {table.name}")
            continue
        live = {c["name"] for c in insp.get_columns(table.name)}
        want = {c.name for c in table.columns}
        if live != want:
            problems.append(f"{table.name}: DB에만 있음 {sorted(live - want)}, 모델에만 있음 {sorted(want - live)}")
    return problems


if __name__ == "__main__":
    if "--print-schema" in sys.argv:
        sys.stdout.write(schema_sql())
    elif "--check" in sys.argv:
        diffs = check_live_schema()
        print("스키마 검사:", "모델과 일치" if not diffs else "불일치 " + "; ".join(diffs))
        sys.exit(1 if diffs else 0)
    else:
        print("적용된 마이그레이션:", migrate() or "없음(최신)")
