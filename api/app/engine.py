"""M3 진단 엔진: 법령 요약을 코드로 옮긴 결정 트리(규칙 우선).

LLM은 사실(facts)만 채우고, 판정은 전부 이 모듈의 결정적 규칙으로 한다.
결과는 '초안'이며 컨설턴트 확정 전에는 효력이 없다. 법률 자문이 아니다.
"""
from __future__ import annotations

from typing import Any

ENGINE_VERSION = "rules-1.0"

DOMAIN_LABELS = {
    "none": "해당 없음",
    "medical": "의료 진단·치료·의료기기",
    "essential_infra": "에너지·먹는물 등 필수 인프라",
    "nuclear": "원자력",
    "biometric_investigation": "범죄 수사 생체인식",
    "hiring": "채용",
    "lending": "대출 심사",
    "transport": "교통수단 주요 운영(레벨4 이상 자율주행 등)",
    "public_service": "공공서비스 핵심 의사결정",
    "education_eval": "교육 — 학생 평가",
}
ROLE_LABELS = {"developer": "인공지능개발사업자", "deployer": "인공지능이용사업자"}
STATUS_LABELS = {
    "not_applicable": "고영향 해당 없음(초안)",
    "candidate": "고영향 후보",
    "excluded_possible": "고영향 영역이나 제외 가능(쟁점)",
}
FLOPS_THRESHOLD = 1e26

FACT_DEFAULTS: dict[str, Any] = {
    "purpose": "",
    "provider_type": "unknown",  # external_api | self_developed | unknown
    "model_provider": "",
    "is_generative": False,
    "user_type": "unknown",  # B2C | B2B | internal | unknown
    "output_types": [],  # text | image | audio | video
    "realistic_synthetic": False,
    "domain": "none",
    "significant_impact": None,  # True | False | None(불명)
    "human_review": "unknown",  # substantive | formal | none | unknown
    "deployed_to_users": True,
    "cumulative_flops": None,
    "foreign_operator": False,
    "other_law_compliance": "",
}


def normalize(facts: dict[str, Any]) -> dict[str, Any]:
    f = dict(FACT_DEFAULTS)
    f.update({k: v for k, v in facts.items() if k in FACT_DEFAULTS})
    if f["domain"] not in DOMAIN_LABELS:
        f["domain"] = "none"
    if f["output_types"] is None:
        f["output_types"] = []
    return f


