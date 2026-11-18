"""웹 '자료 올리기'의 종류별 작성 예시(web/lib/docExamples.json)가 mock 추출에서 기대대로 읽히는지 확인한다.

예시 문구를 고쳤다가 키워드 규칙과 어긋나면 이 테스트가 실패한다.
"""
import json
from pathlib import Path

import pytest

from app.extractor import Doc, extract_mock

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "web" / "lib" / "docExamples.json"
KINDS = ["questionnaire", "service_intro", "tos", "dev_doc", "other"]
# 기능별 기대값: 이용자 유형, 모델 조달 방식, 생성형 여부
EXPECT = {
    "고객 상담 챗봇": {"user_type": "B2C", "provider_type": "external_api", "is_generative": True},
    "사내 회의록 요약": {"user_type": "internal", "provider_type": "external_api", "is_generative": True},
}

pytestmark = pytest.mark.skipif(not EXAMPLES.exists(), reason="저장소 전체가 아닌 곳(예: api 이미지 안)에서는 건너뜀")


def _load():
    return json.loads(EXAMPLES.read_text(encoding="utf-8"))


def _check(systems):
    assert systems, "기능을 하나도 찾지 못했습니다"
    for s in systems:
        assert s["name"] in EXPECT, f"예상하지 못한 기능 이름: {s['name']}"
        for k, v in EXPECT[s["name"]].items():
            assert s["attributes"][k] == v, f"{s['name']}.{k} = {s['attributes'][k]!r} (기대 {v!r})"


def test_every_kind_has_example():
    data = _load()
    assert set(data) == set(KINDS)
    for k in KINDS:
        assert data[k]["title"].startswith("[가상]") and data[k]["content"].startswith("[가상 데이터]")
        assert data[k]["tip"]


@pytest.mark.parametrize("kind", KINDS)
def test_example_alone(kind):
    ex = _load()[kind]
    _check(extract_mock([Doc(1, ex["title"], ex["content"])]))


def test_examples_together():
    data = _load()
    systems = extract_mock([Doc(i, data[k]["title"], data[k]["content"]) for i, k in enumerate(KINDS)])
    assert sorted(s["name"] for s in systems) == sorted(EXPECT)
    _check(systems)


def test_feature_list_line_does_not_leak():
    """'AI 활용 기능: A, B' 목록 줄의 단어(예: '사내')가 다른 기능의 사실로 섞이지 않아야 한다."""
    text = ("AI 활용 기능: 고객 상담 챗봇, 사내 회의록 요약\n"
            "고객 상담 챗봇은 일반 이용자에게 제공하며 외부 LLM API를 호출해 답변을 만듭니다.\n"
            "사내 회의록 요약은 임직원만 쓰는 내부 업무용 도구입니다.")
    by = {s["name"]: s["attributes"] for s in extract_mock([Doc(1, "t", text)])}
    assert by["고객 상담 챗봇"]["user_type"] == "B2C"
    assert by["사내 회의록 요약"]["user_type"] == "internal"
