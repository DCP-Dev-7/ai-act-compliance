from pathlib import Path

from app import kb
from app.changes import affected_by_diff, matches

from .test_workflow_api import cid, to_confirmed


def test_kb_seeded_with_sources_and_labels(client, auth):
    k = client.get("/kb", headers=auth["customer"]).json()
    ids = {c["clause_id"] for c in k["clauses"]}
    assert {"art2-operator", "art2-highimpact", "art31-1", "art31-2", "art31-3", "art32", "art33", "art34",
            "art35", "art36", "art43"} <= ids
    assert all(c["sources"] and all(s.startswith("https://") for s in c["sources"]) for c in k["clauses"])
    assert all(c["label"] == "요약 — 원문 확인 필요" for c in k["clauses"])
    assert k["mapping_label"] == "초안 매핑 — 전문가 검증 필요" and len(k["mappings"]) >= 5
    assert all("(범주)" in m["isms_p"] and "(범주)" in m["iso42001"] for m in k["mappings"])


def test_diff_between_versions():
    v1 = kb.load_file(kb.KB_V1_PATH)
    v2 = kb.load_file(kb.KB_V2_SIM_PATH)
    new = kb.materialize(v2, v1["clauses"])
    d = kb.diff_clauses(v1["clauses"], new)
    assert [c["clause_id"] for c in d["added"]] == ["guide-img-edit"]
    assert [c["clause_id"] for c in d["changed"]] == ["art31-2"] and d["removed"] == []
    assert kb.diff_clauses(v1["clauses"], v1["clauses"]) == {"added": [], "changed": [], "removed": []}
    assert "시뮬레이션" in v2["label"]


def test_applies_when_matching():
    aw = {"is_generative": True, "output_types": ["image"]}
    assert matches(aw, {"is_generative": True, "output_types": ["image", "text"]})
    assert not matches(aw, {"is_generative": True, "output_types": ["text"]})
    assert not matches(aw, {"is_generative": False, "output_types": ["image"]})
    assert matches(None, {})


