"""M8 워크플로: 계약(engagement) 단위 상태 기계."""
from __future__ import annotations

from datetime import datetime, timezone

from .models import Engagement

STATES = [
    "intake", "inventory_review", "classification_draft", "classification_confirmed",
    "gap_report", "documents_draft", "approved", "evidence_stored",
]
STATE_LABELS = {
    "intake": "자료 접수", "inventory_review": "인벤토리 검토", "classification_draft": "판정 초안",
    "classification_confirmed": "판정 확정", "gap_report": "갭 리포트", "documents_draft": "문서 초안",
    "approved": "승인 완료", "evidence_stored": "증적 보관",
}


class WorkflowError(RuntimeError):
    pass


def idx(state: str) -> int:
    return STATES.index(state)


def require(eng: Engagement, min_state: str, action: str) -> None:
    """현재 상태가 min_state 이상이어야 action 을 할 수 있다(단계 건너뛰기 금지)."""
    if idx(eng.state) < idx(min_state):
        raise WorkflowError(
            f"'{action}'은(는) '{STATE_LABELS[min_state]}' 단계 이후에만 할 수 있습니다 (현재: {STATE_LABELS[eng.state]})")


def move(eng: Engagement, state: str) -> None:
    """상태 이동. 앞 단계 작업을 다시 하면(재평가 등) 그 단계로 되돌아간다."""
    if state not in STATES:
        raise WorkflowError(f"알 수 없는 상태: {state}")
    eng.state = state
    eng.updated_at = datetime.now(timezone.utc)
