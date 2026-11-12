"""M7 변경 감지: (a) 법령 KB 버전 변경 → 조문 diff → 영향받는 확정 판정 → 재평가 작업, (b) 고객 릴리스 웹훅."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import kb
from .models import AISystem, ChangeEvent, Classification, ReassessmentTask


def matches(applies_when: dict[str, Any] | None, attrs: dict[str, Any]) -> bool:
    if not applies_when:
        return True
    for k, want in applies_when.items():
        have = attrs.get(k)
        if isinstance(want, list):
            have_set = set(have) if isinstance(have, list) else {have}
            if not have_set & set(want):
                return False
        elif have != want:
            return False
    return True


def affected_by_diff(diff: dict[str, Any], classifications: list[tuple[Classification, AISystem]]) -> list[dict[str, Any]]:
    """diff 와 (확정 판정, 시스템) 목록으로 재평가 대상을 계산한다(순수 함수)."""
    out = []
    for cls, system in classifications:
        attrs = system.attributes or {}
        applicable = set(cls.result.get("applicable_articles", []))
        reasons: list[str] = []
        clause_ids: list[str] = []
        for ch in diff.get("changed", []):
            cid = ch["clause_id"]
            if cid in applicable and matches(ch["after"].get("applies_when"), attrs):
                reasons.append(f"적용 조문 변경: {ch['after']['article']} {ch['after']['title']}")
                clause_ids.append(cid)
        for c in diff.get("removed", []):
            if c["clause_id"] in applicable:
                reasons.append(f"적용 조문 삭제: {c['article']} {c['title']}")
                clause_ids.append(c["clause_id"])
        for c in diff.get("added", []):
            if c.get("applies_when") and matches(c["applies_when"], attrs):
                reasons.append(f"신규 기준 적용 가능: {c['article']} {c['title']}")
                clause_ids.append(c["clause_id"])
        if reasons:
            out.append({"classification": cls, "system": system, "reasons": reasons, "clause_ids": clause_ids})
    return out


def confirmed_classifications(db: Session, customer_id: int | None = None) -> list[tuple[Classification, AISystem]]:
    q = (select(Classification, AISystem).join(AISystem, AISystem.id == Classification.system_id)
         .where(Classification.status == "confirmed", AISystem.active.is_(True)))
    if customer_id is not None:
        q = q.where(Classification.customer_id == customer_id)
    return [(c, s) for c, s in db.execute(q).all()]


def apply_law_change(db: Session, data: dict[str, Any], actor: str) -> dict[str, Any]:
    targets = confirmed_classifications(db)  # 새 버전 적용 전의 확정 판정
    diff = kb.store_version(db, data)
    event = ChangeEvent(
        type="law_change", title=data.get("label", data["version"]), created_by=actor,
        payload={"from": diff["from"], "to": diff["to"],
                 "added": [c["clause_id"] for c in diff["added"]],
                 "changed": [c["clause_id"] for c in diff["changed"]],
                 "removed": [c["clause_id"] for c in diff["removed"]],
                 "diff": diff},
    )
    db.add(event)
    db.flush()
    tasks = []
    for a in affected_by_diff(diff, targets):
        t = ReassessmentTask(customer_id=a["classification"].customer_id, system_id=a["system"].id,
                             classification_id=a["classification"].id, change_event_id=event.id,
                             reason=" / ".join(a["reasons"]), clause_ids=a["clause_ids"])
        db.add(t)
        tasks.append(t)
    db.flush()
    return {"event": event, "tasks": tasks, "diff": diff}


def record_release(db: Session, customer_id: int, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    event = ChangeEvent(type="customer_release", customer_id=customer_id,
                        title=f"고객 릴리스 {payload.get('version', '')}".strip(), payload=payload, created_by=actor)
    db.add(event)
    db.flush()
    q = select(AISystem).where(AISystem.customer_id == customer_id, AISystem.active.is_(True))
    systems = db.scalars(q).all()
    name = (payload.get("system_name") or "").strip()
    matched = [s for s in systems if s.name == name] if name else systems
    tasks = []
    for s in matched or systems:
        t = ReassessmentTask(customer_id=customer_id, system_id=s.id, change_event_id=event.id,
                             reason=f"고객 릴리스({payload.get('version', '버전 미상')}): {payload.get('notes', '변경 내용 미기재')}",
                             clause_ids=[])
        db.add(t)
        tasks.append(t)
    if not systems:
        t = ReassessmentTask(customer_id=customer_id, system_id=None, change_event_id=event.id,
                             reason="고객 릴리스 접수 — 인벤토리 미작성 상태, 인벤토리 추출부터 필요", clause_ids=[])
        db.add(t)
        tasks.append(t)
    db.flush()
    return {"event": event, "tasks": tasks}
