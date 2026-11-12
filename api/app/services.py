"""업무 로직(오케스트레이션). 라우트와 스케줄러 작업이 함께 쓴다."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import docgen, gap, kb, workflow
from .config import get_settings
from .deps import audit
from .engine import classify
from .evidence import EvidenceStore
from .extractor import (LLM_SYSTEM, Doc, build_llm_prompt, extract_mock, extract_single_mock, facts_to_attributes,
                        parse_llm_extraction)
from .golden import run_golden
from .llm.base import LLMError
from .llm.router import ModelRouter, get_router
from .models import (AISystem, Classification, Customer, Document, Engagement, EvidenceItem, Fact, GapReport,
                     GeneratedDocument, GoldenRun, ModelConfig, ReassessmentTask, TechCheck, User)
from .techcheck import run_check


def actor_name(actor: User | str) -> str:
    return actor.email if isinstance(actor, User) else actor


def engagement_of(db: Session, customer: Customer) -> Engagement:
    eng = db.scalars(select(Engagement).where(Engagement.customer_id == customer.id)).first()
    if eng is None:
        eng = Engagement(customer_id=customer.id, state="intake")
        db.add(eng)
        db.flush()
    return eng


# ---------- 자료 접수 ----------

def ingest_document(db: Session, customer: Customer, actor: User | str, *, kind: str, title: str, content: str,
                    data: dict[str, Any] | None = None) -> Document:
    doc = Document(customer_id=customer.id, kind=kind, title=title, content=content, data=data,
                   uploaded_by=actor_name(actor))
    db.add(doc)
    if data and isinstance(data.get("current_state"), dict):
        customer.current_state = {**(customer.current_state or {}), **data["current_state"]}
    eng = engagement_of(db, customer)
    db.flush()
    audit(db, actor, "document.upload", entity="document", entity_id=doc.id, customer_id=customer.id,
          detail={"kind": kind, "title": title, "chars": len(content), "engagement_state": eng.state})
    return doc


# ---------- M2 인벤토리 ----------

def run_inventory(db: Session, customer: Customer, actor: User | str, router: ModelRouter | None = None) -> dict[str, Any]:
    router = router or get_router()
    eng = engagement_of(db, customer)
    rows = db.scalars(select(Document).where(Document.customer_id == customer.id).order_by(Document.id)).all()
    if not rows:
        raise workflow.WorkflowError("접수된 자료가 없습니다. 먼저 자료를 올려 주세요")
    docs = [Doc(d.id, d.title, d.content) for d in rows]
    sel = router.select(db, customer, "inventory_extract")
    note = ""
    provider = sel.provider.name
    if sel.is_mock:
        systems = extract_mock(docs)
        router.record_mock(db, customer, "inventory_extract", sel, "".join(d.content for d in docs),
                           json.dumps([s["attributes"] for s in systems], ensure_ascii=False))
    else:
        try:
            res, info = router.complete(db, customer, "inventory_extract", LLM_SYSTEM, build_llm_prompt(docs), sel=sel,
                                        max_tokens=4000)
            systems = parse_llm_extraction(res.text, docs)
            note = f"비식별화 적용: {info['pii_counts']}" if info["deidentified"] else ""
            if not systems:
                raise ValueError("LLM이 시스템을 찾지 못했습니다")
        except (LLMError, ValueError) as e:
            systems = extract_mock(docs)
            provider = "mock(대체)"
            note = f"LLM 추출 실패로 규칙 기반으로 대체: {e}"
    existing = {s.name: s for s in db.scalars(select(AISystem).where(AISystem.customer_id == customer.id)).all()}
    seen = set()
    out = []
    for s in systems:
        row = existing.get(s["name"])
        if row is None:
            row = AISystem(customer_id=customer.id, name=s["name"])
            db.add(row)
        row.attributes = s["attributes"]
        row.extracted_by = provider
        row.active = True
        db.flush()
        for f in db.scalars(select(Fact).where(Fact.system_id == row.id)).all():
            db.delete(f)
        for f in s["facts"]:
            db.add(Fact(system_id=row.id, field=f["field"], value=f["value"], doc_id=f["doc_id"], quote=f["quote"],
                        span_start=f["span_start"], span_end=f["span_end"], source=f["source"], supported=f["supported"]))
        seen.add(s["name"])
        out.append(row)
    for name, row in existing.items():
        if name not in seen:
            row.active = False
    workflow.move(eng, "inventory_review")
    audit(db, actor, "inventory.extract", entity="customer", entity_id=customer.id, customer_id=customer.id,
          detail={"systems": [s.name for s in out], "provider": provider, "route_reason": sel.reason, "note": note})
    db.flush()
    return {"systems": out, "provider": provider, "route_reason": sel.reason, "note": note}


def update_system_attributes(db: Session, system: AISystem, actor: User, changes: dict[str, Any]) -> AISystem:
    from .engine import FACT_DEFAULTS

    attrs = dict(system.attributes or {})
    for k, v in changes.items():
        if k not in FACT_DEFAULTS:
            continue
        attrs[k] = v
        for f in db.scalars(select(Fact).where(Fact.system_id == system.id, Fact.field == k)).all():
            db.delete(f)
        db.add(Fact(system_id=system.id, field=k, value=v, doc_id=None, quote="컨설턴트가 직접 수정", source="consultant",
                    supported=True))
    system.attributes = attrs
    audit(db, actor, "inventory.edit", entity="ai_system", entity_id=system.id, customer_id=system.customer_id,
          detail={"changes": changes})
    db.flush()
    return system


# ---------- M3 판정 ----------

def active_systems(db: Session, customer_id: int) -> list[AISystem]:
    return list(db.scalars(select(AISystem).where(AISystem.customer_id == customer_id, AISystem.active.is_(True))
                           .order_by(AISystem.id)).all())


def latest_classifications(db: Session, customer_id: int) -> dict[int, Classification]:
    out: dict[int, Classification] = {}
    for c in db.scalars(select(Classification).where(Classification.customer_id == customer_id,
                                                     Classification.status != "superseded")
                        .order_by(Classification.version)).all():
        out[c.system_id] = c
    return out


def run_classify(db: Session, customer: Customer, actor: User | str) -> list[Classification]:
    eng = engagement_of(db, customer)
    workflow.require(eng, "inventory_review", "판정 초안 생성")
    systems = active_systems(db, customer.id)
    if not systems:
        raise workflow.WorkflowError("인벤토리에 AI 시스템이 없습니다")
    version = kb.active_version(db).version
    out = []
    for s in systems:
        prev = db.scalars(select(Classification).where(Classification.system_id == s.id)
                          .order_by(Classification.version.desc())).all()
        for p in prev:
            if p.status != "superseded":
                p.status = "superseded"
        c = Classification(customer_id=customer.id, system_id=s.id, version=(prev[0].version + 1) if prev else 1,
                           status="draft", kb_version=version, result=classify(s.attributes or {}))
        db.add(c)
        out.append(c)
    workflow.move(eng, "classification_draft")
    db.flush()
    audit(db, actor, "classification.draft", entity="customer", entity_id=customer.id, customer_id=customer.id,
          detail={"kb_version": version, "classification_ids": [c.id for c in out]})
    return out


def confirm_classification(db: Session, cls: Classification, actor: User) -> Classification:
    if actor.role != "consultant":
        raise PermissionError("판정 확정은 컨설턴트만 할 수 있습니다")
    if cls.status == "superseded":
        raise workflow.WorkflowError("이미 대체된 판정 버전은 확정할 수 없습니다")
    customer = db.get(Customer, cls.customer_id)
    eng = engagement_of(db, customer)
    if cls.status != "confirmed":
        cls.status = "confirmed"
        cls.confirmed_by = actor.email
        cls.confirmed_at = datetime.now(timezone.utc)
        audit(db, actor, "classification.confirm", entity="classification", entity_id=cls.id,
              customer_id=cls.customer_id, detail={"system_id": cls.system_id, "version": cls.version})
    db.flush()
    latest = latest_classifications(db, cls.customer_id)
    systems = active_systems(db, cls.customer_id)
    if systems and all(s.id in latest and latest[s.id].status == "confirmed" for s in systems):
        if workflow.idx(eng.state) <= workflow.idx("classification_draft"):
            workflow.move(eng, "classification_confirmed")
    return cls


def classified_systems(db: Session, customer_id: int, *, confirmed_only: bool = True) -> list[dict[str, Any]]:
    latest = latest_classifications(db, customer_id)
    out = []
    for s in active_systems(db, customer_id):
        c = latest.get(s.id)
        if c is None or (confirmed_only and c.status != "confirmed"):
            continue
        out.append({"id": s.id, "name": s.name, "attributes": s.attributes or {}, "result": c.result,
                    "classification_id": c.id})
    return out


# ---------- 갭 리포트 ----------

def build_gap_report(db: Session, customer: Customer, actor: User | str) -> GapReport:
    eng = engagement_of(db, customer)
    workflow.require(eng, "classification_confirmed", "갭 리포트 생성")
    systems = classified_systems(db, customer.id)
    if len(systems) != len(active_systems(db, customer.id)):
        raise workflow.WorkflowError("확정되지 않은 판정이 있습니다. 컨설턴트 확정 후 진행하세요")
    version, clauses = kb.active_clauses(db)
    findings = gap.build_findings(systems, customer.current_state or {})
    n = db.scalar(select(func.count(GapReport.id)).where(GapReport.customer_id == customer.id)) or 0
    report = GapReport(customer_id=customer.id, version=n + 1, kb_version=version, findings=findings,
                       html=gap.render_html(customer.name, version, systems, findings, clauses, date.today().isoformat()),
                       created_by=actor_name(actor))
    db.add(report)
    workflow.move(eng, "gap_report")
    db.flush()
    audit(db, actor, "gap_report.create", entity="gap_report", entity_id=report.id, customer_id=customer.id,
          detail={"findings": [f["code"] for f in findings]})
    return report


def latest_gap_report(db: Session, customer_id: int) -> GapReport | None:
    return db.scalars(select(GapReport).where(GapReport.customer_id == customer_id)
                      .order_by(GapReport.version.desc())).first()


# ---------- M4 문서 ----------

def _draft(db: Session, router: ModelRouter, customer: Customer, kind: str, template: list[dict[str, Any]],
           clauses: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    sel = router.select(db, customer, f"doc_{kind}")
    text_in = json.dumps(template, ensure_ascii=False)
    if sel.is_mock:
        router.record_mock(db, customer, f"doc_{kind}", sel, text_in, text_in)
        return docgen.validate_paragraphs(template, clauses), "mock(템플릿)"
    try:
        res, _ = router.complete(db, customer, f"doc_{kind}", docgen.LLM_SYSTEM,
                                 docgen.build_llm_prompt(kind, customer.name, template, clauses), sel=sel, max_tokens=4000)
        return docgen.validate_paragraphs(docgen.parse_llm_paragraphs(res.text), clauses), f"{sel.provider.name}:{sel.provider.model}"
    except (LLMError, ValueError):
        return docgen.validate_paragraphs(template, clauses), "mock(템플릿, LLM 실패 대체)"


def generate_documents(db: Session, customer: Customer, actor: User | str,
                       router: ModelRouter | None = None) -> list[GeneratedDocument]:
    router = router or get_router()
    eng = engagement_of(db, customer)
    workflow.require(eng, "gap_report", "문서 초안 생성")
    systems = classified_systems(db, customer.id)
    version, clauses = kb.active_clauses(db)
    report = latest_gap_report(db, customer.id)
    plans: list[tuple[str, int | None, str, list[dict[str, Any]] | None]] = []
    if any(s["result"]["art31"]["prior_notice"] for s in systems):
        plans.append(("notice_texts", None, "사전 고지 문구 3종", docgen.notice_texts(customer.name, systems)))
        plans.append(("tos_clause", None, "이용약관 AI 조항 초안", docgen.tos_clause(customer.name, systems)))
    for s in systems:
        if s["result"]["high_impact"]["status"] == "candidate":
            plans.append(("risk_policy", s["id"], f"위험관리 정책 골격 — {s['name']}", docgen.risk_policy(customer.name, s)))
            plans.append(("impact_checklist", s["id"], f"영향평가 체크리스트 — {s['name']}",
                          docgen.impact_checklist(customer.name, s)))
    for d in db.scalars(select(GeneratedDocument).where(GeneratedDocument.customer_id == customer.id,
                                                        GeneratedDocument.status != "superseded",
                                                        GeneratedDocument.kind != "monthly_report")).all():
        d.status = "superseded"
    out = []

    def next_version(kind: str, system_id: int | None) -> int:
        q = select(func.count(GeneratedDocument.id)).where(GeneratedDocument.customer_id == customer.id,
                                                           GeneratedDocument.kind == kind)
        q = q.where(GeneratedDocument.system_id == system_id) if system_id else q.where(GeneratedDocument.system_id.is_(None))
        return int(db.scalar(q) or 0) + 1

    for kind, system_id, title, template in plans:
        paragraphs, provider = _draft(db, router, customer, kind, template or [], clauses)
        doc = GeneratedDocument(customer_id=customer.id, system_id=system_id, kind=kind, title=title,
                                version=next_version(kind, system_id), paragraphs=paragraphs, provider=provider,
                                html=docgen.render_html(title, customer.name, version, paragraphs, clauses, provider))
        db.add(doc)
        out.append(doc)
    if report:
        doc = GeneratedDocument(customer_id=customer.id, kind="gap_report", title="갭 리포트",
                                version=next_version("gap_report", None), paragraphs=[], provider="규칙(결정적)",
                                html=report.html)
        db.add(doc)
        out.append(doc)
    workflow.move(eng, "documents_draft")
    db.flush()
    audit(db, actor, "documents.generate", entity="customer", entity_id=customer.id, customer_id=customer.id,
          detail={"documents": [{"id": d.id, "kind": d.kind} for d in out]})
    return out


def current_documents(db: Session, customer_id: int) -> list[GeneratedDocument]:
    return list(db.scalars(select(GeneratedDocument).where(GeneratedDocument.customer_id == customer_id,
                                                           GeneratedDocument.status != "superseded")
                           .order_by(GeneratedDocument.id)).all())


def approve_documents(db: Session, customer: Customer, actor: User) -> list[GeneratedDocument]:
    if actor.role != "consultant":
        raise PermissionError("승인은 컨설턴트만 할 수 있습니다")
    eng = engagement_of(db, customer)
    workflow.require(eng, "documents_draft", "문서 승인")
    docs = [d for d in current_documents(db, customer.id) if d.kind != "monthly_report"]
    if not docs:
        raise workflow.WorkflowError("승인할 문서 초안이 없습니다")
    now = datetime.now(timezone.utc)
    for d in docs:
        d.status = "approved"
        d.approved_by = actor.email
        d.approved_at = now
    workflow.move(eng, "approved")
    audit(db, actor, "documents.approve", entity="customer", entity_id=customer.id, customer_id=customer.id,
          detail={"document_ids": [d.id for d in docs],
                  "unsupported_paragraphs": sum(1 for d in docs for p in d.paragraphs if not p.get("supported", True))})
    db.flush()
    return docs


# ---------- M6 증적 ----------

def store_evidence_package(db: Session, customer: Customer, actor: User | str,
                           store: EvidenceStore | None = None) -> list[EvidenceItem]:
    store = store or EvidenceStore()
    eng = engagement_of(db, customer)
    workflow.require(eng, "approved", "증적 보관")
    who = actor_name(actor)
    items = []
    systems = classified_systems(db, customer.id)
    payload = json.dumps({"customer": customer.name, "systems": systems}, ensure_ascii=False, indent=1, default=str)
    items.append(store.append(db, customer.id, kind="classification", title="확정 판정서(JSON)", data=payload,
                              content_type="application/json", created_by=who,
                              meta={"classification_ids": [s["classification_id"] for s in systems]}))
    for d in current_documents(db, customer.id):
        if d.status != "approved":
            continue
        items.append(store.append(db, customer.id, kind=f"document:{d.kind}", title=f"{d.title} (승인본 v{d.version})",
                                  data=d.html, content_type="text/html; charset=utf-8", created_by=who,
                                  meta={"document_id": d.id, "approved_by": d.approved_by}))
    workflow.move(eng, "evidence_stored")
    audit(db, actor, "evidence.store_package", entity="customer", entity_id=customer.id, customer_id=customer.id,
          detail={"evidence_ids": [i.id for i in items], "head_hash": items[-1].chain_hash})
    db.flush()
    return items


# ---------- M5 기술 점검 ----------

def run_tech_check(db: Session, customer: Customer, actor: User | str, store: EvidenceStore | None = None,
                   client: Any = None) -> TechCheck:
    s = get_settings()
    cfg = dict(customer.tech_targets or {})
    base = (cfg.get("base_url") or s.demo_service_url).rstrip("/")
    results = run_check(base, cfg, s.tech_check_allowlist, client=client)
    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed
    tc = TechCheck(customer_id=customer.id, target=base, results=results, passed=passed, failed=failed,
                   triggered_by=actor_name(actor))
    db.add(tc)
    db.flush()
    store = store or EvidenceStore()
    item = store.append(db, customer.id, kind="tech_check", title=f"기술 점검 결과 #{tc.id} ({base})",
                        data=json.dumps({"target": base, "results": results, "passed": passed, "failed": failed},
                                        ensure_ascii=False, indent=1),
                        content_type="application/json", created_by=actor_name(actor), meta={"tech_check_id": tc.id})
    tc.evidence_id = item.id
    audit(db, actor, "tech_check.run", entity="tech_check", entity_id=tc.id, customer_id=customer.id,
          detail={"target": base, "passed": passed, "failed": failed})
    db.flush()
    return tc


# ---------- M9 게이트웨이 로그 ----------

def ingest_gateway_logs(db: Session, customer: Customer, actor: User | str, body: str,
                        store: EvidenceStore | None = None) -> dict[str, Any]:
    lines = [ln for ln in body.splitlines() if ln.strip()]
    ok = bad = 0
    models: dict[str, int] = {}
    for ln in lines:
        try:
            rec = json.loads(ln)
            if not isinstance(rec, dict):
                raise ValueError
            ok += 1
            m = str(rec.get("model", "unknown"))
            models[m] = models.get(m, 0) + 1
        except ValueError:
            bad += 1
    if ok == 0:
        raise ValueError("유효한 JSON Lines 레코드가 없습니다")
    store = store or EvidenceStore()
    item = store.append(db, customer.id, kind="gateway_log", title=f"AI 게이트웨이 로그 {ok}건",
                        data=body, content_type="application/x-ndjson", created_by=actor_name(actor),
                        meta={"records": ok, "invalid_lines": bad, "models": models})
    audit(db, actor, "gateway_logs.ingest", entity="evidence", entity_id=item.id, customer_id=customer.id,
          detail={"records": ok, "invalid_lines": bad})
    db.flush()
    return {"evidence_id": item.id, "records": ok, "invalid_lines": bad, "models": models, "sha256": item.sha256}


# ---------- 골든셋 ----------

def golden_regression(db: Session, router: ModelRouter | None = None) -> GoldenRun:
    router = router or get_router()
    sel = router.select(db, None, "golden_regression")
    if sel.is_mock:
        result = run_golden()
    else:
        def extract(name: str, text: str) -> dict[str, Any]:
            doc = Doc(0, name, text)
            res, _ = router.complete(db, None, "golden_regression", LLM_SYSTEM, build_llm_prompt([doc], name), sel=sel,
                                     max_tokens=1500)
            systems = parse_llm_extraction(res.text, [doc])
            return systems[0]["attributes"] if systems else facts_to_attributes([])

        result = run_golden(extract)
    name = f"{sel.provider.name}:{sel.provider.model}"
    run = GoldenRun(config_name=name, provider=sel.provider.name, total=result["total"], matched=result["matched"],
                    rate=result["rate"], engine_rate=result["engine_rate"], threshold=result["threshold"],
                    passed=result["passed"], mismatches=result["mismatches"])
    db.add(run)
    cfg = db.scalars(select(ModelConfig).where(ModelConfig.name == name)).first()
    if cfg is None:
        cfg = ModelConfig(name=name, provider=sel.provider.name, model=sel.provider.model)
        db.add(cfg)
    cfg.status = "승격 가능" if result["passed"] else "승격 차단"
    cfg.last_rate = result["rate"]
    cfg.updated_at = datetime.now(timezone.utc)
    db.flush()
    return run


def open_task_count(db: Session, customer_id: int | None = None) -> int:
    q = select(func.count(ReassessmentTask.id)).where(ReassessmentTask.status == "open")
    if customer_id is not None:
        q = q.where(ReassessmentTask.customer_id == customer_id)
    return int(db.scalar(q) or 0)


__all__ = [n for n in dir() if not n.startswith("_")]
_ = extract_single_mock  # 재노출(테스트 편의)
