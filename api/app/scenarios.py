"""고객사 등록용 기준 정보와 연습 시나리오(전부 가상).

- INDUSTRIES      : 등록 폼의 업종 목록
- STATE_ITEMS     : '현재 이행 상태' 설문 8문항 — 쉬운 설명과 관련 조문(KB clause_id)
- SCENARIOS       : 연습 시나리오 A~E. A 는 시드 고객(A사)이고, B~E 는 등록할 때 고를 수 있다.
                    expected 는 "이 시나리오를 돌리면 나와야 하는 판정"이며 테스트가 실제 파이프라인 결과와 대조한다.

시나리오의 회사·문서·수치는 모두 지어낸 것이며 실제 기업·서비스와 무관하다. 법률 자문이 아니다.
"""
from __future__ import annotations

from typing import Any

from .config import DATA_DIR
from .gap import STATE_LABELS

SCENARIO_DIR = DATA_DIR / "scenarios"
SEED_DIR = DATA_DIR / "seed"

INDUSTRIES = [
    "전자상거래·유통", "인사·채용", "의료·헬스케어", "금융·보험", "제조", "교육", "미디어·콘텐츠",
    "IT·소프트웨어", "공공·행정", "교통·물류", "에너지·인프라", "기타",
]

STATE_KEYS = list(STATE_LABELS)  # 갭 리포트가 쓰는 8개 키와 같은 순서

STATE_ITEMS: list[dict[str, Any]] = [
    {"key": "has_prior_notice", "clause_ids": ["art31-1"],
     "help": "서비스를 쓰기 전에 \"이 서비스는 AI로 운용됩니다\"라고 알리는 문구가 앱·화면·계약서에 있는가. (제31조 사전 고지)"},
    {"key": "labels_outputs_visible", "clause_ids": ["art31-2"],
     "help": "AI가 만든 글·이미지·음성에 사람이 알아볼 수 있는 'AI 생성' 표시가 붙는가. (제31조 생성물 표시)"},
    {"key": "embeds_metadata", "clause_ids": ["art31-2"],
     "help": "만든 파일 안에 기계가 읽을 수 있는 AI 생성 정보(메타데이터·워터마크)를 넣는가. (제31조 생성물 표시의 다른 방식)"},
    {"key": "tos_has_ai_clause", "clause_ids": ["art31-1"],
     "help": "이용약관·계약서에 AI 기능을 제공한다는 조항이 있는가. 사전 고지를 약관으로 하는 방법이다. (제31조 사전 고지)"},
    {"key": "risk_policy", "clause_ids": ["art34"],
     "help": "AI가 잘못 판단했을 때의 위험을 찾아내고 줄이는 방안을 문서로 정해 운영하는가. 고영향 AI에만 요구된다. (제34조)"},
    {"key": "explanation_method", "clause_ids": ["art34"],
     "help": "AI가 왜 그런 결과를 냈는지 당사자에게 설명할 방법이 있는가. 고영향 AI에만 요구된다. (제34조)"},
    {"key": "human_oversight_killswitch", "clause_ids": ["art34"],
     "help": "사람이 AI를 감독하고, 문제가 생기면 멈출 수 있는 절차(비상정지)가 있는가. 고영향 AI에만 요구된다. (제34조)"},
    {"key": "doc_retention_5y", "clause_ids": ["art34"],
     "help": "안전성·신뢰성 조치 내용을 확인할 수 있는 문서를 5년간 보관하는가. 고영향 AI에만 요구된다. (제34조)"},
]
for _item in STATE_ITEMS:
    _item["label"] = STATE_LABELS[_item["key"]]


def _state(**true_keys: bool) -> dict[str, bool]:
    return {k: bool(true_keys.get(k, False)) for k in STATE_KEYS}


def _exp(role: str, gen: bool, notice: bool, label: bool, deepfake: bool, internal: bool, status: str, art33: bool,
         art34: bool = False, deemed: bool = False) -> dict[str, Any]:
    return {"operator_role": role, "is_generative": gen, "prior_notice": notice, "output_labeling": label,
            "deepfake_notice": deepfake, "internal_exemption": internal, "high_impact_status": status,
            "art33_recommended": art33, "art34_applicable": art34, "deemed_compliance_possible": deemed}


