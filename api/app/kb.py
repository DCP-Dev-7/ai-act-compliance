"""M1 법령 지식베이스: 버전 관리되는 조문(clause) 단위 KB.

모든 법령 내용은 '요약 — 원문 확인 필요'이며, 원문 문장을 그대로 싣지 않는다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import DATA_DIR
from .models import ControlMapping, KBClause, KBVersion

KB_V1_PATH = DATA_DIR / "kb_v1.json"
KB_V2_SIM_PATH = DATA_DIR / "kb_v2_simulated.json"
SUMMARY_LABEL = "요약 — 원문 확인 필요"
MAPPING_LABEL = "초안 매핑 — 전문가 검증 필요"


def load_file(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def clause_hash(c: dict[str, Any]) -> str:
    canon = json.dumps(
        {
            "article": c["article"],
            "title": c["title"],
            "summary": c["summary"],
            "obligations": c.get("obligations", []),
            "applies_when": c.get("applies_when"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def materialize(data: dict[str, Any], base_clauses: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """전체 clause 목록을 만든다. 패치 형식(base/changed/added/removed)이면 base에 적용한다."""
    if "clauses" in data:
        return [dict(c) for c in data["clauses"]]
    if base_clauses is None:
        raise ValueError("패치 형식 KB에는 base 버전의 조문이 필요합니다")
    removed = set(data.get("removed", []))
    changed = {c["clause_id"]: c for c in data.get("changed", [])}
    out = []
    for c in base_clauses:
        if c["clause_id"] in removed:
            continue
        out.append(dict(changed.get(c["clause_id"], c)))
    out.extend(dict(c) for c in data.get("added", []))
    return out


def diff_clauses(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    o = {c["clause_id"]: c for c in old}
    n = {c["clause_id"]: c for c in new}
    added = [n[k] for k in n if k not in o]
    removed = [o[k] for k in o if k not in n]
    changed = []
    for k in n:
        if k in o and clause_hash(o[k]) != clause_hash(n[k]):
            changed.append({"clause_id": k, "before": o[k], "after": n[k]})
    return {"added": added, "changed": changed, "removed": removed}


def _clause_to_dict(c: KBClause) -> dict[str, Any]:
    return {
        "clause_id": c.clause_id,
        "article": c.article,
        "title": c.title,
        "summary": c.summary,
        "obligations": c.obligations or [],
        "sources": c.sources or [],
        "applies_when": c.applies_when,
        "content_hash": c.content_hash,
        "label": SUMMARY_LABEL,
    }


def get_clauses(db: Session, version: str) -> list[dict[str, Any]]:
    rows = db.scalars(select(KBClause).where(KBClause.kb_version == version).order_by(KBClause.position)).all()
    return [_clause_to_dict(r) for r in rows]


def active_version(db: Session) -> KBVersion:
    v = db.scalars(select(KBVersion).where(KBVersion.is_active.is_(True))).first()
    if v is None:
        raise RuntimeError("활성 KB 버전이 없습니다. 시드를 먼저 실행하세요.")
    return v


def active_clauses(db: Session) -> tuple[str, dict[str, dict[str, Any]]]:
    v = active_version(db)
    return v.version, {c["clause_id"]: c for c in get_clauses(db, v.version)}


def store_version(db: Session, data: dict[str, Any], *, activate: bool = True) -> dict[str, Any]:
    """KB 버전을 DB에 적재하고 (활성 버전 대비) diff를 돌려준다. 이미 있으면 ValueError."""
    version = data["version"]
    if db.scalars(select(KBVersion).where(KBVersion.version == version)).first():
        raise ValueError(f"KB 버전 {version} 은(는) 이미 적용되어 있습니다")
    prev = db.scalars(select(KBVersion).where(KBVersion.is_active.is_(True))).first()
    prev_clauses = get_clauses(db, prev.version) if prev else []
    base_clauses = None
    if "clauses" not in data:
        base_clauses = get_clauses(db, data["base"])
        if not base_clauses:
            raise ValueError(f"base 버전 {data['base']} 이(가) 없습니다")
    clauses = materialize(data, base_clauses)
    diff = diff_clauses(prev_clauses, clauses) if prev else {"added": clauses, "changed": [], "removed": []}
    if activate and prev:
        prev.is_active = False
    db.add(
        KBVersion(
            version=version,
            label=data.get("label", version),
            effective_date=data.get("effective_date", ""),
            notice=data.get("notice", SUMMARY_LABEL),
            is_active=activate,
        )
    )
    for i, c in enumerate(clauses):
        db.add(
            KBClause(
                kb_version=version,
                clause_id=c["clause_id"],
                article=c["article"],
                title=c["title"],
                summary=c["summary"],
                obligations=c.get("obligations", []),
                sources=c.get("sources", []),
                applies_when=c.get("applies_when"),
                content_hash=clause_hash(c),
                position=i,
            )
        )
    mappings = data.get("mappings")
    if mappings is None and prev:
        mappings = [
            {"clause_id": m.clause_id, "isms_p": m.isms_p, "iso42001": m.iso42001, "note": m.note}
            for m in db.scalars(select(ControlMapping).where(ControlMapping.kb_version == prev.version)).all()
        ]
    for m in mappings or []:
        db.add(ControlMapping(kb_version=version, clause_id=m["clause_id"], isms_p=m["isms_p"],
                              iso42001=m["iso42001"], note=m.get("note", "")))
    db.flush()
    return {"from": prev.version if prev else None, "to": version, **diff}


def seed_kb(db: Session) -> None:
    if db.scalars(select(KBVersion)).first() is None:
        store_version(db, load_file(KB_V1_PATH))


def file_clauses_v1() -> dict[str, dict[str, Any]]:
    """DB 없이 쓰는 경로(골든셋·단위 테스트)용."""
    return {c["clause_id"]: c for c in load_file(KB_V1_PATH)["clauses"]}
