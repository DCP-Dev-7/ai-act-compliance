"""M4 문서 생성기.

- mock 모드: 검증된 템플릿으로 초안을 만든다.
- 실제 LLM 모드: 템플릿 초안과 KB 요약을 주고 LLM이 다듬게 한 뒤, 문단별 조문 참조를 검증한다.
모든 규범적 문단은 KB 조문 참조를 가져야 하며, 없거나 KB에 없는 참조면 '근거 미확인'으로 표시한다.
"""
from __future__ import annotations

import html
import json
from typing import Any

from .extractor import _extract_json

DOC_KIND_LABELS = {
    "notice_texts": "사전 고지 문구 3종",
    "tos_clause": "이용약관 AI 조항 초안",
    "gap_report": "갭 리포트",
    "risk_policy": "위험관리 정책 골격",
    "impact_checklist": "영향평가 체크리스트",
    "monthly_report": "월간 준수 현황 보고 초안",
}
OUTPUT_LABELS = {"text": "글", "image": "이미지", "audio": "음성", "video": "영상"}


def P(text: str, articles: list[str] | None = None, heading: str = "", kind: str = "normative") -> dict[str, Any]:
    return {"heading": heading, "text": text, "articles": articles or [], "kind": kind}


def validate_paragraphs(paragraphs: list[dict[str, Any]], clauses: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for p in paragraphs:
        p = dict(p)
        arts = [a for a in (p.get("articles") or []) if isinstance(a, str)]
        unknown = [a for a in arts if a not in clauses]
        p["articles"] = arts
        if p.get("kind") == "editorial":
            p["supported"] = True
            p["flag"] = ""
        elif not arts:
            p["supported"] = False
            p["flag"] = "근거 미확인 — 조문 참조 없음"
        elif unknown:
            p["supported"] = False
            p["flag"] = "근거 미확인 — KB에 없는 조문 참조: " + ", ".join(unknown)
        else:
            p["supported"] = True
            p["flag"] = ""
        out.append(p)
    return out


def _outputs(system: dict[str, Any]) -> str:
    outs = system["attributes"].get("output_types") or []
    return "·".join(OUTPUT_LABELS.get(o, o) for o in outs) or "결과물"


def notice_texts(customer_name: str, systems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = [s for s in systems if s["result"]["art31"]["prior_notice"]]
    names = ", ".join(s["name"] for s in targets)
    ps = [P(f"대상 기능: {names}. 아래 문구는 초안이며 실제 게시 전 컨설턴트·법무 검토가 필요합니다.", kind="editorial",
            heading="적용 범위")]
    ps.append(P(f"[앱 첫 화면·기능 진입 화면] 이 서비스의 {names} 기능은 생성형 인공지능(AI)을 기반으로 운용됩니다. "
                "AI가 만든 결과물에는 사실과 다르거나 부정확한 내용이 포함될 수 있으니 이용 전에 확인해 주세요.",
                ["art31-1"], heading="문구 1 — 앱 첫 화면 고지"))
    ps.append(P(f"[약관·계약서 삽입용] 회사는 {names} 기능을 생성형 인공지능을 이용하여 제공하며, 이용자는 해당 기능이 "
                "인공지능에 기반하여 운용된다는 사실을 고지받고 이용합니다.", ["art31-1"], heading="문구 2 — 약관 조항용 고지"))
    for s in targets:
        if not s["result"]["art31"]["output_labeling"]:
            continue
        outs = set(s["attributes"].get("output_types") or [])
        if outs & {"image", "audio", "video"}:
            text = (f"[생성물 라벨 — {s['name']}] 'AI 생성 {_outputs(s)}' 문구를 결과물 미리보기와 다운로드 화면에 표시하고, "
                    "파일에는 기계가 읽을 수 있는 메타데이터(예: AIGenerated=true, 생성 일시, 서비스명)를 함께 기록합니다.")
        else:
            text = (f"[생성물 라벨 — {s['name']}] 결과 영역 하단에 '이 글은 AI가 생성했습니다' 문구를 표시하고, "
                    "복사·내보내기 시에도 표시가 유지되도록 합니다.")
        ps.append(P(text, ["art31-2"], heading=f"문구 3 — 생성물 라벨({s['name']})"))
        if s["result"]["art31"]["deepfake_notice"]:
            ps.append(P(f"[명확 고지 — {s['name']}] 이 {_outputs(s)}은(는) 실제가 아닌 인공지능 생성물입니다. "
                        "결과물 재생·열람 시작 시점과 공유 화면에서 이용자가 명확히 인식할 수 있게 표시합니다.",
                        ["art31-3"], heading=f"추가 — 실제와 구분 어려운 결과물({s['name']})"))
    exempt = [s["name"] for s in systems if s["result"]["art31"]["internal_exemption"]]
    if exempt:
        ps.append(P(f"{', '.join(exempt)} 기능은 내부 업무 용도로만 사용되어 고지·표시 문구 적용 대상에서 제외하였습니다. "
                    "외부 제공으로 바뀌면 다시 판정해야 합니다.", ["art31-exception"], heading="예외 기능"))
    return ps


def tos_clause(customer_name: str, systems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = [s for s in systems if s["result"]["art31"]["prior_notice"]]
    names = ", ".join(s["name"] for s in targets)
    ps = [
        P("제○조 (인공지능 기반 기능의 제공)", kind="editorial", heading="조 제목"),
        P(f"① 회사는 다음 기능을 생성형 인공지능을 이용하여 제공합니다: {names}. 회사는 해당 기능이 인공지능에 기반하여 "
          "운용된다는 사실을 서비스 화면과 이 약관을 통해 이용자에게 미리 알립니다.", ["art31-1"]),
        P("② 회사는 인공지능이 생성한 결과물에 그 사실을 이용자가 알 수 있도록 표시하며, 이미지 등 파일 형태의 결과물에는 "
          "기계가 판독할 수 있는 정보를 함께 기록할 수 있습니다.", ["art31-2"]),
        P("③ 이용자는 결과물에 포함된 인공지능 생성 표시를 임의로 삭제하거나 훼손하여 제3자에게 제공하지 않도록 유의합니다.",
          ["art31-2"]),
        P("④ 인공지능이 생성한 결과물은 사실과 다르거나 부정확할 수 있으며, 이용자는 이를 이용하기 전에 내용을 확인할 책임이 있습니다.",
          []),
        P("⑤ 회사는 인공지능 기능의 주요 변경(모델 교체, 적용 범위 확대 등)이 있는 경우 관련 고지 내용을 갱신합니다.", ["art31-1"]),
    ]
    if any(s["result"]["art31"]["deepfake_notice"] for s in systems):
        ps.append(P("⑥ 회사는 실제와 구분하기 어려운 음향·이미지·영상 결과물에 대하여 이용자가 명확하게 인식할 수 있는 방식으로 "
                    "인공지능 생성 사실을 고지 또는 표시합니다.", ["art31-3"]))
    ps.append(P("위 ④항은 이용자 유의사항으로, 인공지능기본법 조문에 직접 근거한 문장이 아닙니다(민사상 책임 배분은 법무 검토 필요).",
                kind="editorial", heading="작성 메모"))
    return ps


def risk_policy(customer_name: str, system: dict[str, Any]) -> list[dict[str, Any]]:
    n = system["name"]
    return [
        P(f"본 문서는 {customer_name}의 '{n}' 시스템(고영향 후보)에 대한 위험관리 정책 골격입니다. 각 항목의 구체 내용은 "
          "컨설턴트와 고객 담당자가 채워야 합니다.", kind="editorial", heading="문서 성격"),
        P("1. 위험관리 방안: 수명주기(기획·개발·운영·폐기) 단계별 위험 식별·평가·완화 절차와 책임자를 정하고, 주요 내용을 공개한다.",
          ["art34"], heading="위험관리 방안의 수립·운영·공개"),
        P("2. 설명 방안: 인공지능이 도출한 최종 결과, 결과 도출에 활용된 주요 기준, 학습용 데이터 개요를 기술적으로 가능한 범위에서 "
          "설명할 수 있는 절차를 둔다.", ["art34"], heading="설명 방안"),
        P("3. 이용자 보호: 이의 제기·정정 요청 창구, 처리 기한, 피해 구제 절차를 정한다.", ["art34"], heading="이용자 보호 방안"),
        P("4. 사람의 관리·감독: 감독 책임자 지정, 결과 재검토 기준, 비상정지(킬스위치) 발동 조건과 절차를 정한다.",
          ["art34"], heading="사람의 관리·감독"),
        P("5. 문서화·보관: 위 조치의 이행 내용을 확인할 수 있는 문서를 작성하고 5년간 보관한다(증적 저장소 연계).",
          ["art34"], heading="문서 작성·보관(5년)"),
        P("6. 고영향 해당 여부 검토 기록과 확인 요청 결과(회신 기한 30일, 연장 시 최대 60일)를 본 정책의 부속 문서로 관리한다.",
          ["art33"], heading="고영향 확인 절차"),
    ]


def impact_checklist(customer_name: str, system: dict[str, Any]) -> list[dict[str, Any]]:
    n = system["name"]
    items = [
        "사용 행태: 누가, 어떤 의사결정에, 어느 정도 빈도로 이 시스템을 사용하는가?",
        "영향받는 사람: 결과의 영향을 받는 집단(취약 계층 포함)은 누구인가?",
        "영향받는 기본권: 평등권·사생활·직업 선택·생명·신체 등 어떤 기본권이 관련되는가?",
        "영향의 정도와 되돌릴 수 있는지 여부: 오류 시 피해 규모와 회복 가능성은?",
        "완화 조치: 사람의 검토, 이의 제기 절차, 모니터링 지표는 무엇인가?",
        "재평가 주기: 모델·데이터·적용 범위 변경 시 재평가 기준은?",
    ]
    ps = [P(f"'{n}' 시스템(고영향 후보)에 대한 영향평가 체크리스트입니다. 영향평가는 노력 의무입니다.",
            ["art35"], heading="개요")]
    ps += [P(f"☐ {t}", ["art35"], heading=f"점검 항목 {i}") for i, t in enumerate(items, 1)]
    return ps


def monthly_report(customer_name: str, month: str, stats: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        P(f"{customer_name} {month} 준수 현황 보고 초안입니다(자동 생성, 컨설턴트 검토 전).", kind="editorial", heading="개요"),
        P(f"증적 보관: 누적 {stats.get('evidence_count', 0)}건, 체인 검증 결과 {stats.get('chain_ok', '미실행')}. "
          "고영향 관련 문서는 5년 보관 대상입니다.", ["art34"], heading="증적"),
        P(f"기술 점검: 최근 점검 통과 {stats.get('tech_passed', 0)}건 / 미흡 {stats.get('tech_failed', 0)}건. "
          "사전 고지 문구와 생성물 표시 상태를 점검했습니다.", ["art31-1", "art31-2"], heading="기술 점검"),
        P(f"미해결 재평가 작업 {stats.get('open_tasks', 0)}건, 미해결 갭 {stats.get('open_gaps', 0)}건.", kind="editorial",
          heading="미결 사항"),
    ]


def render_html(title: str, customer_name: str, kb_version: str, paragraphs: list[dict[str, Any]],
                clauses: dict[str, dict[str, Any]], provider: str) -> str:
    e = html.escape
    body = []
    for p in paragraphs:
        refs = ", ".join(f"{clauses[a]['article']} {clauses[a]['title']}" if a in clauses else a for a in p.get("articles", []))
        flag = f'<span class="flag">⚠ {e(p["flag"])}</span>' if p.get("flag") else ""
        head = f"<h3>{e(p['heading'])}</h3>" if p.get("heading") else ""
        ref = f'<div class="ref">근거(요약): {e(refs)}</div>' if refs else ""
        body.append(f'<section class="{"unsupported" if not p.get("supported", True) else ""}">{head}<p>{e(p["text"])}</p>{ref}{flag}</section>')
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{e(title)}</title>
<style>body{{font-family:sans-serif;margin:2rem;color:#1c2430;max-width:860px}}section{{margin:0 0 14px;padding:8px 12px;border-left:3px solid #9fb3c8}}
section.unsupported{{border-left-color:#c0392b;background:#fdf0ee}}.ref{{font-size:12px;color:#4a5a6a}}.flag{{font-size:12px;color:#c0392b}}
h3{{margin:0 0 4px;font-size:14px}}p{{margin:0 0 4px;line-height:1.6}}.banner{{background:#fff4d6;border:1px solid #e0b84a;padding:8px 12px;font-size:13px}}</style></head><body>
<div class="banner">초안 · 가상 데이터 · 법률 자문 아님 · 법령 내용은 요약 — 원문 확인 필요 (KB {e(kb_version)}, 작성 모드: {e(provider)})</div>
<h1>{e(title)}</h1><p>{e(customer_name)}</p>{''.join(body)}</body></html>"""


# ---------------- 실제 LLM 경로 ----------------

LLM_SYSTEM = """당신은 한국 인공지능기본법 준수 문서 초안 작성 보조자입니다.
주어진 초안 문단을 한국어로 자연스럽고 명확하게 다듬되, 법적 의미를 바꾸거나 새로운 법적 주장을 추가하지 마십시오.
각 문단의 articles에는 제공된 조문 id만 사용하십시오. 근거가 없는 문장을 추가했다면 articles를 빈 배열로 두십시오.
JSON만 출력하십시오: {"paragraphs":[{"heading":"","text":"","articles":["art31-1"],"kind":"normative|editorial"}]}"""


def build_llm_prompt(kind: str, customer_name: str, template: list[dict[str, Any]], clauses: dict[str, dict[str, Any]]) -> str:
    used = sorted({a for p in template for a in p.get("articles", [])})
    kb = [{"id": a, "article": clauses[a]["article"], "title": clauses[a]["title"], "summary": clauses[a]["summary"]}
          for a in used if a in clauses]
    return (f"문서 종류: {DOC_KIND_LABELS.get(kind, kind)}\n고객: {customer_name}\n\n"
            f"사용 가능한 조문 요약(요약 — 원문 확인 필요):\n{json.dumps(kb, ensure_ascii=False)}\n\n"
            f"초안 문단:\n{json.dumps(template, ensure_ascii=False)}\n\n위 초안을 다듬어 같은 JSON 구조로 출력하십시오.")


def parse_llm_paragraphs(text: str) -> list[dict[str, Any]]:
    data = _extract_json(text)
    out = []
    for p in data.get("paragraphs", []):
        t = str(p.get("text", "")).strip()
        if not t:
            continue
        kind = p.get("kind") if p.get("kind") in ("normative", "editorial") else "normative"
        out.append(P(t, [a for a in (p.get("articles") or []) if isinstance(a, str)], str(p.get("heading", "") or ""), kind))
    if not out:
        raise ValueError("LLM 응답에 문단이 없습니다")
    return out