_A_DOCS = [
    {"kind": "questionnaire", "title": "[가상] 사전 설문 응답", "file": "questionnaire.txt"},
    {"kind": "service_intro", "title": "[가상] 서비스 소개서", "file": "service_intro.txt"},
    {"kind": "tos", "title": "[가상] 이용약관", "file": "tos.txt"},
    {"kind": "dev_doc", "title": "[가상] 개발 문서 발췌", "file": "dev_doc.txt"},
]

SCENARIOS: dict[str, dict[str, Any]] = {
    "a": {
        "letter": "A", "name": "A사 (가상)", "title": "생성형 AI로 상품 이미지·문구를 만들어 주는 B2C 앱",
        "industry": "전자상거래·유통", "employees": 40, "selectable": False,
        "description": "[가상 데이터] 직원 40명. 생성형 AI로 상품 이미지를 만들어 주는 B2C 서비스 '상품 페이지 도우미' 운영. 외부 LLM 2종 사용.",
        "allow_external": True, "monthly_budget_usd": 50.0, "subscribed": True,
        "current_state": _state(labels_outputs_visible=True),
        "lesson": "가장 흔한 경우. 외부 AI를 붙여 고객에게 생성 결과물을 주면 '알리고(사전 고지) 표시하는(생성물 표시)' 의무가 생긴다.",
        "points": ["외부 API만 써도 '이용사업자'로서 의무 대상이 된다", "고객에게 주는 기능과 직원만 쓰는 기능은 판정이 다르다",
                   "고영향 영역이 아니므로 제34·35조는 해당 없음"],
        "expected": {
            "상품 이미지 생성": _exp("deployer", True, True, True, False, False, "not_applicable", False),
            "상품 설명 문구 생성": _exp("deployer", True, True, True, False, False, "not_applicable", False),
            "고객문의 요약": _exp("deployer", True, False, False, False, True, "not_applicable", False),
        },
        "expected_gaps": ["GAP-NOTICE", "GAP-METADATA", "GAP-TOS"],
        "dir": SEED_DIR, "docs": _A_DOCS,
    },
    "b": {
        "letter": "B", "name": "B사 (가상)", "title": "채용 지원서를 AI가 점수화해 자동 탈락시키는 솔루션",
        "industry": "인사·채용", "employees": 120, "selectable": True,
        "description": "[가상 데이터] 직원 120명. 기업 인사팀에 채용 솔루션 '채용 도우미'를 공급. AI가 지원서를 점수화해 기준 미만은 "
                       "사람 검토 없이 자동 탈락시키고, 면접 답변 분석 결과는 형식적으로 일괄 승인한다.",
        "allow_external": False, "monthly_budget_usd": 50.0, "subscribed": True,
        "current_state": _state(),
        "lesson": "채용은 법이 정한 고영향 영역이다. 사람의 실질적인 검토 없이 당락을 정하면 '고영향 후보'가 되어 의무가 크게 늘어난다.",
        "points": ["생성형이 아니어도 고영향이면 사전 고지 의무가 생긴다", "제34조 책무(위험관리·설명·사람의 감독·문서 5년 보관)와 제35조 영향평가 준비가 필요하다",
                   "사람이 '일괄 승인'만 하는 형식적 검토는 제외 사유로 인정되기 어렵다 → 쟁점이므로 제33조 확인 요청을 권고한다",
                   "지원자 정보가 담긴 자료이므로 '외부 반출 금지'로 등록한다"],
        "expected": {
            "지원서 자동 평가": _exp("developer", False, True, False, False, False, "candidate", False, art34=True),
            "면접 답변 분석": _exp("developer", False, True, False, False, False, "candidate", True, art34=True),
        },
        "expected_gaps": ["GAP-NOTICE", "GAP-TOS", "GAP-RISK", "GAP-EXPLAIN", "GAP-OVERSIGHT", "GAP-RETENTION",
                          "GAP-IMPACT", "GAP-CONFIRM"],
        "dir": SCENARIO_DIR / "b",
        "docs": [
            {"kind": "questionnaire", "title": "[가상] B사 사전 설문 응답", "file": "questionnaire.txt"},
            {"kind": "service_intro", "title": "[가상] B사 서비스 소개서", "file": "service_intro.txt"},
            {"kind": "tos", "title": "[가상] B사 이용약관 발췌", "file": "tos.txt"},
            {"kind": "dev_doc", "title": "[가상] B사 개발 문서 발췌", "file": "dev_doc.txt"},
        ],
    },
    "c": {
        "letter": "C", "name": "C사 (가상)", "title": "의료 영상에서 병변 의심 영역을 표시하고, 의사가 최종 판독하는 보조 소프트웨어",
        "industry": "의료·헬스케어", "employees": 60, "selectable": True,
        "description": "[가상 데이터] 직원 60명. 병원에 흉부 영상 판독 보조 소프트웨어를 공급. AI는 병변 의심 영역만 표시하고 "
                       "전문의가 직접 확인해 판독문에 서명한다. 의료기기 인허가(디지털의료제품법)를 받았다.",
        "allow_external": False, "monthly_budget_usd": 50.0, "subscribed": True,
        "current_state": _state(has_prior_notice=True, tos_has_ai_clause=True, risk_policy=True, explanation_method=True,
                                human_oversight_killswitch=True, doc_retention_5y=True),
        "lesson": "의료는 고영향 영역이지만, 사람이 실질적으로 검토·통제하면 고영향에서 제외될 수 있다. 다만 해석상 쟁점이라 확인 요청을 권고한다.",
        "points": ["B사와 같은 '고영향 영역'인데 결과가 다르다 — 차이는 사람의 검토가 실질적인가",
                   "'제외 가능(쟁점)'은 확정이 아니다 → 제33조에 따라 과기정통부에 확인을 요청할 수 있다(30일 내 회신)",
                   "디지털의료제품법 등 다른 법에 따라 동등한 조치를 이미 했다면 이 법의 의무를 이행한 것으로 볼 수 있다(이행 간주)",
                   "고영향 영역이므로 사전 고지는 필요하다(보수적 판단)"],
        "expected": {
            "흉부 영상 판독 보조": _exp("developer", False, True, False, False, False, "excluded_possible", True, deemed=True),
        },
        "expected_gaps": ["GAP-CONFIRM"],
        "dir": SCENARIO_DIR / "c",
        "docs": [
            {"kind": "questionnaire", "title": "[가상] C사 사전 설문 응답", "file": "questionnaire.txt"},
            {"kind": "service_intro", "title": "[가상] C사 서비스 소개서", "file": "service_intro.txt"},
            {"kind": "tos", "title": "[가상] C사 공급 계약서 발췌", "file": "contract.txt"},
            {"kind": "dev_doc", "title": "[가상] C사 개발 문서 발췌", "file": "dev_doc.txt"},
        ],
    },
    "d": {
        "letter": "D", "name": "D사 (가상)", "title": "직원만 쓰는 사내 문서 요약·코드 도우미(고객에게는 제공 안 함)",
        "industry": "제조", "employees": 200, "selectable": True,
        "description": "[가상 데이터] 직원 200명. 산업용 부품 제조사. 임직원만 쓰는 사내 문서 요약과 코드 작성 도우미에 외부 LLM을 사용하며, "
                       "고객에게 제공하는 제품·서비스에는 AI 기능이 없다.",
        "allow_external": True, "monthly_budget_usd": 50.0, "subscribed": False,
        "current_state": _state(),
        "lesson": "AI를 쓴다고 모두 의무가 생기는 것은 아니다. 내부 업무에만 쓰고 고객에게 제공하지 않으면 고지·표시 의무의 예외다.",
        "points": ["생성형 AI라도 내부 업무용이면 제31조 고지·표시 의무에서 제외된다", "고영향 영역도 아니므로 갭(해야 할 일)이 0건으로 나온다 — 오류가 아니라 정상 결과",
                   "남는 일: 내부 업무용이라는 사실을 기록해 두고, 나중에 고객에게 제공하게 되면 다시 판정한다"],
        "expected": {
            "사내 문서 요약": _exp("deployer", True, False, False, False, True, "not_applicable", False),
            "코드 작성 도우미": _exp("deployer", True, False, False, False, True, "not_applicable", False),
        },
        "expected_gaps": [],
        "dir": SCENARIO_DIR / "d",
        "docs": [
            {"kind": "questionnaire", "title": "[가상] D사 사전 설문 응답", "file": "questionnaire.txt"},
            {"kind": "service_intro", "title": "[가상] D사 회사 소개 및 사내 AI 사용 현황", "file": "service_intro.txt"},
            {"kind": "dev_doc", "title": "[가상] D사 개발 문서 발췌", "file": "dev_doc.txt"},
        ],
    },
    "e": {
        "letter": "E", "name": "E사 (가상)", "title": "실제 목소리와 구분하기 어려운 AI 음성 합성 앱(B2C)",
        "industry": "미디어·콘텐츠", "employees": 25, "selectable": True,
        "description": "[가상 데이터] 직원 25명. 일반 이용자에게 글을 음성으로 바꿔 주는 앱 '목소리 공방' 운영. 결과 음성은 실제 목소리와 "
                       "구분하기 어렵고, 파일에 워터마크·메타데이터가 없다.",
        "allow_external": True, "monthly_budget_usd": 50.0, "subscribed": True,
        "current_state": _state(has_prior_notice=True, tos_has_ai_clause=True),
        "lesson": "실제와 구분하기 어려운 결과물(딥페이크성)은 일반 생성물보다 한 단계 더 강한 '명확한 고지·표시'가 필요하다.",
        "points": ["A사와 같은 생성형 B2C지만 '실제와 구분하기 어려운 음성'이라 딥페이크 고지(제31조)가 추가된다",
                   "사전 고지와 약관은 이미 있어도, 결과물 자체의 표시(안내·워터마크·메타데이터)가 없으면 갭이 남는다",
                   "고영향 영역은 아니므로 제34·35조는 해당 없음"],
        "expected": {
            "맞춤 음성 합성": _exp("deployer", True, True, True, True, False, "not_applicable", False),
        },
        "expected_gaps": ["GAP-LABEL", "GAP-METADATA", "GAP-DEEPFAKE"],
        "dir": SCENARIO_DIR / "e",
        "docs": [
            {"kind": "questionnaire", "title": "[가상] E사 사전 설문 응답", "file": "questionnaire.txt"},
            {"kind": "service_intro", "title": "[가상] E사 서비스 소개서", "file": "service_intro.txt"},
            {"kind": "tos", "title": "[가상] E사 이용약관 발췌", "file": "tos.txt"},
            {"kind": "dev_doc", "title": "[가상] E사 개발 문서 발췌", "file": "dev_doc.txt"},
        ],
    },
}

