from __future__ import annotations

import hmac
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import changes, jobs, kb, services, workflow
from .config import get_settings
from .db import get_db
from .deps import ROLE_LABELS, audit, current_user, customer_for, require_roles
from .docgen import DOC_KIND_LABELS
from .engine import DOMAIN_LABELS
from .evidence import EvidenceStore, WriteOnceViolation, evidence_count
from .gap import STATE_LABELS as GAP_STATE_LABELS
from .llm.base import BudgetExceeded, PolicyViolation
from .llm.router import get_router
from .models import (AISystem, AuditLog, ChangeEvent, Classification, ControlMapping, Customer, Document,
                     EvidenceItem, Fact, GeneratedDocument, GoldenRun, JobRun, KBVersion, LLMUsage, ModelConfig,
                     ReassessmentTask, TechCheck, User)
from .security import create_token, verify_password
from .seed import sample_docs
from .techcheck import TargetNotAllowed

BANNER = "가상 데이터 · 법률 자문 아님"
_http_counts: dict[str, int] = {}
_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if get_settings().scheduler_enabled:
        jobs.start_scheduler()
    yield
    jobs.stop_scheduler()


app = FastAPI(title="AI 기본법 준수 플랫폼 API (데모)", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(get_settings().cors_origins), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def count_requests(request: Request, call_next):
    response = await call_next(request)
    key = f"{request.method} {response.status_code // 100}xx"
    with _lock:
        _http_counts[key] = _http_counts.get(key, 0) + 1
    return response


@app.exception_handler(workflow.WorkflowError)
async def _wf(_: Request, e: workflow.WorkflowError):
    return JSONResponse({"detail": str(e)}, status_code=409)


@app.exception_handler(PermissionError)
async def _perm(_: Request, e: PermissionError):
    return JSONResponse({"detail": str(e)}, status_code=403)


@app.exception_handler(PolicyViolation)
async def _policy(_: Request, e: PolicyViolation):
    return JSONResponse({"detail": str(e)}, status_code=403)


@app.exception_handler(BudgetExceeded)
async def _budget(_: Request, e: BudgetExceeded):
    return JSONResponse({"detail": str(e)}, status_code=402)


@app.exception_handler(TargetNotAllowed)
async def _target(_: Request, e: TargetNotAllowed):
    return JSONResponse({"detail": str(e)}, status_code=400)


@app.exception_handler(WriteOnceViolation)
async def _wo(_: Request, e: WriteOnceViolation):
    return JSONResponse({"detail": str(e)}, status_code=409)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def llm_status(db: Session, customer: Customer | None = None) -> dict[str, Any]:
    r = get_router()
    configured = r.configured_name()
    out: dict[str, Any] = {"configured": configured, "model": r.provider(configured).model,
                           "internal_endpoint_configured": r.has_internal()}
    if customer is not None:
        sel = r.select(db, customer, "status")
        out.update({"effective": sel.provider.name, "effective_model": sel.provider.model, "route_reason": sel.reason})
    return out


# ---------------- 공용 ----------------

@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok", "time": iso(datetime.now(timezone.utc))}
    except Exception as e:
        return JSONResponse({"status": "degraded", "db": f"error: {type(e).__name__}"}, status_code=503)


@app.get("/metrics", response_class=PlainTextResponse)
def metrics(db: Session = Depends(get_db)):
    lines = ["# HELP aiact_http_requests_total HTTP 요청 수", "# TYPE aiact_http_requests_total counter"]
    with _lock:
        for k, v in sorted(_http_counts.items()):
            method, cls = k.split(" ")
            lines.append(f'aiact_http_requests_total{{method="{method}",status="{cls}"}} {v}')
    lines += ["# HELP aiact_evidence_items_total 증적 건수", "# TYPE aiact_evidence_items_total gauge",
              f"aiact_evidence_items_total {evidence_count(db)}"]
    lines += ["# HELP aiact_llm_tokens_total LLM 토큰 사용량", "# TYPE aiact_llm_tokens_total counter"]
    for prov, i, o, cost in db.execute(select(LLMUsage.provider, func.sum(LLMUsage.input_tokens),
                                              func.sum(LLMUsage.output_tokens), func.sum(LLMUsage.cost_usd))
                                       .group_by(LLMUsage.provider)).all():
        lines.append(f'aiact_llm_tokens_total{{provider="{prov}",direction="input"}} {int(i or 0)}')
        lines.append(f'aiact_llm_tokens_total{{provider="{prov}",direction="output"}} {int(o or 0)}')
        lines.append(f'aiact_llm_cost_usd_total{{provider="{prov}"}} {float(cost or 0):.6f}')
    lines += ["# HELP aiact_job_runs_total 작업 실행 수", "# TYPE aiact_job_runs_total counter"]
    for job, status, n in db.execute(select(JobRun.job, JobRun.status, func.count(JobRun.id))
                                     .group_by(JobRun.job, JobRun.status)).all():
        lines.append(f'aiact_job_runs_total{{job="{job}",status="{status}"}} {n}')
    g = db.scalars(select(GoldenRun).order_by(GoldenRun.id.desc())).first()
    lines += ["# HELP aiact_golden_match_rate 최근 골든셋 일치율", "# TYPE aiact_golden_match_rate gauge",
              f"aiact_golden_match_rate {g.rate if g else 'NaN'}"]
    lines += ["# HELP aiact_open_reassessment_tasks 미해결 재평가 작업", "# TYPE aiact_open_reassessment_tasks gauge",
              f"aiact_open_reassessment_tasks {services.open_task_count(db)}"]
    return "\n".join(lines) + "\n"


@app.get("/meta")
def meta(db: Session = Depends(get_db)):
    v = db.scalars(select(KBVersion).where(KBVersion.is_active.is_(True))).first()
    return {"banner": BANNER, "llm": llm_status(db), "kb_version": v.version if v else None,
            "kb_label": v.label if v else None, "workflow_states": workflow.STATES,
            "workflow_labels": workflow.STATE_LABELS, "domain_labels": DOMAIN_LABELS,
            "doc_kind_labels": DOC_KIND_LABELS, "state_labels": GAP_STATE_LABELS, "role_labels": ROLE_LABELS}


# ---------------- 인증 ----------------

class LoginIn(BaseModel):
    email: str
    password: str


def user_out(u: User) -> dict[str, Any]:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "role_label": ROLE_LABELS.get(u.role, u.role),
            "customer_id": u.customer_id}