def test_law_change_creates_reassessment_tasks_only_for_affected_confirmed(client, auth):
    c = cid(client, auth)
    to_confirmed(client, auth, c)
    assert client.post("/changes/law/simulate", headers=auth["customer"]).status_code == 403
    r = client.post("/changes/law/simulate", headers=auth["consultant"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["event"]["payload"]["added"] == ["guide-img-edit"] and body["event"]["payload"]["changed"] == ["art31-2"]
    tasks = {t["system_name"]: t for t in body["tasks"]}
    # 이미지·문구 생성은 영향(표시 조문 변경), 내부용 요약은 표시 의무 예외라 영향 없음
    assert set(tasks) == {"상품 이미지 생성", "상품 설명 문구 생성"}
    assert "guide-img-edit" in tasks["상품 이미지 생성"]["clause_ids"]
    assert tasks["상품 설명 문구 생성"]["clause_ids"] == ["art31-2"]
    assert all(t["status"] == "open" for t in tasks.values())
    k = client.get("/kb", headers=auth["consultant"]).json()
    assert k["version"] == "2026.11-v2-sim" and len(k["versions"]) == 2
    assert client.post("/changes/law/simulate", headers=auth["consultant"]).status_code == 409  # 중복 적용 방지
    ch = client.get(f"/changes?customer_id={c}", headers=auth["customer"]).json()
    assert len(ch["tasks"]) == 2 and ch["events"][0]["type"] == "law_change" and not ch["simulation_available"]
    # 재판정은 새 KB 버전으로 기록된다
    drafts = client.post(f"/customers/{c}/classify", headers=auth["consultant"]).json()
    assert all(d["kb_version"] == "2026.11-v2-sim" and d["version"] == 2 for d in drafts)
    t = body["tasks"][0]
    assert client.post(f"/tasks/{t['id']}/resolve", headers=auth["customer"]).status_code == 403
    assert client.post(f"/tasks/{t['id']}/resolve", headers=auth["consultant"]).json()["status"] == "done"


def test_draft_classifications_do_not_get_tasks(client, auth):
    from app.seed import sample_docs

    c = cid(client, auth)
    for d in sample_docs():
        client.post(f"/customers/{c}/documents", json=d, headers=auth["customer"])
    client.post(f"/customers/{c}/inventory/extract", headers=auth["consultant"])
    client.post(f"/customers/{c}/classify", headers=auth["consultant"])
    assert client.post("/changes/law/simulate", headers=auth["ops"]).json()["tasks"] == []


def test_affected_by_diff_removed_clause():
    class C:  # 최소 대역
        result = {"applicable_articles": ["art31-1"]}

    class S:
        attributes = {}

    d = {"added": [], "changed": [], "removed": [{"clause_id": "art31-1", "article": "제31조", "title": "사전 고지"}]}
    out = affected_by_diff(d, [(C(), S())])
    assert len(out) == 1 and "삭제" in out[0]["reasons"][0]


def test_release_webhook(client, auth):
    c = cid(client, auth)
    to_confirmed(client, auth, c)
    body = {"customer_id": c, "version": "v2.3.0", "system_name": "상품 이미지 생성", "notes": "이미지 모델 교체"}
    assert client.post("/webhooks/release", json=body).status_code == 401
    assert client.post("/webhooks/release", json=body, headers={"X-Webhook-Token": "wrong"}).status_code == 401
    r = client.post("/webhooks/release", json=body, headers={"X-Webhook-Token": "demo-webhook-token"})
    assert r.status_code == 201
    assert [t["system_name"] for t in r.json()["tasks"]] == ["상품 이미지 생성"]
    assert "모델 교체" in r.json()["tasks"][0]["reason"] and r.json()["event"]["type"] == "customer_release"


def test_jobs_record_runs_and_golden_blocks_promotion(client, auth, monkeypatch):
    c = cid(client, auth)
    to_confirmed(client, auth, c)
    h = auth["ops"]
    r = client.post("/ops/jobs/golden_regression/run", headers=h).json()
    assert r["status"] == "ok" and r["detail"]["rate"] >= 0.9 and r["detail"]["promotion"] == "승격 가능"
    assert client.post("/ops/jobs/evidence_verify/run", headers=h).json()["status"] == "ok"
    m = client.post("/ops/jobs/monthly_report/run", headers=h).json()
    assert m["status"] == "ok" and m["detail"]["results"][0]["document_id"]
    assert client.post("/ops/jobs/nope/run", headers=h).status_code == 404
    monkeypatch.setenv("GOLDEN_THRESHOLD", "1.0")  # 임계를 100%로 올리면(현재 32/33) 승격이 차단되어야 한다
    r2 = client.post("/ops/jobs/golden_regression/run", headers=h).json()
    assert r2["status"] == "failed" and r2["detail"]["promotion"] == "승격 차단"
    s = client.get("/ops/summary", headers=h).json()
    assert s["model_configs"][0]["status"] == "승격 차단"
    assert [g["passed"] for g in s["golden_runs"]][:2] == [False, True]
    assert {j["name"] for j in s["jobs"]} == {"evidence_verify", "tech_check", "monthly_report", "golden_regression"}
    assert len(s["job_runs"]) == 4 and s["llm"]["configured"] == "mock"
    assert any(u["task"] == "inventory_extract" and u["input_tokens"] > 0 for u in s["usage"])
    assert s["budgets"][0]["status"] == "정상" and s["pricing"] == {"input_per_mtok_usd": 8.0, "output_per_mtok_usd": 40.0}
    text = client.get("/metrics").text
    assert 'aiact_job_runs_total{job="golden_regression",status="ok"} 1' in text and "aiact_golden_match_rate" in text


def test_scheduler_registers_all_jobs():
    from app import jobs

    sched = jobs.start_scheduler()
    try:
        assert {j.id for j in sched.get_jobs()} == set(jobs.JOBS)
        assert all(v for v in jobs.next_runs().values())
    finally:
        jobs.stop_scheduler()


def test_sql_migration_matches_models():
    """001 은 배포된 그대로여야 하고(이후 추가 컬럼 제외 시 모델과 동일), 추가 컬럼은 뒤 마이그레이션에 있어야 한다."""
    import re

    from app.db import Base
    from app.migrate import ADDED_COLUMNS, MIGRATIONS_DIR, schema_sql

    assert (Path(MIGRATIONS_DIR) / "001_init.sql").read_text(encoding="utf-8") == schema_sql()
    for fname, tables in ADDED_COLUMNS.items():
        sql = (Path(MIGRATIONS_DIR) / fname).read_text(encoding="utf-8")
        for table, cols in tables.items():
            for col in cols:
                assert col in Base.metadata.tables[table].columns, f"모델에 {table}.{col} 없음"
                assert re.search(rf"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} ", sql), f"{fname} 에 {col} 없음"
                # 이전 버전 코드가 넣는 행도 깨지지 않도록 DB 기본값이 있어야 한다
                assert re.search(rf"ADD COLUMN IF NOT EXISTS {col} [^;]*NOT NULL DEFAULT", sql)


def test_later_migrations_are_additive_only():
    """기존 DB(볼륨)를 보존해야 하므로 001 이후 마이그레이션은 DROP/RENAME/타입 변경을 쓰지 않는다."""
    import re

    from app.migrate import MIGRATIONS_DIR

    later = sorted(p for p in Path(MIGRATIONS_DIR).glob("*.sql") if p.name != "001_init.sql")
    assert later, "추가 마이그레이션이 있어야 한다"
    for p in later:
        body = re.sub(r"--[^\n]*", "", p.read_text(encoding="utf-8")).upper()
        for bad in ("DROP ", "RENAME ", "ALTER COLUMN", "TRUNCATE", "DELETE FROM"):
            assert bad not in body, f"{p.name}: {bad.strip()} 사용 금지"