SELECTABLE = [k for k, s in SCENARIOS.items() if s["selectable"]]


def scenario_docs(key: str, current_state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """시나리오의 가상 자료. 설문 응답 문서에는 구조화된 '현재 이행 상태'를 함께 싣는다.

    current_state 를 주면(등록 폼에서 고친 값) 그 값을, 없으면 시나리오 기본값을 쓴다.
    """
    sc = SCENARIOS[key]
    state = dict(current_state) if current_state is not None else dict(sc["current_state"])
    return [{"kind": d["kind"], "title": d["title"],
             "data": {"current_state": state} if d["kind"] == "questionnaire" else None,
             "content": (sc["dir"] / d["file"]).read_text(encoding="utf-8")} for d in sc["docs"]]


def public_view() -> dict[str, Any]:
    """등록 폼·학습 화면에 내려주는 기준 정보."""
    return {
        "industries": INDUSTRIES,
        "state_items": STATE_ITEMS,
        "scenarios": [{
            "key": k, "letter": s["letter"], "name": s["name"], "title": s["title"], "industry": s["industry"],
            "employees": s["employees"], "description": s["description"], "allow_external": s["allow_external"],
            "monthly_budget_usd": s["monthly_budget_usd"], "subscribed": s["subscribed"],
            "current_state": s["current_state"], "selectable": s["selectable"], "lesson": s["lesson"],
            "points": s["points"], "expected_gaps": s["expected_gaps"],
            "systems": [{"name": n, **e} for n, e in s["expected"].items()],
            "documents": [{"kind": d["kind"], "title": d["title"]} for d in s["docs"]],
        } for k, s in SCENARIOS.items()],
    }
