from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import AuditLog, Customer, User
from .security import decode_token

ROLE_LABELS = {"customer": "고객 담당자", "consultant": "컨설턴트", "ops": "운영자"}


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(get_settings().cookie_name)
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    payload = decode_token(token) if token else None
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "사용자를 찾을 수 없습니다")
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            allowed = ", ".join(ROLE_LABELS[r] for r in roles)
            raise HTTPException(403, f"권한이 없습니다. 이 작업은 {allowed}만 할 수 있습니다")
        return user

    return dep


def customer_for(db: Session, user: User, customer_id: int) -> Customer:
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(404, "고객사를 찾을 수 없습니다")
    if user.role == "customer" and user.customer_id != c.id:
        raise HTTPException(403, "다른 고객사의 정보에는 접근할 수 없습니다")
    return c


def audit(db: Session, actor: User | str, action: str, *, entity: str = "", entity_id: object = "",
          customer_id: int | None = None, detail: dict | None = None) -> None:
    if isinstance(actor, User):
        name, role = actor.email, actor.role
    else:
        name, role = actor, "system"
    db.add(AuditLog(actor=name, role=role, action=action, entity=entity, entity_id=str(entity_id),
                    customer_id=customer_id, detail=detail or {}))
