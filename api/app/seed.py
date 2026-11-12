"""시드: 법령 KB v1, 가상 고객 A사, 데모 계정 3개. 여러 번 실행해도 안전하다(idempotent)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import kb
from .config import DATA_DIR, get_settings
from .db import session_factory
from .models import Customer, Engagement, ModelConfig, User
from .security import hash_password

SEED_DIR = DATA_DIR / "seed"
DEMO_PASSWORD = "demo1234"
CUSTOMER_NAME = "A사 (가상)"

SAMPLE_DOCS: list[dict[str, Any]] = [
    {"kind": "questionnaire", "title": "[가상] 사전 설문 응답", "file": "questionnaire.txt",
     "data": {"current_state": {"has_prior_notice": False, "labels_outputs_visible": True, "embeds_metadata": False,
                                "tos_has_ai_clause": False, "risk_policy": False, "explanation_method": False,
                                "human_oversight_killswitch": False, "doc_retention_5y": False}}},
    {"kind": "service_intro", "title": "[가상] 서비스 소개서", "file": "service_intro.txt", "data": None},
    {"kind": "tos", "title": "[가상] 이용약관", "file": "tos.txt", "data": None},
    {"kind": "dev_doc", "title": "[가상] 개발 문서 발췌", "file": "dev_doc.txt", "data": None},
]


def sample_docs() -> list[dict[str, Any]]:
    return [{"kind": d["kind"], "title": d["title"], "data": d["data"],
             "content": (SEED_DIR / d["file"]).read_text(encoding="utf-8")} for d in SAMPLE_DOCS]


def seed(db: Session) -> None:
    kb.seed_kb(db)
    s = get_settings()
    cust = db.scalars(select(Customer).where(Customer.name == CUSTOMER_NAME)).first()
    if cust is None:
        cust = Customer(
            name=CUSTOMER_NAME,
            description="[가상 데이터] 직원 40명. 생성형 AI로 상품 이미지를 만들어 주는 B2C 서비스 '상품 페이지 도우미' 운영. 외부 LLM 2종 사용.",
            employees=40, is_synthetic=True, allow_external=True, monthly_budget_usd=50.0, subscribed=True,
            current_state={},
            tech_targets={"base_url": s.demo_service_url, "notice_pages": ["/", "/generate.html"],
                          "image_pages": ["/generate.html"], "generated_image_prefix": "/generated/"},
        )
        db.add(cust)
        db.flush()
        db.add(Engagement(customer_id=cust.id, state="intake"))
    for email, name, role, cid in [
        ("a-company@demo", "A사 담당자(가상)", "customer", cust.id),
        ("consultant@demo", "컨설턴트(가상)", "consultant", None),
        ("ops@demo", "운영자(가상)", "ops", None),
    ]:
        if db.scalars(select(User).where(User.email == email)).first() is None:
            db.add(User(email=email, name=name, role=role, customer_id=cid, password_hash=hash_password(DEMO_PASSWORD)))
    if db.scalars(select(ModelConfig)).first() is None:
        db.add(ModelConfig(name="mock:mock-rules-1", provider="mock", model="mock-rules-1", status="후보"))
    db.commit()


if __name__ == "__main__":
    with session_factory()() as db:
        seed(db)
    print("시드 완료: KB v1, 고객 'A사 (가상)', 데모 계정 3개 (비밀번호 demo1234)")