@app.post("/auth/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(User.email == body.email.strip().lower())).first()
    if not user or not verify_password(body.password, user.password_hash):
        audit(db, body.email[:100], "auth.login_failed")
        db.commit()
        raise HTTPException(401, "이메일 또는 비밀번호가 올바르지 않습니다")
    s = get_settings()
    token = create_token(user.id, user.role)
    response.set_cookie(s.cookie_name, token, httponly=True, samesite="lax", secure=s.cookie_secure,
                        max_age=s.session_hours * 3600, path="/")
    audit(db, user, "auth.login")
    db.commit()
    return {"user": user_out(user), "token": token}


@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(get_settings().cookie_name, path="/")
    return {"ok": True}


@app.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


# ---------------- M1 KB ----------------

@app.get("/kb")
def kb_view(db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = kb.active_version(db)
    versions = db.scalars(select(KBVersion).order_by(KBVersion.id)).all()
    mappings = db.scalars(select(ControlMapping).where(ControlMapping.kb_version == v.version)).all()
    return {
        "version": v.version, "label": v.label, "effective_date": v.effective_date, "notice": v.notice,
        "summary_label": kb.SUMMARY_LABEL, "mapping_label": kb.MAPPING_LABEL,
        "clauses": kb.get_clauses(db, v.version),
        "mappings": [{"clause_id": m.clause_id, "isms_p": m.isms_p, "iso42001": m.iso42001, "note": m.note} for m in mappings],
        "versions": [{"version": x.version, "label": x.label, "is_active": x.is_active, "applied_at": iso(x.applied_at)}
                     for x in versions],
    }


# ---------------- 고객사 ----------------

def customer_out(db: Session, c: Customer) -> dict[str, Any]:
    eng = services.engagement_of(db, c)
    r = get_router()
    return {
        "id": c.id, "name": c.name, "description": c.description, "employees": c.employees,
        "is_synthetic": c.is_synthetic, "allow_external": c.allow_external,
        "monthly_budget_usd": c.monthly_budget_usd, "month_cost_usd": round(r.month_cost(db, c.id), 6),
        "subscribed": c.subscribed, "current_state": c.current_state or {}, "tech_targets": c.tech_targets or {},
        "state": eng.state, "state_label": workflow.STATE_LABELS[eng.state], "state_index": workflow.idx(eng.state),
        "updated_at": iso(eng.updated_at), "open_tasks": services.open_task_count(db, c.id),
        "evidence_count": evidence_count(db, c.id), "llm": llm_status(db, c),
    }


@app.get("/customers")
def customers(db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(Customer).order_by(Customer.id)
    if user.role == "customer":
        q = q.where(Customer.id == user.customer_id)
    out = [customer_out(db, c) for c in db.scalars(q).all()]
    db.commit()
    return out


@app.get("/customers/{cid}")
def customer_detail(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = customer_for(db, user, cid)
    out = customer_out(db, c)
    db.commit()
    return out


class PolicyIn(BaseModel):
    allow_external: bool | None = None
    monthly_budget_usd: float | None = Field(default=None, ge=0, le=100000)


@app.patch("/customers/{cid}/policy")
def set_policy(cid: int, body: PolicyIn, db: Session = Depends(get_db),
               user: User = Depends(require_roles("consultant", "ops"))):
    c = customer_for(db, user, cid)
    before = {"allow_external": c.allow_external, "monthly_budget_usd": c.monthly_budget_usd}
    if body.allow_external is not None:
        c.allow_external = body.allow_external
    if body.monthly_budget_usd is not None:
        c.monthly_budget_usd = body.monthly_budget_usd
    audit(db, user, "customer.policy", entity="customer", entity_id=c.id, customer_id=c.id,
          detail={"before": before, "after": {"allow_external": c.allow_external, "monthly_budget_usd": c.monthly_budget_usd}})
    out = customer_out(db, c)
    db.commit()
    return out


# ---------------- 자료 ----------------

class DocumentIn(BaseModel):
    kind: str = Field(pattern="^(questionnaire|service_intro|tos|dev_doc|other)$")
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=200_000)
    data: dict[str, Any] | None = None


def doc_out(d: Document, full: bool = False) -> dict[str, Any]:
    o = {"id": d.id, "kind": d.kind, "title": d.title, "chars": len(d.content), "uploaded_by": d.uploaded_by,
         "created_at": iso(d.created_at), "has_structured_data": bool(d.data)}
    if full:
        o["content"] = d.content
        o["data"] = d.data
    return o


@app.get("/customers/{cid}/documents")
def list_documents(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    customer_for(db, user, cid)
    return [doc_out(d, True) for d in db.scalars(select(Document).where(Document.customer_id == cid).order_by(Document.id))]


@app.post("/customers/{cid}/documents", status_code=201)
def upload_document(cid: int, body: DocumentIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("customer", "consultant"))):
    c = customer_for(db, user, cid)
    d = services.ingest_document(db, c, user, kind=body.kind, title=body.title, content=body.content, data=body.data)
    db.commit()
    return doc_out(d)


@app.post("/customers/{cid}/documents/load-samples", status_code=201)
def load_samples(cid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("customer", "consultant"))):
    c = customer_for(db, user, cid)
    have = {d.title for d in db.scalars(select(Document).where(Document.customer_id == cid))}
    out = [services.ingest_document(db, c, user, **d) for d in sample_docs() if d["title"] not in have]
    db.commit()
    return [doc_out(d) for d in out]


# ---------------- M2 인벤토리 ----------------

def system_out(db: Session, s: AISystem) -> dict[str, Any]:
    facts = db.scalars(select(Fact).where(Fact.system_id == s.id).order_by(Fact.id)).all()
    titles = {d.id: d.title for d in db.scalars(select(Document).where(Document.customer_id == s.customer_id))}
    return {"id": s.id, "name": s.name, "attributes": s.attributes or {}, "extracted_by": s.extracted_by,
            "facts": [{"id": f.id, "field": f.field, "value": f.value, "doc_id": f.doc_id,
                       "doc_title": titles.get(f.doc_id), "quote": f.quote, "span_start": f.span_start,
                       "span_end": f.span_end, "source": f.source, "supported": f.supported} for f in facts]}


@app.post("/customers/{cid}/inventory/extract")
def extract_inventory(cid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("consultant"))):
    c = customer_for(db, user, cid)
    r = services.run_inventory(db, c, user)
    out = {"provider": r["provider"], "route_reason": r["route_reason"], "note": r["note"],
           "systems": [system_out(db, s) for s in r["systems"]]}
    db.commit()
    return out


@app.get("/customers/{cid}/systems")
def list_systems(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    customer_for(db, user, cid)
    return [system_out(db, s) for s in services.active_systems(db, cid)]


class SystemPatch(BaseModel):
    attributes: dict[str, Any]


@app.patch("/systems/{sid}")
def patch_system(sid: int, body: SystemPatch, db: Session = Depends(get_db),
                 user: User = Depends(require_roles("consultant"))):
    s = db.get(AISystem, sid)
    if not s:
        raise HTTPException(404, "시스템을 찾을 수 없습니다")
    services.update_system_attributes(db, s, user, body.attributes)
    out = system_out(db, s)
    db.commit()
    return out


# ---------------- M3 판정 ----------------

def cls_out(c: Classification, system_name: str = "") -> dict[str, Any]:
    return {"id": c.id, "system_id": c.system_id, "system_name": system_name, "version": c.version,
            "status": c.status, "kb_version": c.kb_version, "result": c.result, "confirmed_by": c.confirmed_by,
            "confirmed_at": iso(c.confirmed_at), "created_at": iso(c.created_at)}


@app.post("/customers/{cid}/classify")
def classify_customer(cid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("consultant"))):
    c = customer_for(db, user, cid)
    rows = services.run_classify(db, c, user)
    names = {s.id: s.name for s in services.active_systems(db, cid)}
    out = [cls_out(r, names.get(r.system_id, "")) for r in rows]
    db.commit()
    return out


@app.get("/customers/{cid}/classifications")
def list_classifications(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    customer_for(db, user, cid)
    systems = services.active_systems(db, cid)
    latest = services.latest_classifications(db, cid)
    _, clauses = kb.active_clauses(db)
    history = db.scalars(select(Classification).where(Classification.customer_id == cid)
                         .order_by(Classification.system_id, Classification.version)).all()
    items = []
    for s in systems:
        c = latest.get(s.id)
        if c:
            o = cls_out(c, s.name)
            o["system"] = system_out(db, s)
            o["history"] = [{"id": h.id, "version": h.version, "status": h.status, "kb_version": h.kb_version,
                             "confirmed_by": h.confirmed_by, "created_at": iso(h.created_at)}
                            for h in history if h.system_id == s.id]
            items.append(o)
    return {"items": items, "clauses": clauses}


@app.post("/classifications/{clid}/confirm")
def confirm(clid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("consultant"))):
    c = db.get(Classification, clid)
    if not c:
        raise HTTPException(404, "판정을 찾을 수 없습니다")
    services.confirm_classification(db, c, user)
    db.commit()
    return cls_out(c)


# ---------------- 갭 리포트 ----------------

def gap_out(r: Any) -> dict[str, Any]:
    return {"id": r.id, "version": r.version, "kb_version": r.kb_version, "findings": r.findings, "html": r.html,
            "created_by": r.created_by, "created_at": iso(r.created_at)}


@app.post("/customers/{cid}/gap-report")
def create_gap(cid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("consultant"))):
    c = customer_for(db, user, cid)
    r = services.build_gap_report(db, c, user)
    db.commit()
    return gap_out(r)


