"""M2 AI 인벤토리 추출.

- mock 모드: 키워드/규칙 휴리스틱(문장 단위, 간단한 부정 처리). 모든 사실에 인용(문서 id + 인용 구간)을 붙인다.
- 실제 LLM 모드: LLM이 JSON으로 사실+인용문을 내고, 인용문이 실제 문서에 존재하는지 검증한다
  (존재하지 않으면 supported=false 로 표시).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .engine import DOMAIN_LABELS, FACT_DEFAULTS


@dataclass
class Doc:
    id: int | None
    title: str
    content: str


@dataclass
class Sentence:
    doc_id: int | None
    text: str
    start: int
    end: int
    heading: str


_HEADING = re.compile(r"^\s*(?:#{1,6}\s+|\d+[.)]\s+|[■▶◆●]\s*|\[[^\]]+\]\s*$)")
_SPLIT = re.compile(r"(?<=[.?!。])\s+")


def split_sentences(doc: Doc) -> list[Sentence]:
    out: list[Sentence] = []
    pos = 0
    heading = ""
    for line in doc.content.split("\n"):
        line_start = pos
        pos += len(line) + 1
        if not line.strip():
            continue
        if _HEADING.match(line) and len(line.strip()) <= 60:
            heading = line.strip()
        off = 0
        for part in _SPLIT.split(line):
            idx = line.find(part, off)
            off = idx + len(part)
            if part.strip():
                lead = len(part) - len(part.lstrip())
                out.append(Sentence(doc.id, part.strip(), line_start + idx + lead,
                                    line_start + idx + lead + len(part.strip()), heading))
    return out


_NEG = re.compile(r"않|없(?!이)|아니|아닌|아닙|제외|미사용|금지|못")
_CLAUSE_END = re.compile(r"[,;]|며 |하고 |이고 |지만|으나|하되")


def find(pattern: str, text: str) -> re.Match[str] | None:
    """부정되지 않은 첫 매치를 돌려준다(매치 뒤 같은 절 안에 부정어가 있으면 건너뜀)."""
    for m in re.finditer(pattern, text):
        tail = _CLAUSE_END.split(text[m.end(): m.end() + 24])[0]
        if _NEG.search(tail):
            continue
        return m
    return None


DOMAIN_PATTERNS: list[tuple[str, str]] = [
    ("medical", r"의료|환자|질병|판독|의료기기|진료"),
    ("nuclear", r"원자력|원전"),
    ("essential_infra", r"전력|에너지 ?공급|먹는 ?물|상수도|정수장|가스 ?공급"),
    ("biometric_investigation", r"범죄 ?수사|수사기관|생체 ?인식"),
    ("hiring", r"채용|지원자|서류 ?전형|면접 ?평가"),
    ("lending", r"대출|여신|신용 ?평가"),
    ("transport", r"자율주행|레벨 ?4|철도 ?운행|항공기 ?운항"),
    ("public_service", r"공공서비스|행정기관|복지 ?급여|수급 ?자격"),
    ("education_eval", r"학생 ?평가|성적|채점|학업 ?성취|입학 ?사정"),
]

P_SELF = r"자체 ?(?:개발|학습|구축)|직접 (?:개발|학습)|독자 ?개발|자사 ?모델"
P_EXTERNAL = r"외부[^.]{0,12}(?:API|모델|LLM)|API(?:를|로)? ?(?:연동|호출|이용|사용)|타사 ?모델|상용 ?(?:LLM|모델)"
P_GENERATIVE = r"생성형|생성|합성|요약|초안|챗봇|대화형|LLM|번역"
P_INTERNAL = r"내부 ?업무|사내|임직원|직원만|직원이 사용|상담 ?직원|내부 ?(?:전용|도구)|외부에 제공하지 않"
P_B2B = r"B2B|기업 ?고객|고객사|기관에 (?:납품|공급|제공)|병원에 (?:납품|공급|제공)|은행에 (?:납품|공급|제공)|솔루션으로 (?:판매|공급|제공)"
P_B2C = r"B2C|소비자|일반 ?이용자|개인 ?고객|이용자에게|누구나|앱 ?이용자|판매자에게|시민|민원인|구직자에게|승객"
P_REALISTIC = r"실제와 ?구분(?:하기)? ?어려운|실제 (?:사람|인물)(?:처럼|과 같은|과 구분)|실존 ?인물|딥페이크|실사 ?(?:인물|영상)|실제 ?목소리"
P_SIG_TRUE = (r"자동(?:으로)? ?(?:결정|탈락|거절|승인|확정|판정|제어|반영)|합격 ?여부|당락|승인 ?여부를 (?:결정|확정)|"
              r"중대한 영향|생명|신체|기본권|직접 ?제어|주요 ?운영|운행을 (?:제어|수행)|진단 ?결과를 (?:제시|산출)|판독 ?결과|신원을 ?특정")
P_SIG_FALSE = r"참고용|단순 ?(?:안내|정보 ?제공)|일반(?:적인)? ?(?:정보|안내)|영향(?:이|을) (?:없|미치지 않)|일정 ?조율|문구 ?작성 ?보조|통계 ?리포트"
P_HR_FORMAL = r"형식적|일괄 ?승인|클릭만|사후 ?(?:확인|통보)만|검토 ?없이 ?승인|관행적으로 승인"
P_HR_SUBST = (r"최종 ?(?:결정|판단|승인|확정)(?:은|을|권은)? ?(?:반드시 )?(?:사람|담당자|인사 ?담당자|의사|전문의|심사역|교사|운전원)|"
              r"(?:사람|담당자|인사 ?담당자|의사|전문의|심사역|교사|운전원)(?:이|가) (?:직접 |모두 |전부 |개별 )?(?:검토|확인|판단|결정)|"
              r"실질적(?:으로|인) ?(?:검토|통제)")
P_HR_NONE = r"사람의? ?(?:개입|검토|확인) ?없이|완전 ?자동|전자동|자동으로 ?(?:결정|탈락|거절|확정|판정)"
P_DEPLOYED_NO = r"출시 ?전|개발 ?중|PoC|시범 ?단계|미출시"
OUTPUT_PATTERNS = [("image", r"이미지|사진|그림"), ("audio", r"음성|목소리|오디오"), ("video", r"영상|동영상|비디오"),
                   ("text", r"문구|텍스트|문장|요약|답변|번역|보고서|초안|코드")]
P_PROVIDER_NAME = r"((?:[A-Za-z가-힣0-9]+ )?(?:LLM|모델|API)[^.,\n]{0,20}?(?:\([^)]{1,30}\)))"
P_FLOPS = r"10\^(\d{2})\s*FLOPs?"


def _cite(field: str, value: Any, s: Sentence | None, m: re.Match[str] | None = None) -> dict[str, Any]:
    if s is None:
        return {"field": field, "value": value, "doc_id": None, "quote": "", "span_start": None,
                "span_end": None, "source": "default", "supported": True}
    return {"field": field, "value": value, "doc_id": s.doc_id, "quote": s.text, "span_start": s.start,
            "span_end": s.end, "source": "extracted", "supported": True}


def _first(pattern: str, sents: list[Sentence]) -> tuple[Sentence, re.Match[str]] | None:
    for s in sents:
        m = find(pattern, s.text)
        if m:
            return s, m
    return None


def extract_facts_from_sentences(name: str, sents: list[Sentence], fallback: list[Sentence] | None = None) -> list[dict[str, Any]]:
    """한 시스템에 해당하는 문장들에서 사실을 뽑는다(규칙 기반)."""
    fallback = fallback or []
    facts: list[dict[str, Any]] = []

    # 목적: 시스템명을 처음 언급하는 문장
    purpose = next((s for s in sents if name in s.text and len(s.text) > len(name) + 6
                    and not _FEATURE_LINE.search(s.text)), None) or (sents[0] if sents else None)
    facts.append(_cite("purpose", purpose.text if purpose else "", purpose))

    # 모델 조달 방식 (시스템별 문장 우선, 없으면 문서 전체에서 보완)
    hit_self, hit_ext = _first(P_SELF, sents), _first(P_EXTERNAL, sents)
    if not hit_self and not hit_ext:
        hit_self, hit_ext = _first(P_SELF, fallback), _first(P_EXTERNAL, fallback)
        if hit_ext:
            hit_self = None  # 전사 설명에서는 외부 API 사용 진술을 우선
    if hit_self:
        facts.append(_cite("provider_type", "self_developed", hit_self[0]))
    elif hit_ext:
        facts.append(_cite("provider_type", "external_api", hit_ext[0]))
    else:
        facts.append(_cite("provider_type", "unknown", None))

    hit = _first(P_PROVIDER_NAME, sents)
    facts.append(_cite("model_provider", hit[1].group(1).strip() if hit else "", hit[0] if hit else None))

    # 생성형 여부·산출물 유형
    gen = _first(P_GENERATIVE, sents)
    facts.append(_cite("is_generative", bool(gen), gen[0] if gen else None))
    outs: list[str] = []
    out_sent: Sentence | None = None
    if gen:
        # 시스템 이름에 산출물 유형이 드러나면 그것을 우선한다(여러 기능이 한 문장에 섞인 경우 대비)
        for key, pat in OUTPUT_PATTERNS:
            if re.search(pat, name):
                outs.append(key)
                out_sent = purpose
        if not outs:
            gen_sents = [s for s in sents if find(P_GENERATIVE, s.text)]
            for key, pat in OUTPUT_PATTERNS:
                h = _first(pat, gen_sents)
                if h:
                    outs.append(key)
                    out_sent = out_sent or h[0]
    facts.append(_cite("output_types", outs, out_sent))

    # 이용자 유형
    h_int, h_b2b, h_b2c = _first(P_INTERNAL, sents), _first(P_B2B, sents), _first(P_B2C, sents)
    if h_int:
        facts.append(_cite("user_type", "internal", h_int[0]))
    elif h_b2c:
        facts.append(_cite("user_type", "B2C", h_b2c[0]))
    elif h_b2b:
        facts.append(_cite("user_type", "B2B", h_b2b[0]))
    else:
        facts.append(_cite("user_type", "unknown", None))

    h = _first(P_REALISTIC, sents)
    facts.append(_cite("realistic_synthetic", bool(h), h[0] if h else None))

    # 고영향 영역
    best: tuple[int, str, Sentence] | None = None
    for i, s in enumerate(sents):
        for key, pat in DOMAIN_PATTERNS:
            if find(pat, s.text):
                if best is None or i < best[0]:
                    best = (i, key, s)
                break
        if best:
            break
    domain = best[1] if best else "none"
    facts.append(_cite("domain", domain, best[2] if best else None))

    if domain != "none":
        h_false, h_true = _first(P_SIG_FALSE, sents), _first(P_SIG_TRUE, sents)
        if h_false:
            facts.append(_cite("significant_impact", False, h_false[0]))
        elif h_true:
            facts.append(_cite("significant_impact", True, h_true[0]))
        else:
            facts.append(_cite("significant_impact", None, None))
        h_formal, h_sub, h_none = _first(P_HR_FORMAL, sents), _first(P_HR_SUBST, sents), _first(P_HR_NONE, sents)
        if h_formal:
            facts.append(_cite("human_review", "formal", h_formal[0]))
        elif h_sub:
            facts.append(_cite("human_review", "substantive", h_sub[0]))
        elif h_none:
            facts.append(_cite("human_review", "none", h_none[0]))
        else:
            facts.append(_cite("human_review", "unknown", None))
    else:
        facts.append(_cite("significant_impact", None, None))
        facts.append(_cite("human_review", "unknown", None))

    user_type = next(f["value"] for f in facts if f["field"] == "user_type")
    h = _first(P_DEPLOYED_NO, sents)
    if user_type == "internal":
        facts.append(_cite("deployed_to_users", False, h_int[0] if h_int else None))
    else:
        facts.append(_cite("deployed_to_users", not bool(h), h[0] if h else None))

    h = _first(P_FLOPS, sents)
    if h:
        facts.append(_cite("cumulative_flops", float(10 ** int(h[1].group(1))), h[0]))
    h = _first(r"디지털의료제품법", sents)
    if h:
        facts.append(_cite("other_law_compliance", "디지털의료제품법", h[0]))
    h = _first(r"국내에 (?:주소|영업소|법인)(?:가|이|나 영업소가)? 없", sents) or _first(r"해외 ?(?:사업자|법인)", sents)
    if h:
        facts.append(_cite("foreign_operator", True, h[0]))
    return facts


_FEATURE_LINE = re.compile(r"AI\s*(?:활용|적용|사용)\s*기능[^:：\n]{0,20}[:：]\s*(.+)")
_FEATURE_HEADING = re.compile(r"(?:기능\s*[:：]\s*)?(.{2,30}?(?:생성|요약|추천|심사|진단|평가|챗봇|합성|번역|분석|탐지|예측))\s*$")


def discover_system_names(docs: list[Doc]) -> list[tuple[str, Sentence | None]]:
    names: list[tuple[str, Sentence | None]] = []
    seen: set[str] = set()
    for d in docs:
        for s in split_sentences(d):
            m = _FEATURE_LINE.search(s.text)
            if m:
                for raw in re.split(r"[,、/]|\s+및\s+", m.group(1)):
                    n = re.sub(r"^\s*(?:\(?\d+\)?[.)]?|[①-⑳])\s*", "", raw).strip(" .·")
                    n = re.sub(r"\s*\(.*?\)\s*$", "", n)
                    if 2 <= len(n) <= 30 and n not in seen:
                        seen.add(n)
                        names.append((n, s))
    if names:
        return names
    for d in docs:
        for s in split_sentences(d):
            if s.heading and s.heading == s.text:
                h = _HEADING.sub("", s.text).strip(" []")
                m = _FEATURE_HEADING.search(h)
                if m and m.group(1).strip() not in seen:
                    seen.add(m.group(1).strip())
                    names.append((m.group(1).strip(), s))
    return names


def sentences_for(name: str, all_sents: list[Sentence]) -> list[Sentence]:
    compact = name.replace(" ", "")
    out = []
    for s in all_sents:
        # 'AI 활용 기능: A, B' 목록 줄은 모든 기능 이름을 담고 있어 다른 기능의 단어(예: '사내')가 섞이므로 제외
        if _FEATURE_LINE.search(s.text):
            continue
        if name in s.text or compact in s.text.replace(" ", "") or (s.heading and compact in s.heading.replace(" ", "")):
            out.append(s)
    return out


def facts_to_attributes(facts: list[dict[str, Any]]) -> dict[str, Any]:
    attrs = dict(FACT_DEFAULTS)
    for f in facts:
        if f["field"] in attrs:
            attrs[f["field"]] = f["value"]
    return attrs


def extract_mock(docs: list[Doc]) -> list[dict[str, Any]]:
    """문서 묶음에서 AI 시스템 목록과 사실을 뽑는다(규칙 기반)."""
    all_sents = [s for d in docs for s in split_sentences(d)]
    systems = []
    for name, name_sent in discover_system_names(docs):
        sents = sentences_for(name, all_sents)
        facts = extract_facts_from_sentences(name, sents, fallback=all_sents)
        facts.insert(0, _cite("name", name, name_sent))
        systems.append({"name": name, "facts": facts, "attributes": facts_to_attributes(facts)})
    return systems


def extract_single_mock(name: str, text: str) -> dict[str, Any]:
    """설명문 1건 = 시스템 1개(골든셋용)."""
    doc = Doc(None, name, text)
    sents = split_sentences(doc)
    facts = extract_facts_from_sentences(name, sents)
    return {"name": name, "facts": facts, "attributes": facts_to_attributes(facts)}


# ---------------- 실제 LLM 경로 ----------------

LLM_SYSTEM = """당신은 한국 인공지능기본법 준수 진단을 돕는 사실 추출기입니다.
고객이 제출한 문서에서 AI 시스템(기능)별 사실만 추출합니다. 법적 판단은 하지 마십시오.
반드시 JSON만 출력합니다. 모든 사실에는 문서에서 그대로 복사한 인용문(quote)을 붙이십시오.
문서에 근거가 없으면 해당 필드를 생략하십시오. 추측하지 마십시오."""

LLM_SCHEMA_HINT = {
    "systems": [{
        "name": "시스템(기능) 이름",
        "facts": [{"field": "purpose|provider_type|model_provider|is_generative|user_type|output_types|"
                            "realistic_synthetic|domain|significant_impact|human_review|deployed_to_users|"
                            "cumulative_flops|foreign_operator|other_law_compliance",
                   "value": "값", "doc_id": 0, "quote": "문서 원문 그대로의 인용"}],
    }]
}
ALLOWED_VALUES: dict[str, Any] = {
    "provider_type": {"external_api", "self_developed", "unknown"},
    "user_type": {"B2C", "B2B", "internal", "unknown"},
    "domain": set(DOMAIN_LABELS),
    "human_review": {"substantive", "formal", "none", "unknown"},
}


def build_llm_prompt(docs: list[Doc], single_name: str | None = None) -> str:
    parts = [
        "다음 문서에서 AI 시스템별 사실을 추출해 아래 JSON 형식으로만 답하십시오.",
        "형식: " + json.dumps(LLM_SCHEMA_HINT, ensure_ascii=False),
        "값 규칙: provider_type ∈ {external_api,self_developed,unknown}; user_type ∈ {B2C,B2B,internal,unknown}; "
        "output_types ⊂ [text,image,audio,video]; domain ∈ {" + ",".join(DOMAIN_LABELS) + "}; "
        "human_review ∈ {substantive,formal,none,unknown}; is_generative/realistic_synthetic/deployed_to_users/"
        "foreign_operator 는 true/false; significant_impact 는 true/false/null.",
    ]
    if single_name:
        parts.append(f"이 문서는 시스템 1개('{single_name}')만 설명합니다. systems 배열에 1개만 넣으십시오.")
    for d in docs:
        parts.append(f"<document doc_id=\"{d.id if d.id is not None else 0}\" title=\"{d.title}\">\n{d.content}\n</document>")
    return "\n\n".join(parts)


def _extract_json(text: str) -> Any:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e < 0:
        raise ValueError("LLM 응답에서 JSON을 찾지 못했습니다")
    return json.loads(text[s: e + 1])


def parse_llm_extraction(text: str, docs: list[Doc]) -> list[dict[str, Any]]:
    """LLM JSON을 검증한다. 인용문이 문서에 없으면 supported=False."""
    data = _extract_json(text)
    by_id = {(d.id if d.id is not None else 0): d for d in docs}
    systems = []
    for s in data.get("systems", []):
        name = str(s.get("name", "")).strip()
        if not name:
            continue
        facts: list[dict[str, Any]] = []
        for f in s.get("facts", []):
            field = f.get("field")
            if field not in FACT_DEFAULTS:
                continue
            value = f.get("value")
            if field in ALLOWED_VALUES and value not in ALLOWED_VALUES[field]:
                continue
            if field == "output_types":
                value = [v for v in (value if isinstance(value, list) else [value]) if v in ("text", "image", "audio", "video")]
            quote = str(f.get("quote", "") or "").strip()
            doc = by_id.get(f.get("doc_id"))
            start = end = None
            supported = False
            doc_id = None
            candidates = [doc] if doc else []
            candidates += [d for d in docs if d is not doc]
            if quote:
                for d in candidates:
                    idx = d.content.find(quote)
                    if idx >= 0:
                        start, end, supported, doc_id = idx, idx + len(quote), True, d.id
                        break
            facts.append({"field": field, "value": value, "doc_id": doc_id, "quote": quote, "span_start": start,
                          "span_end": end, "source": "extracted", "supported": supported})
        have = {f["field"] for f in facts}
        for field in ("provider_type", "is_generative", "user_type", "output_types", "domain"):
            if field not in have:
                facts.append(_cite(field, FACT_DEFAULTS[field], None))
        # 근거 없는(supported=False) 사실은 판정에 쓰지 않는다 → 기본값 유지
        attrs = facts_to_attributes([f for f in facts if f["supported"]])
        systems.append({"name": name, "facts": facts, "attributes": attrs})
    return systems