def classify(facts: dict[str, Any]) -> dict[str, Any]:
    f = normalize(facts)
    rationale: list[dict[str, Any]] = []
    assumptions: list[str] = []

    def why(text: str, articles: list[str], fact_fields: list[str]) -> None:
        rationale.append({"text": text, "articles": articles, "facts": fact_fields})

    # 1) 사업자 지위 (제2조)
    if f["provider_type"] == "self_developed":
        role = "developer"
        why("인공지능을 자체 개발하여 제공하므로 개발사업자로 본다.", ["art2-operator"], ["provider_type"])
    else:
        role = "deployer"
        if f["provider_type"] == "unknown":
            assumptions.append("모델 조달 방식이 자료에서 확인되지 않아 이용사업자로 가정함 — 확인 필요")
            why("모델 조달 방식이 확인되지 않아 이용사업자로 가정한다(확인 필요).", ["art2-operator"], [])
        else:
            why("외부에서 제공받은 인공지능(API 등)을 이용해 서비스를 제공하므로 이용사업자로 본다.",
                ["art2-operator"], ["provider_type"])

    # 2) 생성형 여부 (제2조)
    generative = bool(f["is_generative"])
    if generative:
        why("글·이미지·음성·영상 등 결과물을 생성하므로 생성형 인공지능에 해당한다.",
            ["art2-generative"], ["is_generative", "output_types"])

    # 3) 고영향 2단계 판단 (제2조, 제33조)
    domain = f["domain"]
    stage1 = domain != "none"
    sig = f["significant_impact"]
    hr = f["human_review"]
    issue = False
    issue_note = ""
    if not stage1:
        status = "not_applicable"
        why("법이 정한 고영향 영역(의료, 필수 인프라, 채용·대출 심사 등)에서 활용되지 않는다(1단계 불충족).",
            ["art2-highimpact"], ["domain"])
    elif sig is False:
        status = "not_applicable"
        why(f"영역({DOMAIN_LABELS[domain]})에는 해당하나 생명·신체·기본권에 중대한 영향을 미치는 용도가 아니다(2단계 불충족).",
            ["art2-highimpact"], ["domain", "significant_impact"])
    else:
        why(f"활용 영역이 고영향 영역({DOMAIN_LABELS[domain]})에 해당한다(1단계 충족).",
            ["art2-highimpact"], ["domain"])
        if sig is None:
            assumptions.append("중대한 영향 여부가 자료에서 확인되지 않아 보수적으로 후보로 분류함")
            why("생명·신체·기본권에 대한 중대한 영향 여부가 불명확하여 보수적으로 후보로 분류한다(2단계 불명).",
                ["art2-highimpact", "art33"], [])
        else:
            why("결과가 사람의 생명·신체·기본권에 중대한 영향을 미칠 수 있다(2단계 충족).",
                ["art2-highimpact"], ["significant_impact"])
        if hr == "substantive":
            status = "excluded_possible"
            issue = True
            issue_note = "사람이 실질적으로 검토·통제하므로 고영향에서 제외될 수 있음 — 쟁점(확인 요청 권고)"
            why("사람이 최종 결정을 실질적으로 검토·통제하므로 고영향에서 제외될 수 있다. 다만 해석상 쟁점이므로 확인 요청을 권고한다.",
                ["art2-highimpact", "art33"], ["human_review"])
        else:
            status = "candidate"
            if hr == "formal":
                issue = True
                issue_note = "사람의 검토가 형식적이어서 제외 사유로 인정되기 어려움 — 쟁점"
                why("사람의 검토가 형식적 수준이어서 제외 사유로 인정되기 어렵다(쟁점). 고영향 후보로 본다.",
                    ["art2-highimpact", "art33"], ["human_review"])
            elif hr == "none":
                why("사람의 실질적 검토 없이 결과가 적용되므로 고영향 후보로 본다.",
                    ["art2-highimpact"], ["human_review"])
    art33 = stage1 and sig is not False and (sig is None or hr in ("substantive", "formal"))
    if art33:
        why("고영향 해당 여부가 불명확하므로 과기정통부 확인 요청을 권고한다(30일 내 회신, 연장 시 최대 60일, 이의 시 10일 내 재확인).",
            ["art33"], [])

    # 4) 제31조 투명성
    internal = f["user_type"] == "internal"
    internal_exemption = internal and status == "not_applicable"
    prior_notice = (not internal_exemption) and (generative or status in ("candidate", "excluded_possible"))
    labeling = (not internal_exemption) and generative
    deepfake = labeling and bool(f["realistic_synthetic"])
    if internal_exemption:
        why("내부 업무 용도로만 사용하고 이용자에게 제공하지 않으므로 고지·표시 의무의 예외에 해당한다.",
            ["art31-exception"], ["user_type"])
    else:
        if internal:
            why("내부 사용이지만 고영향 영역에서 영향받는 사람이 있으므로 예외를 적용하지 않는다(보수적 판단).",
                ["art31-exception", "art31-1"], ["user_type", "domain"])
        if prior_notice:
            basis = "생성형" if generative else "고영향(후보)"
            why(f"{basis} 인공지능 기반 서비스이므로 이용자에게 AI 기반 운용 사실을 사전 고지해야 한다(약관·계약서·UI 등).",
                ["art31-1", "art43"], ["is_generative", "user_type"] if generative else ["domain"])
        if labeling:
            why("생성 결과물에 AI 생성 사실을 표시해야 한다(가시 표시 또는 워터마크·메타데이터).",
                ["art31-2"], ["is_generative", "output_types"])
        if deepfake:
            why("실제와 구분하기 어려운 결과물이므로 이용자가 명확히 인식할 수 있게 고지·표시해야 한다.",
                ["art31-3"], ["realistic_synthetic"])
    if (prior_notice or labeling) and not f["deployed_to_users"] and not internal:
        assumptions.append("아직 이용자에게 제공 전 — 출시 시점부터 의무 적용")

    # 5) 고영향 사업자 책무 (제34조, 제35조)
    if status == "candidate":
        why("고영향 후보이므로 위험관리 방안, 설명 방안, 이용자 보호, 사람의 관리·감독, 문서 5년 보관 준비가 필요하다.",
            ["art34"], [])
        why("고영향 인공지능 영향평가를 실시하도록 노력해야 한다.", ["art35"], [])

    # 6) 기타
    flops = f["cumulative_flops"]
    art32 = bool(flops and float(flops) >= FLOPS_THRESHOLD)
    if art32:
        why("학습 누적 연산량이 10^26 FLOPs 이상이므로 안전성 확보 의무 대상이다.", ["art32"], ["cumulative_flops"])
    art36 = bool(f["foreign_operator"])
    if art36:
        why("국내에 주소·영업소가 없는 사업자이므로 기준 해당 시 국내대리인 지정이 필요하다.", ["art36"], ["foreign_operator"])
    deemed = bool(f["other_law_compliance"])
    if deemed:
        why(f"다른 법령({f['other_law_compliance']})에 따른 동등 조치 이행 시 이행 간주가 가능하다.",
            ["deemed"], ["other_law_compliance"])

    articles: list[str] = []
    for r in rationale:
        for a in r["articles"]:
            if a not in articles:
                articles.append(a)

    return {
        "engine_version": ENGINE_VERSION,
        "operator_role": role,
        "operator_role_label": ROLE_LABELS[role],
        "is_generative": generative,
        "art31": {
            "applicable": prior_notice or labeling,
            "prior_notice": prior_notice,
            "output_labeling": labeling,
            "deepfake_notice": deepfake,
            "internal_exemption": internal_exemption,
        },
        "high_impact": {
            "status": status,
            "status_label": STATUS_LABELS[status],
            "stage1_domain": stage1,
            "domain": domain,
            "domain_label": DOMAIN_LABELS[domain],
            "stage2_significant": sig,
            "human_review": hr,
            "issue": issue,
            "issue_note": issue_note,
        },
        "art33_recommended": art33,
        "art32_applicable": art32,
        "art34_applicable": status == "candidate",
        "art35_applicable": status == "candidate",
        "art36_applicable": art36,
        "deemed_compliance_possible": deemed,
        "applicable_articles": articles,
        "rationale": rationale,
        "assumptions": assumptions,
        "facts_used": f,
    }


COMPARE_FIELDS = [
    "operator_role",
    "is_generative",
    "prior_notice",
    "output_labeling",
    "deepfake_notice",
    "internal_exemption",
    "high_impact_status",
    "art33_recommended",
]


def flatten(result: dict[str, Any]) -> dict[str, Any]:
    """골든셋 비교용 평탄화."""
    return {
        "operator_role": result["operator_role"],
        "is_generative": result["is_generative"],
        "prior_notice": result["art31"]["prior_notice"],
        "output_labeling": result["art31"]["output_labeling"],
        "deepfake_notice": result["art31"]["deepfake_notice"],
        "internal_exemption": result["art31"]["internal_exemption"],
        "high_impact_status": result["high_impact"]["status"],
        "art33_recommended": result["art33_recommended"],
    }