@app.get("/customers/{cid}/gap-report")
def get_gap(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    customer_for(db, user, cid)
    r = services.latest_gap_report(db, cid)
    _, clauses = kb.active_clauses(db)
    return {"report": gap_out(r) if r else None, "clauses": clauses}


# ---------------- M4 문서 ----------------

def gdoc_out(d: GeneratedDocument, full: bool = True) -> dict[str, Any]:
    o = {"id": d.id, "kind": d.kind, "kind_label": DOC_KIND_LABELS.get(d.kind, d.kind), "title": d.title,
         "version": d.version, "status": d.status, "provider": d.provider, "system_id": d.system_id,
         "approved_by": d.approved_by, "approved_at": iso(d.approved_at), "created_at": iso(d.created_at),
         "unsupported": sum(1 for p in d.paragraphs if not p.get("supported", True))}
    if full:
        o["paragraphs"] = d.paragraphs
        o["html"] = d.html
    return o


@app.post("/customers/{cid}/generated-documents/generate")
def gen_docs(cid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("consultant"))):
    c = customer_for(db, user, cid)
    docs = services.generate_documents(db, c, user)
    out = [gdoc_out(d, False) for d in docs]
    db.commit()
    return out


@app.get("/customers/{cid}/generated-documents")
def list_gdocs(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    customer_for(db, user, cid)
    _, clauses = kb.active_clauses(db)
    return {"items": [gdoc_out(d) for d in services.current_documents(db, cid)], "clauses": clauses}


@app.post("/customers/{cid}/approve")
def approve(cid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("consultant"))):
    c = customer_for(db, user, cid)
    docs = services.approve_documents(db, c, user)
    out = [gdoc_out(d, False) for d in docs]
    db.commit()
    return out


