from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    employees: Mapped[int] = mapped_column(Integer, default=0)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_external: Mapped[bool] = mapped_column(Boolean, default=True)
    monthly_budget_usd: Mapped[float] = mapped_column(Float, default=50.0)
    subscribed: Mapped[bool] = mapped_column(Boolean, default=True)
    current_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tech_targets: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # 002 마이그레이션에서 추가(기존 DB 호환을 위해 DB 기본값을 둔다)
    industry: Mapped[str] = mapped_column(String(60), default="", server_default="")
    scenario: Mapped[str] = mapped_column(String(40), default="", server_default="")  # "" = 빈 고객, a = 시드 A사, b~e = 연습 시나리오


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))  # customer | consultant | ops
    password_hash: Mapped[str] = mapped_column(String(300))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)


class Engagement(Base):
    __tablename__ = "engagements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), unique=True)
    state: Mapped[str] = mapped_column(String(40), default="intake")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Document(Base):
    """고객이 제출한 자료(텍스트)."""

    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    kind: Mapped[str] = mapped_column(String(40))  # questionnaire | service_intro | tos | dev_doc | other
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AISystem(Base):
    __tablename__ = "ai_systems"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    name: Mapped[str] = mapped_column(String(200))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    extracted_by: Mapped[str] = mapped_column(String(60), default="mock")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Fact(Base):
    """추출된 사실 1건 = 속성 + 값 + 인용 근거(문서 id, 인용 구간)."""

    __tablename__ = "facts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("ai_systems.id"))
    field: Mapped[str] = mapped_column(String(60))
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    doc_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    quote: Mapped[str] = mapped_column(Text, default="")
    span_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="extracted")  # extracted | default | consultant
    supported: Mapped[bool] = mapped_column(Boolean, default=True)


class Classification(Base):
    __tablename__ = "classifications"
    __table_args__ = (UniqueConstraint("system_id", "version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    system_id: Mapped[int] = mapped_column(ForeignKey("ai_systems.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | confirmed | superseded
    kb_version: Mapped[str] = mapped_column(String(40))
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    confirmed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KBVersion(Base):
    __tablename__ = "kb_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(40), unique=True)
    label: Mapped[str] = mapped_column(String(300))
    effective_date: Mapped[str] = mapped_column(String(20), default="")
    notice: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KBClause(Base):
    __tablename__ = "kb_clauses"
    __table_args__ = (UniqueConstraint("kb_version", "clause_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kb_version: Mapped[str] = mapped_column(String(40))
    clause_id: Mapped[str] = mapped_column(String(60))
    article: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    obligations: Mapped[list[str]] = mapped_column(JSON, default=list)
    sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    applies_when: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer, default=0)


class ControlMapping(Base):
    __tablename__ = "control_mappings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kb_version: Mapped[str] = mapped_column(String(40))
    clause_id: Mapped[str] = mapped_column(String(60))
    isms_p: Mapped[str] = mapped_column(Text)
    iso42001: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text, default="")


class GapReport(Base):
    __tablename__ = "gap_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    kb_version: Mapped[str] = mapped_column(String(40))
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    html: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GeneratedDocument(Base):
    __tablename__ = "generated_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    system_id: Mapped[int | None] = mapped_column(ForeignKey("ai_systems.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | approved | superseded
    paragraphs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    html: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(60), default="mock")
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceItem(Base):
    """증적 색인(조회용). 원본과 원장(ledger)은 증적 백엔드에 write-once로 보관된다."""

    __tablename__ = "evidence_items"
    __table_args__ = (UniqueConstraint("customer_id", "seq"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(String(64))
    chain_hash: Mapped[str] = mapped_column(String(64))
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChangeEvent(Base):
    __tablename__ = "change_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(30))  # law_change | customer_release
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReassessmentTask(Base):
    __tablename__ = "reassessment_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    system_id: Mapped[int | None] = mapped_column(ForeignKey("ai_systems.id"), nullable=True)
    classification_id: Mapped[int | None] = mapped_column(ForeignKey("classifications.id"), nullable=True)
    change_event_id: Mapped[int] = mapped_column(ForeignKey("change_events.id"))
    reason: Mapped[str] = mapped_column(Text)
    clause_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | done
    resolved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(60), default="")
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class TechCheck(Base):
    __tablename__ = "tech_checks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    target: Mapped[str] = mapped_column(String(300))
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    evidence_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LLMUsage(Base):
    __tablename__ = "llm_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task: Mapped[str] = mapped_column(String(60))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobRun(Base):
    __tablename__ = "job_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job: Mapped[str] = mapped_column(String(60))
    trigger: Mapped[str] = mapped_column(String(20), default="schedule")  # schedule | manual
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | ok | failed
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GoldenRun(Base):
    __tablename__ = "golden_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    config_name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(40))
    total: Mapped[int] = mapped_column(Integer)
    matched: Mapped[int] = mapped_column(Integer)
    rate: Mapped[float] = mapped_column(Float)
    engine_rate: Mapped[float] = mapped_column(Float, default=0.0)
    threshold: Mapped[float] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean)
    mismatches: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class ModelConfig(Base):
    """모델·프롬프트 구성. 골든셋 회귀가 임계 미만이면 status가 '승격 차단'이 된다."""

    __tablename__ = "model_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40), default="p1")
    status: Mapped[str] = mapped_column(String(20), default="후보")  # 후보 | 승격 가능 | 승격 차단
    last_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
