"""M8 워크플로·권한: HTTP API 로 A사 흐름을 따라가며 역할 게이트와 감사 로그를 확인한다."""
import httpx

from app.seed import sample_docs

from .conftest import demo_transport


def cid(client, auth):
    return client.get("/customers", headers=auth["consultant"]).json()[0]["id"]


def upload_all(client, auth, c):
    for d in sample_docs():
        r = client.post(f"/customers/{c}/documents", json=d, headers=auth["customer"])
        assert r.status_code == 201, r.text


def to_confirmed(client, auth, c):
    upload_all(client, auth, c)
    assert client.post(f"/customers/{c}/inventory/extract", headers=auth["consultant"]).status_code == 200
    drafts = client.post(f"/customers/{c}/classify", headers=auth["consultant"]).json()
    for d in drafts:
        assert client.post(f"/classifications/{d['id']}/confirm", headers=auth["consultant"]).status_code == 200
    return drafts


def test_auth_required_and_login(client):
    assert client.get("/customers").status_code == 401
    assert client.post("/auth/login", json={"email": "consultant@demo", "password": "wrong"}).status_code == 401
    r = client.post("/auth/login", json={"email": "consultant@demo", "password": "demo1234"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "consultant"
    cookie = r.headers["set-cookie"]
    assert "aiact_session=" in cookie and "HttpOnly" in cookie
    assert client.get("/auth/me").json()["email"] == "consultant@demo"  # 쿠키 세션
    client.post("/auth/logout")
    client.cookies.clear()
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_passwords_are_hashed(db):
    from app.models import User

    for u in db.query(User).all():
        assert u.password_hash.startswith("pbkdf2_sha256$") and "demo1234" not in u.password_hash
    assert {u.email for u in db.query(User).all()} == {"a-company@demo", "consultant@demo", "ops@demo"}


def test_public_endpoints(client):
    assert client.get("/health").json()["status"] == "ok"
    m = client.get("/meta").json()
    assert m["banner"] == "가상 데이터 · 법률 자문 아님" and m["llm"]["configured"] == "mock"
    assert "aiact_evidence_items_total 0" in client.get("/metrics").text


def test_steps_cannot_be_skipped(client, auth):
    c = cid(client, auth)
    h = auth["consultant"]
    assert client.post(f"/customers/{c}/inventory/extract", headers=h).status_code == 409  # 자료 없음
    assert client.post(f"/customers/{c}/classify", headers=h).status_code == 409
    assert client.post(f"/customers/{c}/gap-report", headers=h).status_code == 409
    assert client.post(f"/customers/{c}/generated-documents/generate", headers=h).status_code == 409
    assert client.post(f"/customers/{c}/approve", headers=h).status_code == 409
    assert client.post(f"/customers/{c}/evidence/store-package", headers=h).status_code == 409
    upload_all(client, auth, c)
    client.post(f"/customers/{c}/inventory/extract", headers=h)
    client.post(f"/customers/{c}/classify", headers=h)
    # 판정 미확정 상태에서는 갭 리포트 불가
    assert client.post(f"/customers/{c}/gap-report", headers=h).status_code == 409


def test_role_gates(client, auth):
    c = cid(client, auth)
    upload_all(client, auth, c)
    # 고객·운영자는 추출/판정/확정/승인 불가
    for role in ("customer", "ops"):
        h = auth[role]
        assert client.post(f"/customers/{c}/inventory/extract", headers=h).status_code == 403
        assert client.post(f"/customers/{c}/classify", headers=h).status_code == 403
    client.post(f"/customers/{c}/inventory/extract", headers=auth["consultant"])
    drafts = client.post(f"/customers/{c}/classify", headers=auth["consultant"]).json()
    assert all(d["status"] == "draft" for d in drafts)
    for role in ("customer", "ops"):
        r = client.post(f"/classifications/{drafts[0]['id']}/confirm", headers=auth[role])
        assert r.status_code == 403 and "컨설턴트" in r.json()["detail"]
        assert client.post(f"/customers/{c}/approve", headers=auth[role]).status_code == 403
        assert client.post(f"/customers/{c}/gap-report", headers=auth[role]).status_code == 403
        assert client.post(f"/customers/{c}/evidence/store-package", headers=auth[role]).status_code == 403
    assert client.patch(f"/customers/{c}/policy", json={"allow_external": False}, headers=auth["customer"]).status_code == 403
    assert client.post("/ops/jobs/golden_regression/run", headers=auth["consultant"]).status_code == 403
    assert client.get("/ops/summary", headers=auth["customer"]).status_code == 403
    assert client.post(f"/customers/{c}/documents", json=sample_docs()[0], headers=auth["ops"]).status_code == 403
    still = client.get(f"/customers/{c}/classifications", headers=auth["customer"]).json()["items"]
    assert all(i["status"] == "draft" for i in still)


def test_customer_cannot_see_other_customer(client, auth, db):
    from app.models import Customer

    other = Customer(name="B사 (가상)", description="가상", employees=5)
    db.add(other)
    db.commit()
    assert client.get(f"/customers/{other.id}", headers=auth["customer"]).status_code == 403
    assert client.get(f"/customers/{other.id}/evidence", headers=auth["customer"]).status_code == 403
    assert len(client.get("/customers", headers=auth["customer"]).json()) == 1
    assert len(client.get("/customers", headers=auth["consultant"]).json()) == 2


def test_full_flow_states_gaps_documents_evidence_and_audit(client, auth):
    c = cid(client, auth)
    hc = auth["consultant"]

    def state():
        return client.get(f"/customers/{c}", headers=hc).json()["state"]

    assert state() == "intake"
    drafts = to_confirmed(client, auth, c)
    assert len(drafts) == 3 and state() == "classification_confirmed"
    items = client.get(f"/customers/{c}/classifications", headers=auth["customer"]).json()["items"]
    by = {i["system_name"]: i for i in items}
    assert by["상품 이미지 생성"]["result"]["art31"]["output_labeling"]
    assert by["고객문의 요약"]["result"]["art31"]["internal_exemption"]
    assert all(i["status"] == "confirmed" and i["confirmed_by"] == "consultant@demo" for i in items)
    # 판정 근거는 조문과 사실 인용에 연결된다
    for i in items:
        facts = {f["field"]: f for f in i["system"]["facts"]}
        for r in i["result"]["rationale"]:
            assert r["articles"]
            assert all(f in facts for f in r["facts"])

    gap = client.post(f"/customers/{c}/gap-report", headers=hc).json()
    assert [f["code"] for f in gap["findings"]] == ["GAP-NOTICE", "GAP-METADATA", "GAP-TOS"]
    assert all(f["severity"] and f["owner"] and f["due_date"] and f["articles"] for f in gap["findings"])
    assert [s["name"] for s in gap["findings"][1]["systems"]] == ["상품 이미지 생성"]
    assert "법률 자문 아님" in gap["html"] and state() == "gap_report"

    docs = client.post(f"/customers/{c}/generated-documents/generate", headers=hc).json()
    assert {d["kind"] for d in docs} == {"notice_texts", "tos_clause", "gap_report"}  # 고영향 없음 → 위험관리 문서 없음
    assert state() == "documents_draft"
    full = client.get(f"/customers/{c}/generated-documents", headers=auth["customer"]).json()["items"]
    assert all(d["status"] == "draft" for d in full)
    tos = next(d for d in full if d["kind"] == "tos_clause")
    assert tos["unsupported"] == 1

    approved = client.post(f"/customers/{c}/approve", headers=hc).json()
    assert all(d["status"] == "approved" and d["approved_by"] == "consultant@demo" for d in approved)
    assert state() == "approved"
    ev = client.post(f"/customers/{c}/evidence/store-package", headers=hc).json()
    assert len(ev) == 4 and state() == "evidence_stored"
    v = client.post(f"/customers/{c}/evidence/verify", headers=auth["customer"]).json()
    assert v["ok"] and v["count"] == 4
    listing = client.get(f"/customers/{c}/evidence", headers=auth["customer"]).json()
    assert [e["seq"] for e in listing] == [1, 2, 3, 4] and listing[1]["prev_hash"] == listing[0]["chain_hash"]
    content = client.get(f"/evidence/{listing[0]['id']}/content", headers=auth["customer"])
    assert content.status_code == 200 and "상품 이미지 생성" in content.text
    assert "attachment" in content.headers["content-disposition"]
    # 증적 수정·삭제 경로는 없다
    assert client.delete(f"/evidence/{listing[0]['id']}/content", headers=hc).status_code == 405
    assert client.put(f"/customers/{c}/evidence", headers=hc).status_code == 405

    logs = client.get(f"/audit?customer_id={c}", headers=auth["ops"]).json()
    actions = [a["action"] for a in logs]
    for a in ["document.upload", "inventory.extract", "classification.draft", "classification.confirm",
              "gap_report.create", "documents.generate", "documents.approve", "evidence.store_package", "evidence.verify"]:
        assert a in actions, a
    assert all(a["actor"] and a["at"] and a["role"] for a in logs)
    confirm = next(a for a in logs if a["action"] == "classification.confirm")
    assert confirm["actor"] == "consultant@demo" and confirm["role"] == "consultant"


def test_classification_versions_are_kept(client, auth):
    c = cid(client, auth)
    to_confirmed(client, auth, c)
    client.post(f"/customers/{c}/classify", headers=auth["consultant"])
    items = client.get(f"/customers/{c}/classifications", headers=auth["consultant"]).json()["items"]
    for i in items:
        assert i["version"] == 2 and i["status"] == "draft"
        assert [(h["version"], h["status"]) for h in i["history"]] == [(1, "superseded"), (2, "draft")]


def test_consultant_can_correct_fact_and_reclassify(client, auth):
    c = cid(client, auth)
    to_confirmed(client, auth, c)
    systems = client.get(f"/customers/{c}/systems", headers=auth["consultant"]).json()
    img = next(s for s in systems if s["name"] == "상품 이미지 생성")
    assert client.patch(f"/systems/{img['id']}", json={"attributes": {"realistic_synthetic": True}},
                        headers=auth["customer"]).status_code == 403
    r = client.patch(f"/systems/{img['id']}", json={"attributes": {"realistic_synthetic": True, "bogus": 1}},
                     headers=auth["consultant"]).json()
    assert r["attributes"]["realistic_synthetic"] is True and "bogus" not in r["attributes"]
    assert any(f["field"] == "realistic_synthetic" and f["source"] == "consultant" for f in r["facts"])
    drafts = client.post(f"/customers/{c}/classify", headers=auth["consultant"]).json()
    assert next(d for d in drafts if d["system_id"] == img["id"])["result"]["art31"]["deepfake_notice"] is True


def test_data_policy_toggle_and_gateway_logs_and_tech_check(client, auth, db, monkeypatch):
    c = cid(client, auth)
    r = client.patch(f"/customers/{c}/policy", json={"allow_external": False, "monthly_budget_usd": 5},
                     headers=auth["consultant"]).json()
    assert r["allow_external"] is False and r["monthly_budget_usd"] == 5
    body = '{"ts":"2026-11-01T00:00:00Z","model":"가상모델-A","tokens":120}\n{"ts":"x","model":"가상모델-A"}\nnot json\n'
    assert client.post(f"/customers/{c}/gateway-logs", content=body, headers=auth["customer"]).status_code == 403
    g = client.post(f"/customers/{c}/gateway-logs", content=body, headers=auth["ops"])
    assert g.status_code == 201 and g.json()["records"] == 2 and g.json()["invalid_lines"] == 1
    assert client.post(f"/customers/{c}/gateway-logs", content="nope", headers=auth["ops"]).status_code == 400
    # 기술 점검(서비스 계층, HTTP 는 mock transport)
    from app import services
    from app.models import Customer

    cust = db.get(Customer, c)
    cust.tech_targets = {**cust.tech_targets, "base_url": "http://demo.test"}
    tc = services.run_tech_check(db, cust, "tester", client=httpx.Client(transport=demo_transport()))
    db.commit()
    assert (tc.passed, tc.failed) == (2, 2) and tc.evidence_id
    cust.tech_targets = {**cust.tech_targets, "base_url": "http://not-allowed.example"}
    db.commit()
    assert client.post(f"/customers/{c}/tech-check", headers=auth["ops"]).status_code == 400
    ev = client.get(f"/customers/{c}/evidence", headers=auth["ops"]).json()
    assert [e["kind"] for e in ev] == ["gateway_log", "tech_check"]
    assert client.post(f"/customers/{c}/evidence/verify", headers=auth["ops"]).json()["ok"]