# ---------------- M6 증적 ----------------

def ev_out(e: EvidenceItem) -> dict[str, Any]:
    return {"id": e.id, "seq": e.seq, "kind": e.kind, "title": e.title, "content_type": e.content_type, "size": e.size,
            "sha256": e.sha256, "prev_hash": e.prev_hash, "chain_hash": e.chain_hash,
            "retention_until": iso(e.retention_until), "created_by": e.created_by, "created_at": iso(e.created_at),
            "meta": e.meta}


@app.post("/customers/{cid}/evidence/store-package")
def store_package(cid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("consultant"))):
    c = customer_for(db, user, cid)
    items = services.store_evidence_package(db, c, user)
    out = [ev_out(i) for i in items]
    db.commit()
    return out


@app.get("/customers/{cid}/evidence")
def list_evidence(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    customer_for(db, user, cid)
    rows = db.scalars(select(EvidenceItem).where(EvidenceItem.customer_id == cid).order_by(EvidenceItem.seq)).all()
    return [ev_out(e) for e in rows]


@app.post("/customers/{cid}/evidence/verify")
def verify_evidence(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = customer_for(db, user, cid)
    r = EvidenceStore().verify(db, c.id)
    audit(db, user, "evidence.verify", entity="customer", entity_id=c.id, customer_id=c.id,
          detail={"ok": r["ok"], "count": r["count"], "problems": len(r["problems"])})
    db.commit()
    return r


@app.get("/evidence/{eid}/content")
def evidence_content(eid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = db.get(EvidenceItem, eid)
    if not e:
        raise HTTPException(404, "증적을 찾을 수 없습니다")
    customer_for(db, user, e.customer_id)
    try:
        data = EvidenceStore().read(e.customer_id, e.sha256)
    except FileNotFoundError:
        raise HTTPException(410, "증적 원본 파일이 없습니다(체인 검증을 실행하세요)")
    # 저장된 HTML 이 포털 출처에서 실행되지 않도록 항상 첨부·텍스트로만 내려준다
    return Response(content=data, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="evidence-{e.seq}.txt"',
                             "X-Content-Type-Options": "nosniff"})


# ---------------- M5 기술 점검 ----------------

def tc_out(t: TechCheck) -> dict[str, Any]:
    return {"id": t.id, "target": t.target, "results": t.results, "passed": t.passed, "failed": t.failed,
            "evidence_id": t.evidence_id, "triggered_by": t.triggered_by, "created_at": iso(t.created_at)}


@app.post("/customers/{cid}/tech-check")
def tech_check(cid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("consultant", "ops"))):
    c = customer_for(db, user, cid)
    t = services.run_tech_check(db, c, user)
    db.commit()
    return tc_out(t)


@app.get("/customers/{cid}/tech-checks")
def tech_checks(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    customer_for(db, user, cid)
    rows = db.scalars(select(TechCheck).where(TechCheck.customer_id == cid).order_by(TechCheck.id.desc()).limit(20)).all()
    return {"items": [tc_out(t) for t in rows], "allowlist": list(get_settings().tech_check_allowlist)}


# ---------------- M7 변경 감지 ----------------

def task_out(t: ReassessmentTask, names: dict[int, str]) -> dict[str, Any]:
    return {"id": t.id, "customer_id": t.customer_id, "system_id": t.system_id,
            "system_name": names.get(t.system_id or -1, "(전체)"), "classification_id": t.classification_id,
            "change_event_id": t.change_event_id, "reason": t.reason, "clause_ids": t.clause_ids, "status": t.status,
            "resolved_by": t.resolved_by, "created_at": iso(t.created_at)}


def event_out(e: ChangeEvent) -> dict[str, Any]:
    return {"id": e.id, "type": e.type, "customer_id": e.customer_id, "title": e.title, "payload": e.payload,
            "created_by": e.created_by, "created_at": iso(e.created_at)}


@app.post("/changes/law/simulate")
def simulate_law_change(db: Session = Depends(get_db), user: User = Depends(require_roles("consultant", "ops"))):
    data = kb.load_file(kb.KB_V2_SIM_PATH)
    try:
        r = changes.apply_law_change(db, data, user.email)
    except ValueError as e:
        raise HTTPException(409, str(e))
    audit(db, user, "law_change.apply", entity="change_event", entity_id=r["event"].id,
          detail={"to": data["version"], "tasks": len(r["tasks"])})
    names = {s.id: s.name for s in db.scalars(select(AISystem))}
    out = {"event": event_out(r["event"]), "tasks": [task_out(t, names) for t in r["tasks"]]}
    db.commit()
    return out


@app.get("/changes")
def list_changes(customer_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role == "customer":
        customer_id = user.customer_id
    q = select(ChangeEvent).order_by(ChangeEvent.id.desc())
    events = [e for e in db.scalars(q).all()
              if e.type == "law_change" or customer_id is None or e.customer_id == customer_id]
    tq = select(ReassessmentTask).order_by(ReassessmentTask.id.desc())
    if customer_id is not None:
        tq = tq.where(ReassessmentTask.customer_id == customer_id)
    names = {s.id: s.name for s in db.scalars(select(AISystem))}
    v2 = kb.load_file(kb.KB_V2_SIM_PATH)["version"]
    applied = db.scalars(select(KBVersion).where(KBVersion.version == v2)).first() is not None
    return {"events": [event_out(e) for e in events], "tasks": [task_out(t, names) for t in db.scalars(tq).all()],
            "simulation_available": not applied, "simulation_version": v2}


@app.post("/tasks/{tid}/resolve")
def resolve_task(tid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("consultant"))):
    t = db.get(ReassessmentTask, tid)
    if not t:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    t.status = "done"
    t.resolved_by = user.email
    audit(db, user, "reassessment.resolve", entity="reassessment_task", entity_id=t.id, customer_id=t.customer_id)
    db.commit()
    return {"id": t.id, "status": t.status}


class ReleaseIn(BaseModel):
    customer_id: int
    version: str = Field(default="", max_length=100)
    system_name: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)


@app.post("/webhooks/release", status_code=201)
def release_webhook(body: ReleaseIn, request: Request, db: Session = Depends(get_db)):
    expected = os.environ.get("RELEASE_WEBHOOK_TOKEN", "demo-webhook-token")
    if not hmac.compare_digest(request.headers.get("x-webhook-token", ""), expected):
        raise HTTPException(401, "웹훅 토큰이 올바르지 않습니다")
    c = db.get(Customer, body.customer_id)
    if not c:
        raise HTTPException(404, "고객사를 찾을 수 없습니다")
    r = changes.record_release(db, c.id, body.model_dump(), "webhook")
    audit(db, "webhook", "release.webhook", entity="change_event", entity_id=r["event"].id, customer_id=c.id,
          detail={"version": body.version, "tasks": len(r["tasks"])})
    names = {s.id: s.name for s in db.scalars(select(AISystem))}
    out = {"event": event_out(r["event"]), "tasks": [task_out(t, names) for t in r["tasks"]]}
    db.commit()
    return out


# ---------------- M9 연동 ----------------

@app.post("/customers/{cid}/gateway-logs", status_code=201)
async def gateway_logs(cid: int, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(require_roles("consultant", "ops"))):
    c = customer_for(db, user, cid)
    raw = await request.body()
    if len(raw) > 5_000_000:
        raise HTTPException(413, "로그가 너무 큽니다(최대 5MB)")
    try:
        out = services.ingest_gateway_logs(db, c, user, raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise HTTPException(400, str(e) or "잘못된 로그 형식")
    db.commit()
    return out


# ---------------- 감사 로그 ----------------

@app.get("/audit")
def audit_logs(customer_id: int | None = None, limit: int = 200, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    if user.role == "customer":
        customer_id = user.customer_id
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(max(1, min(limit, 500)))
    if customer_id is not None:
        q = q.where(AuditLog.customer_id == customer_id)
    return [{"id": a.id, "at": iso(a.at), "actor": a.actor, "role": a.role, "action": a.action, "entity": a.entity,
             "entity_id": a.entity_id, "customer_id": a.customer_id, "detail": a.detail} for a in db.scalars(q).all()]


# ---------------- 운영 콘솔 ----------------

@app.get("/ops/summary")
def ops_summary(db: Session = Depends(get_db), user: User = Depends(require_roles("ops", "consultant"))):
    r = get_router()
    nxt = jobs.next_runs()
    runs = db.scalars(select(JobRun).order_by(JobRun.id.desc()).limit(30)).all()
    golden = db.scalars(select(GoldenRun).order_by(GoldenRun.id.desc()).limit(10)).all()
    usage = db.execute(select(LLMUsage.customer_id, LLMUsage.task, LLMUsage.provider, func.count(LLMUsage.id),
                              func.sum(LLMUsage.input_tokens), func.sum(LLMUsage.output_tokens),
                              func.sum(LLMUsage.cost_usd))
                       .group_by(LLMUsage.customer_id, LLMUsage.task, LLMUsage.provider)).all()
    names = {c.id: c.name for c in db.scalars(select(Customer))}
    budgets = []
    for c in db.scalars(select(Customer).order_by(Customer.id)):
        spent = r.month_cost(db, c.id)
        budgets.append({"customer_id": c.id, "customer": c.name, "allow_external": c.allow_external,
                        "budget_usd": c.monthly_budget_usd, "spent_usd": round(spent, 6),
                        "status": "초과" if spent >= (c.monthly_budget_usd or 0) else "정상"})
    s = get_settings()
    return {
        "llm": llm_status(db),
        "pricing": {"input_per_mtok_usd": s.price_in_per_mtok, "output_per_mtok_usd": s.price_out_per_mtok},
        "scheduler_enabled": s.scheduler_enabled,
        "jobs": [{"name": n, "label": j["label"], "schedule": j["schedule"], "next_run": nxt.get(n)} for n, j in jobs.JOBS.items()],
        "job_runs": [{"id": x.id, "job": x.job, "label": jobs.JOBS.get(x.job, {}).get("label", x.job), "trigger": x.trigger,
                      "status": x.status, "detail": x.detail, "started_at": iso(x.started_at),
                      "finished_at": iso(x.finished_at)} for x in runs],
        "golden_runs": [{"id": g.id, "at": iso(g.at), "config": g.config_name, "total": g.total, "matched": g.matched,
                         "rate": g.rate, "engine_rate": g.engine_rate, "threshold": g.threshold, "passed": g.passed,
                         "mismatches": g.mismatches} for g in golden],
        "model_configs": [{"name": m.name, "provider": m.provider, "model": m.model, "status": m.status,
                           "last_rate": m.last_rate, "updated_at": iso(m.updated_at)}
                          for m in db.scalars(select(ModelConfig).order_by(ModelConfig.id))],
        "usage": [{"customer": names.get(cid, "(공통)"), "task": task, "provider": prov, "calls": n,
                   "input_tokens": int(i or 0), "output_tokens": int(o or 0), "cost_usd": round(float(cost or 0), 6)}
                  for cid, task, prov, n, i, o, cost in usage],
        "budgets": budgets,
        "evidence_backend": s.evidence_backend,
    }


@app.post("/ops/jobs/{name}/run")
def run_job_now(name: str, db: Session = Depends(get_db), user: User = Depends(require_roles("ops"))):
    if name not in jobs.JOBS:
        raise HTTPException(404, "알 수 없는 작업")
    audit(db, user, "ops.job_run", entity="job", entity_id=name)
    db.commit()
    return jobs.run_job(name, trigger="manual")
