import json

from app import docgen
from app.engine import classify
from app.extractor import Doc, extract_mock, find, parse_llm_extraction
from app.kb import file_clauses_v1
from app.seed import sample_docs


def seed_docs():
    return [Doc(i + 1, d["title"], d["content"]) for i, d in enumerate(sample_docs())]


def systems_with_results():
    out = []
    for i, s in enumerate(extract_mock(seed_docs()), 1):
        out.append({"id": i, "name": s["name"], "attributes": s["attributes"], "result": classify(s["attributes"])})
    return out


def test_seed_docs_yield_three_systems_with_expected_facts():
    systems = {s["name"]: s for s in extract_mock(seed_docs())}
    assert list(systems) == ["상품 이미지 생성", "상품 설명 문구 생성", "고객문의 요약"]
    img, txt, summ = (systems[n]["attributes"] for n in systems)
    assert img["user_type"] == "B2C" and img["output_types"] == ["image"] and img["is_generative"]
    assert img["provider_type"] == "external_api" and img["realistic_synthetic"] is False and img["domain"] == "none"
    assert txt["user_type"] == "B2C" and txt["output_types"] == ["text"] and txt["is_generative"]
    assert summ["user_type"] == "internal" and summ["deployed_to_users"] is False
    r = [classify(a) for a in (img, txt, summ)]
    assert r[0]["art31"]["prior_notice"] and r[0]["art31"]["output_labeling"]
    assert r[1]["art31"]["prior_notice"] and r[1]["art31"]["output_labeling"]
    assert r[2]["art31"]["internal_exemption"] and not r[2]["art31"]["applicable"]
    assert all(x["high_impact"]["status"] == "not_applicable" and x["operator_role"] == "deployer" for x in r)


def test_every_extracted_fact_has_valid_citation_span():
    docs = {d.id: d for d in seed_docs()}
    n = 0
    for s in extract_mock(list(docs.values())):
        for f in s["facts"]:
            if f["source"] != "extracted":
                assert f["doc_id"] is None
                continue
            n += 1
            assert f["doc_id"] in docs and f["quote"]
            assert docs[f["doc_id"]].content[f["span_start"]:f["span_end"]] == f["quote"]
    assert n >= 15


def test_negation_handling():
    assert find(r"자체 ?개발", "자체 개발한 모델은 없습니다.") is None
    assert find(r"자체 ?개발", "자체 개발한 모델을 쓰며 외부 모델은 없습니다.") is not None
    assert find(r"지원자", "지원자의 서류를 사람의 검토 없이 처리한다") is not None


def test_llm_extraction_validates_quotes():
    docs = seed_docs()
    payload = {"systems": [{"name": "상품 이미지 생성", "facts": [
        {"field": "user_type", "value": "B2C", "doc_id": 2, "quote": "판매자에게 제공하는 B2C 기능"},
        {"field": "is_generative", "value": True, "doc_id": 4, "quote": "외부 이미지 생성 모델 API(가상 공급사 알파)를 호출합니다."},
        {"field": "domain", "value": "medical", "doc_id": 2, "quote": "문서에 없는 지어낸 인용"},
        {"field": "user_type", "value": "외계인", "doc_id": 2, "quote": "판매자"},
        {"field": "nonsense", "value": 1, "doc_id": 2, "quote": "판매자"},
    ]}]}
    systems = parse_llm_extraction("```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```", docs)
    s = systems[0]
    by = {(f["field"], f["supported"]) for f in s["facts"]}
    assert ("user_type", True) in by and ("is_generative", True) in by
    assert ("domain", False) in by  # 인용이 문서에 없으면 근거 없음으로 표시
    assert s["attributes"]["domain"] == "none"  # 근거 없는 사실은 판정에 쓰이지 않는다
    assert s["attributes"]["user_type"] == "B2C" and s["attributes"]["is_generative"] is True
    q = next(f for f in s["facts"] if f["field"] == "user_type")
    assert docs[1].content[q["span_start"]:q["span_end"]] == q["quote"]


def test_templates_have_article_refs_and_flag_unsupported():
    clauses = file_clauses_v1()
    systems = systems_with_results()
    notice = docgen.validate_paragraphs(docgen.notice_texts("A사 (가상)", systems), clauses)
    headings = " ".join(p["heading"] for p in notice)
    assert "문구 1" in headings and "문구 2" in headings and "문구 3" in headings
    assert all(p["supported"] for p in notice)
    assert all(p["articles"] for p in notice if p["kind"] == "normative")
    assert any("고객문의 요약" in p["text"] and p["articles"] == ["art31-exception"] for p in notice)
    assert any("메타데이터" in p["text"] and "상품 이미지 생성" in p["text"] for p in notice)
    tos = docgen.validate_paragraphs(docgen.tos_clause("A사 (가상)", systems), clauses)
    flagged = [p for p in tos if not p["supported"]]
    assert len(flagged) == 1 and "근거 미확인" in flagged[0]["flag"]  # ④항: 조문 근거 없는 문장
    bad = docgen.validate_paragraphs([docgen.P("근거 없는 주장", ["art999"])], clauses)
    assert not bad[0]["supported"] and "art999" in bad[0]["flag"]
    html = docgen.render_html("t", "A사 (가상)", "v", tos, clauses, "mock")
    assert "법률 자문 아님" in html and "근거 미확인" in html


def test_high_impact_documents():
    clauses = file_clauses_v1()
    attrs = {"provider_type": "self_developed", "domain": "hiring", "significant_impact": True, "human_review": "none"}
    system = {"id": 1, "name": "서류 평가 AI", "attributes": attrs, "result": classify(attrs)}
    rp = docgen.validate_paragraphs(docgen.risk_policy("B사 (가상)", system), clauses)
    ic = docgen.validate_paragraphs(docgen.impact_checklist("B사 (가상)", system), clauses)
    text = " ".join(p["text"] for p in rp)
    for kw in ["위험관리", "설명", "이용자 보호", "비상정지", "5년"]:
        assert kw in text
    assert all(p["supported"] for p in rp + ic) and len(ic) >= 6
    assert all(p["articles"] == ["art35"] for p in ic)


def test_llm_paragraph_parsing_and_validation():
    clauses = file_clauses_v1()
    out = docgen.parse_llm_paragraphs(json.dumps({"paragraphs": [
        {"heading": "h", "text": "고지합니다", "articles": ["art31-1"]},
        {"text": "지어낸 의무", "articles": []}, {"text": ""}]}, ensure_ascii=False))
    v = docgen.validate_paragraphs(out, clauses)
    assert [p["supported"] for p in v] == [True, False]
