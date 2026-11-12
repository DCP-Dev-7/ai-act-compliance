"""운영 자동화(APScheduler). 모든 실행은 job_runs 에 기록된다."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import docgen, kb, services
from .db import session_factory
from .evidence import EvidenceStore, evidence_count
from .models import Customer, GeneratedDocument, JobRun, TechCheck

log = logging.getLogger("aiact.jobs")


def job_evidence_verify(db: Session) -> dict[str, Any]:
    store = EvidenceStore()
    results = []
    for c in db.scalars(select(Customer)).all():
        r = store.verify(db, c.id)
        results.append({"customer": c.name, "ok": r["ok"], "count": r["count"], "problems": r["problems"][:5]})
    return {"ok": all(r["ok"] for r in results), "results": results}


def job_tech_check(db: Session) -> dict[str, Any]:
    results = []
    for c in db.scalars(select(Customer).where(Customer.subscribed.is_(True))).all():
        if not (c.tech_targets or {}).get("base_url"):
            continue
        try:
            tc = services.run_tech_check(db, c, "scheduler")
            results.append({"customer": c.name, "passed": tc.passed, "failed": tc.failed, "tech_check_id": tc.id})
        except Exception as e:
            results.append({"customer": c.name, "error": f"{type(e).__name__}: {e}"})
    return {"ok": not any("error" in r for r in results), "results": results}


def job_monthly_report(db: Session) -> dict[str, Any]:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    version, clauses = kb.active_clauses(db)
    store = EvidenceStore()
    out = []
    for c in db.scalars(select(Customer).where(Customer.subscribed.is_(True))).all():
        last_tc = db.scalars(select(TechCheck).where(TechCheck.customer_id == c.id).order_by(TechCheck.id.desc())).first()
        report = services.latest_gap_report(db, c.id)
        stats = {"evidence_count": evidence_count(db, c.id),
                 "chain_ok": "정상" if store.verify(db, c.id)["ok"] else "이상 발견",
                 "tech_passed": last_tc.passed if last_tc else 0, "tech_failed": last_tc.failed if last_tc else 0,
                 "open_tasks": services.open_task_count(db, c.id),
                 "open_gaps": len(report.findings) if report else 0}
        paragraphs = docgen.validate_paragraphs(docgen.monthly_report(c.name, month, stats), clauses)
        title = f"월간 준수 현황 보고 초안 {month}"
        n = db.scalar(select(func.count(GeneratedDocument.id)).where(GeneratedDocument.customer_id == c.id,
                                                                    GeneratedDocument.kind == "monthly_report")) or 0
        doc = GeneratedDocument(customer_id=c.id, kind="monthly_report", title=title, version=n + 1,
                                paragraphs=paragraphs, provider="mock(템플릿)",
                                html=docgen.render_html(title, c.name, version, paragraphs, clauses, "mock(템플릿)"))
        db.add(doc)
        db.flush()
        out.append({"customer": c.name, "document_id": doc.id, "stats": stats})
    return {"ok": True, "results": out}


def job_golden_regression(db: Session) -> dict[str, Any]:
    run = services.golden_regression(db)
    return {"ok": run.passed, "config": run.config_name, "total": run.total, "matched": run.matched, "rate": run.rate,
            "engine_rate": run.engine_rate, "threshold": run.threshold,
            "promotion": "승격 가능" if run.passed else "승격 차단"}


JOBS: dict[str, dict[str, Any]] = {
    "evidence_verify": {"label": "증적 체인 검증", "schedule": "매일 02:00", "cron": {"hour": 2, "minute": 0},
                        "fn": job_evidence_verify},
    "tech_check": {"label": "구독 고객 기술 점검", "schedule": "매주 월 03:00",
                   "cron": {"day_of_week": "mon", "hour": 3, "minute": 0}, "fn": job_tech_check},
    "monthly_report": {"label": "월간 보고서 초안 생성", "schedule": "매월 1일 04:00",
                       "cron": {"day": 1, "hour": 4, "minute": 0}, "fn": job_monthly_report},
    "golden_regression": {"label": "골든셋 회귀(야간)", "schedule": "매일 01:00", "cron": {"hour": 1, "minute": 0},
                          "fn": job_golden_regression},
}


def run_job(name: str, trigger: str = "schedule") -> dict[str, Any]:
    if name not in JOBS:
        raise KeyError(name)
    fn: Callable[[Session], dict[str, Any]] = JOBS[name]["fn"]
    with session_factory()() as db:
        run = JobRun(job=name, trigger=trigger, status="running")
        db.add(run)
        db.commit()
        try:
            detail = fn(db)
            run.status = "ok" if detail.get("ok", True) else "failed"
            run.detail = detail
        except Exception as e:  # 작업 실패도 기록한다
            db.rollback()
            log.exception("job %s failed", name)
            run = db.get(JobRun, run.id)
            run.status = "failed"
            run.detail = {"error": f"{type(e).__name__}: {e}"}
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return {"id": run.id, "job": name, "status": run.status, "detail": run.detail}


_scheduler = None


def start_scheduler():
    global _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    if _scheduler is not None:
        return _scheduler
    sched = BackgroundScheduler(timezone="Asia/Seoul")
    for name, j in JOBS.items():
        sched.add_job(run_job, CronTrigger(timezone="Asia/Seoul", **j["cron"]), args=[name], id=name,
                      max_instances=1, coalesce=True, misfire_grace_time=3600)
    sched.start()
    _scheduler = sched
    return sched


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def next_runs() -> dict[str, str | None]:
    if _scheduler is None:
        return {name: None for name in JOBS}
    out = {}
    for name in JOBS:
        job = _scheduler.get_job(name)
        out[name] = job.next_run_time.isoformat() if job and job.next_run_time else None
    return out
