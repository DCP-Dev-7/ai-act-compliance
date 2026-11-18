"""고객사 등록과 연습 시나리오(B~E): 권한·검증·감사 로그, 시나리오별 기대 판정과 갭."""
import pytest

from app import scenarios
from app.engine import classify, flatten
from app.extractor import Doc, extract_mock

from .conftest import login
from .test_workflow_api import cid as a_cid

BASE = {"name": "테스트사 (가상)", "industry": "기타", "employees": 10, "description": "[가상] 테스트",
        "allow_external": False, "monthly_budget_usd": 20, "subscribed": False}


def register(client, headers, expect=201, **over):
    r = client.post("/customers", json={**BASE, **over}, headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


def scenario_body(key, **over):
    s = scenarios.SCENARIOS[key]
    return {"name": s["name"], "industry": s["industry"], "employees": s["employees"], "description": s["description"],
            "allow_external": s["allow_external"], "monthly_budget_usd": s["monthly_budget_usd"],
            "subscribed": s["subscribed"], "current_state": s["current_state"], "scenario": key, **over}


def run_to_gap(client, auth, c):
    h = auth["consultant"]
    inv = client.post(f"/customers/{c}/inventory/extract", headers=h)
    assert inv.status_code == 200, inv.text
    drafts = client.post(f"/customers/{c}/classify", headers=h).json()
    for d in drafts:
        assert client.post(f"/classifications/{d['id']}/confirm", headers=h).status_code == 200
    gap = client.post(f"/customers/{c}/gap-report", headers=h)
    assert gap.status_code == 200, gap.text
    return {d["system_name"]: d["result"] for d in drafts}, gap.json()


# ---------- 시나리오 자료 → 추출 → 판정 (결정적) ----------

@pytest.mark.parametrize("key", list(scenarios.SCENARIOS))
def test_scenario_documents_yield_expected_classification(key):
    sc = scenarios.SCENARIOS[key]
    docs = [Doc(i + 1, d["title"], d["content"]) for i, d in enumerate(scenarios.scenario_docs(key))]
    got = {}
    for s in extract_mock(docs):
        r = classify(s["attributes"])
        got[s["name"]] = {**flatten(r), "art34_applicable": r["art34_applicable"],
                          "deemed_compliance_possible": r["deemed_compliance_possible"]}
        cited = [f for f in s["facts"] if f["source"] == "extracted"]
        by_id = {d.id: d.content for d in docs}
        assert all(by_id[f["doc_id"]][f["span_start"]:f["span_end"]] == f["quote"] for f in cited)
    assert got == sc["expected"]


def test_scenarios_are_fictional_and_labelled():
    assert scenarios.SELECTABLE == ["b", "c", "d", "e"]
    for key, sc in scenarios.SCENARIOS.items():
        assert "(가상)" in sc["name"] and sc["description"].startswith("[가상 데이터]")
        assert 3 <= len(sc["docs"]) <= 4
        for d in scenarios.scenario_docs(key):
            assert d["title"].startswith("[가상]") and d["content"].startswith("[가상 데이터]")
        assert sc["industry"] in scenarios.INDUSTRIES
        assert set(sc["current_state"]) == set(scenarios.STATE_KEYS)
    assert [i["key"] for i in scenarios.STATE_ITEMS] == scenarios.STATE_KEYS
    assert all(i["help"] and i["clause_ids"] and i["label"] for i in scenarios.STATE_ITEMS)


def test_state_item_clauses_exist_in_kb(client, auth):
    ids = {c["clause_id"] for c in client.get("/kb", headers=auth["consultant"]).json()["clauses"]}
    cat = client.get("/scenarios", headers=auth["customer"]).json()
    assert all(set(i["clause_ids"]) <= ids for i in cat["state_items"])
    assert [s["letter"] for s in cat["scenarios"]] == ["A", "B", "C", "D", "E"]
    assert "기타" in cat["industries"]
    assert client.get("/scenarios").status_code == 401


# ---------- 등록 API ----------

def test_register_blank_customer_roles_validation_audit(client, auth):
    assert client.post("/customers", json=BASE).status_code == 401
    assert client.post("/customers", json=BASE, headers=auth["customer"]).status_code == 403
    state = {"has_prior_notice": True, "risk_policy": True}
    c = register(client, auth["consultant"], current_state=state)
    assert c["name"] == "테스트사 (가상)" and c["state"] == "intake" and c["state_index"] == 0
    assert c["industry"] == "기타" and c["scenario"] == "" and not c["has_samples"] and c["is_synthetic"]
    assert c["allow_external"] is False and c["monthly_budget_usd"] == 20 and c["subscribed"] is False
    assert c["current_state"] == {**{k: False for k in scenarios.STATE_KEYS}, **state}
    assert c["documents_loaded"] == 0 and c["contact_email"] is None
    assert c["llm"]["effective"] == "mock"
    assert register(client, auth["consultant"], expect=409)["detail"].startswith("이미 같은 이름")
    # 운영자도 등록할 수 있다
    assert register(client, auth["ops"], name="운영자 등록사 (가상)")["state"] == "intake"
    # 검증
    for bad in [{"name": "   "}, {"industry": "없는업종"}, {"employees": -1}, {"monthly_budget_usd": -5},
                {"scenario": "a"}, {"scenario": "zzz"}, {"name": "x" * 101},
                {"contact": {"email": "no-at-sign", "password": "longenough1"}},
                {"contact": {"email": "x@y", "password": "short"}}]:
        r = client.post("/customers", json={**BASE, "name": "검증사", **bad}, headers=auth["consultant"])
        assert r.status_code == 422, (bad, r.text)
        assert isinstance(r.json()["detail"], str) and r.json()["detail"].startswith("입력값을 확인하세요")
    names = [x["name"] for x in client.get("/customers", headers=auth["consultant"]).json()]
    assert names == ["A사 (가상)", "테스트사 (가상)", "운영자 등록사 (가상)"]
    logs = client.get(f"/audit?customer_id={c['id']}", headers=auth["ops"]).json()
    create = next(x for x in logs if x["action"] == "customer.create")
    assert create["actor"] == "consultant@demo" and create["detail"]["scenario"] == "(빈 고객)"
    assert create["detail"]["current_state"]["risk_policy"] is True
    # 빈 고객은 샘플이 없고, 자료 없이는 다음 단계로 못 간다
    assert client.post(f"/customers/{c['id']}/documents/load-samples", headers=auth["consultant"]).status_code == 409
    assert client.post(f"/customers/{c['id']}/inventory/extract", headers=auth["consultant"]).status_code == 409
    assert client.post(f"/customers/{c['id']}/tech-check", headers=auth["consultant"]).status_code == 409


def test_blank_customer_manual_documents_flow(client, auth):
    c = register(client, auth["consultant"], current_state={"has_prior_notice": True})["id"]
    text = ("[가상 데이터] 테스트사 설문\nQ1. AI 활용 기능: 고객 상담 챗봇\n"
            "고객 상담 챗봇은 일반 이용자에게 제공하는 B2C 기능이며 외부 LLM API를 호출합니다.")
    r = client.post(f"/customers/{c}/documents", json={"kind": "questionnaire", "title": "[가상] 설문", "content": text},
                    headers=auth["consultant"])
    assert r.status_code == 201
    results, gap = run_to_gap(client, auth, c)
    assert results["고객 상담 챗봇"]["art31"]["prior_notice"] and results["고객 상담 챗봇"]["art31"]["output_labeling"]
    # 등록 폼에서 '사전 고지 있음'으로 답했으므로 GAP-NOTICE 는 없다
    assert [f["code"] for f in gap["findings"]] == ["GAP-LABEL", "GAP-TOS"]


def test_contact_login_sees_only_own_customer(client, auth):
    contact = {"email": "Owner@B-Company.Example", "password": "practice-1234", "name": "B사 담당자(가상)"}
    b = register(client, auth["consultant"], **scenario_body("b", contact=contact))
    assert b["contact_email"] == "owner@b-company.example" and b["documents_loaded"] == 4
    assert register(client, auth["consultant"], expect=409, name="다른사 (가상)", contact=contact)["detail"].startswith("이미 사용 중인")
    assert client.post("/auth/login", json={"email": "owner@b-company.example", "password": "wrong-pass"}).status_code == 401
    client.cookies.clear()
    h = login(client, "owner@b-company.example", "practice-1234")
    client.cookies.clear()
    me = client.get("/auth/me", headers=h).json()
    assert me["role"] == "customer" and me["customer_id"] == b["id"] and me["name"] == "B사 담당자(가상)"
    assert [x["name"] for x in client.get("/customers", headers=h).json()] == ["B사 (가상)"]
    a = a_cid(client, auth)
    for path in [f"/customers/{a}", f"/customers/{a}/documents", f"/customers/{a}/systems", f"/customers/{a}/classifications",
                 f"/customers/{a}/gap-report", f"/customers/{a}/generated-documents", f"/customers/{a}/evidence",
                 f"/customers/{a}/tech-checks"]:
        assert client.get(path, headers=h).status_code == 403, path
    assert client.post(f"/customers/{a}/documents", json={"kind": "other", "title": "x", "content": "y"}, headers=h).status_code == 403
    assert client.post(f"/customers/{a}/documents/load-samples", headers=h).status_code == 403
    assert client.post("/customers", json=BASE, headers=h).status_code == 403
    # A사 담당자도 B사를 볼 수 없다
    assert client.get(f"/customers/{b['id']}", headers=auth["customer"]).status_code == 403
    assert [x["name"] for x in client.get("/customers", headers=auth["customer"]).json()] == ["A사 (가상)"]
    # 감사 로그는 자기 고객사 것만, 비밀번호는 어디에도 남지 않는다
    logs = client.get(f"/audit?customer_id={a}", headers=h).json()
    assert logs and all(x["customer_id"] == b["id"] for x in logs)
    assert "practice-1234" not in str(client.get("/audit?limit=500", headers=auth["ops"]).json())
    # 자기 고객사에는 자료를 올릴 수 있다
    assert client.post(f"/customers/{b['id']}/documents", json={"kind": "other", "title": "[가상] 추가", "content": "메모"},
                       headers=h).status_code == 201


def test_passwords_of_registered_contacts_are_hashed(client, auth, db):
    from app.models import User

    register(client, auth["consultant"], contact={"email": "c@test.example", "password": "practice-1234"})
    u = db.query(User).filter(User.email == "c@test.example").one()
    assert u.password_hash.startswith("pbkdf2_sha256$") and "practice-1234" not in u.password_hash and u.role == "customer"


# ---------- 시나리오 전체 흐름 ----------

def test_scenario_b_high_impact_candidate_and_gaps(client, auth):
    b = register(client, auth["consultant"], **scenario_body("b"))
    c = b["id"]
    assert b["state"] == "intake" and b["scenario_letter"] == "B" and b["has_samples"] and not b["allow_external"]
    docs = client.get(f"/customers/{c}/documents", headers=auth["consultant"]).json()
    assert len(docs) == 4 and all(d["title"].startswith("[가상] B사") for d in docs)
    # 버튼을 다시 눌러도 중복 접수되지 않는다
    assert client.post(f"/customers/{c}/documents/load-samples", headers=auth["consultant"]).json() == []
    results, gap = run_to_gap(client, auth, c)
    auto, interview = results["지원서 자동 평가"], results["면접 답변 분석"]
    assert auto["high_impact"]["status"] == "candidate" and auto["high_impact"]["domain"] == "hiring"
    assert auto["high_impact"]["stage2_significant"] is True and auto["high_impact"]["human_review"] == "none"
    assert auto["art34_applicable"] and auto["art35_applicable"] and auto["art31"]["prior_notice"]
    assert not auto["is_generative"] and not auto["art31"]["output_labeling"] and not auto["art33_recommended"]
    assert interview["high_impact"]["status"] == "candidate" and interview["high_impact"]["issue"]
    assert interview["art33_recommended"] and "art33" in interview["applicable_articles"]
    codes = [f["code"] for f in gap["findings"]]
    assert codes == scenarios.SCENARIOS["b"]["expected_gaps"]
    assert {"GAP-RISK", "GAP-EXPLAIN", "GAP-OVERSIGHT", "GAP-RETENTION"} <= set(codes)
    kinds = {d["kind"] for d in client.post(f"/customers/{c}/generated-documents/generate", headers=auth["consultant"]).json()}
    assert {"risk_policy", "impact_checklist", "notice_texts"} <= kinds


def test_scenario_c_excluded_possible_with_deemed_compliance(client, auth):
    c = register(client, auth["consultant"], **scenario_body("c"))["id"]
    results, gap = run_to_gap(client, auth, c)
    r = results["흉부 영상 판독 보조"]
    assert r["high_impact"]["status"] == "excluded_possible" and r["high_impact"]["domain"] == "medical"
    assert r["high_impact"]["issue"] and r["art33_recommended"] and not r["art34_applicable"]
    assert r["deemed_compliance_possible"] and "deemed" in r["applicable_articles"]
    assert any("디지털의료제품법" in x["text"] for x in r["rationale"])
    assert [f["code"] for f in gap["findings"]] == ["GAP-CONFIRM"]


def test_scenario_d_internal_only_has_no_obligations(client, auth):
    c = register(client, auth["consultant"], **scenario_body("d"))["id"]
    results, gap = run_to_gap(client, auth, c)
    assert set(results) == {"사내 문서 요약", "코드 작성 도우미"}
    for r in results.values():
        assert r["art31"]["internal_exemption"] and not r["art31"]["applicable"]
        assert not r["art31"]["prior_notice"] and not r["art31"]["output_labeling"]
        assert r["high_impact"]["status"] == "not_applicable" and not r["art34_applicable"] and not r["art33_recommended"]
    assert gap["findings"] == [] and gap["no_gap_note"].startswith("의무 거의 없음")
    assert "의무 거의 없음" in gap["html"]
    got = client.get(f"/customers/{c}/gap-report", headers=auth["consultant"]).json()["report"]
    assert got["no_gap_note"] == gap["no_gap_note"]
    # 의무가 없어도 흐름은 끝까지 간다(고지 문서는 만들지 않고 갭 리포트만 승인·보관)
    h = auth["consultant"]
    kinds = [d["kind"] for d in client.post(f"/customers/{c}/generated-documents/generate", headers=h).json()]
    assert kinds == ["gap_report"]
    assert client.post(f"/customers/{c}/approve", headers=h).status_code == 200
    assert client.post(f"/customers/{c}/evidence/store-package", headers=h).status_code == 200
    assert client.get(f"/customers/{c}", headers=h).json()["state"] == "evidence_stored"


def test_scenario_e_deepfake_notice_and_audio_gaps(client, auth):
    c = register(client, auth["consultant"], **scenario_body("e"))["id"]
    results, gap = run_to_gap(client, auth, c)
    r = results["맞춤 음성 합성"]
    assert r["is_generative"] and r["art31"]["prior_notice"] and r["art31"]["output_labeling"] and r["art31"]["deepfake_notice"]
    assert r["high_impact"]["status"] == "not_applicable" and "art31-3" in r["applicable_articles"]
    assert r["facts_used"]["output_types"] == ["audio"]
    assert [f["code"] for f in gap["findings"]] == ["GAP-LABEL", "GAP-METADATA", "GAP-DEEPFAKE"]


def test_registration_form_answers_override_scenario_preset(client, auth):
    """시나리오로 미리 채운 설문을 폼에서 고치면 고친 값이 갭 리포트에 반영된다."""
    state = {**scenarios.SCENARIOS["e"]["current_state"], "labels_outputs_visible": True}
    c = register(client, auth["consultant"], **scenario_body("e", current_state=state))["id"]
    _, gap = run_to_gap(client, auth, c)
    assert [f["code"] for f in gap["findings"]] == ["GAP-METADATA", "GAP-DEEPFAKE"]


def test_a_company_samples_still_load(client, auth):
    a = a_cid(client, auth)
    cust = client.get(f"/customers/{a}", headers=auth["consultant"]).json()
    assert cust["scenario"] == "a" and cust["has_samples"] and cust["tech_check_available"]
    out = client.post(f"/customers/{a}/documents/load-samples", headers=auth["customer"])
    assert out.status_code == 201 and [d["title"] for d in out.json()] == [
        "[가상] 사전 설문 응답", "[가상] 서비스 소개서", "[가상] 이용약관", "[가상] 개발 문서 발췌"]
    assert client.post(f"/customers/{a}/documents/load-samples", headers=auth["customer"]).json() == []
    _, gap = run_to_gap(client, auth, a)
    assert [f["code"] for f in gap["findings"]] == scenarios.SCENARIOS["a"]["expected_gaps"]
