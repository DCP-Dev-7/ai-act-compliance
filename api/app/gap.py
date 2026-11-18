"""갭 리포트: 판정된 의무 vs 현재 이행 상태(설문) 비교."""
from __future__ import annotations

import html
from datetime import date, timedelta
from typing import Any

STATE_LABELS = {
    "has_prior_notice": "AI 사용 사실 사전 고지(앱·UI)",
    "labels_outputs_visible": "생성물 가시 표시",
    "embeds_metadata": "생성물 메타데이터·워터마크",
    "tos_has_ai_clause": "이용약관 AI 조항",
    "risk_policy": "위험관리 방안",
    "explanation_method": "설명 방안",
    "human_oversight_killswitch": "사람의 관리·감독(비상정지)",
    "doc_retention_5y": "문서 5년 보관 체계",
}
SEVERITY_LABELS = {"high": "높음", "medium": "중간", "low": "낮음"}


def build_findings(systems: list[dict[str, Any]], state: dict[str, Any], today: date | None = None) -> list[dict[str, Any]]:
    """systems: [{id, name, attributes, result}] (확정된 판정). state: 고객 현재 상태."""
    today = today or date.today()
    findings: list[dict[str, Any]] = []

    def add(code: str, title: str, detail: str, severity: str, owner: str, days: int, articles: list[str],
            affected: list[dict[str, Any]], state_key: str, recommendation: str) -> None:
        findings.append({
            "code": code, "title": title, "detail": detail, "severity": severity,
            "severity_label": SEVERITY_LABELS[severity], "owner": owner,
            "due_date": (today + timedelta(days=days)).isoformat(), "articles": articles,
            "systems": [{"id": s.get("id"), "name": s["name"]} for s in affected],
            "state_key": state_key, "recommendation": recommendation, "status": "open",
        })

    notice = [s for s in systems if s["result"]["art31"]["prior_notice"]]
    label = [s for s in systems if s["result"]["art31"]["output_labeling"]]
    media = [s for s in label if set(s["attributes"].get("output_types") or []) & {"image", "audio", "video"}]
    deep = [s for s in systems if s["result"]["art31"]["deepfake_notice"]]
    high = [s for s in systems if s["result"]["high_impact"]["status"] == "candidate"]
    review = [s for s in systems if s["result"]["art33_recommended"]]

    if notice and not state.get("has_prior_notice"):
        add("GAP-NOTICE", "AI 사용 사실 사전 고지 없음",
            "앱 첫 화면·가입 절차 등 이용자 접점에 인공지능 기반 서비스라는 사전 고지가 없습니다.",
            "high", "서비스 기획", 30, ["art31-1", "art43"], notice, "has_prior_notice",
            "앱 첫 화면 또는 기능 진입 화면에 고지 문구를 게시하고 약관에도 반영하십시오.")
    if label and not state.get("labels_outputs_visible"):
        add("GAP-LABEL", "생성물 가시 표시 없음", "생성 결과물에 AI 생성 사실이 표시되지 않습니다.",
            "high", "서비스 기획", 30, ["art31-2"], label, "labels_outputs_visible",
            "결과 화면과 내보내기 결과물에 'AI 생성' 표시를 추가하십시오.")
    if media and not state.get("embeds_metadata"):
        add("GAP-METADATA", "생성 이미지 등에 메타데이터·워터마크 없음",
            "생성된 이미지·음성·영상 파일에 기계 판독 가능한 AI 생성 표시(메타데이터·워터마크)가 없습니다.",
            "high", "개발", 45, ["art31-2"], media, "embeds_metadata",
            "생성 파이프라인에서 파일 메타데이터(예: AIGenerated 필드)를 삽입하고 편집·내보내기 시 보존되는지 점검하십시오.")
    if deep and not state.get("deepfake_clear_notice"):
        add("GAP-DEEPFAKE", "실제와 구분 어려운 결과물의 명확한 고지 미흡",
            "딥페이크성 결과물에 대해 이용자가 명확히 인식할 수 있는 고지·표시가 확인되지 않습니다.",
            "high", "서비스 기획", 30, ["art31-3"], deep, "deepfake_clear_notice",
            "결과물 자체에 식별 가능한 표시를 넣고 공유·다운로드 시 고지를 유지하십시오.")
    if notice and not state.get("tos_has_ai_clause"):
        add("GAP-TOS", "이용약관에 AI 조항 없음",
            "이용약관에 인공지능 기반 기능 제공, 생성물 표시, 이용자 유의사항에 관한 조항이 없습니다.",
            "medium", "법무·경영지원", 60, ["art31-1"], notice, "tos_has_ai_clause",
            "약관 AI 조항 초안을 검토·개정하고 개정 고지 절차를 진행하십시오.")
    if high:
        for key, code, title, owner in [
            ("risk_policy", "GAP-RISK", "위험관리 방안 미수립", "정보보호·리스크"),
            ("explanation_method", "GAP-EXPLAIN", "설명 방안 미수립", "개발"),
            ("human_oversight_killswitch", "GAP-OVERSIGHT", "사람의 관리·감독(비상정지) 체계 없음", "운영"),
            ("doc_retention_5y", "GAP-RETENTION", "문서 5년 보관 체계 없음", "정보보호·리스크"),
        ]:
            if not state.get(key):
                add(code, title, f"고영향 후보 시스템에 요구되는 '{STATE_LABELS[key]}'이(가) 확인되지 않습니다.",
                    "high", owner, 60, ["art34"], high, key, "위험관리 정책 골격을 바탕으로 체계를 수립·운영하십시오.")
        if not state.get("impact_assessment"):
            add("GAP-IMPACT", "영향평가 미실시(노력 의무)", "고영향 후보 시스템에 대한 기본권 영향평가가 없습니다.",
                "medium", "정보보호·리스크", 90, ["art35"], high, "impact_assessment",
                "영향평가 체크리스트로 사용 행태와 영향받는 기본권을 식별하십시오.")
    if review:
        add("GAP-CONFIRM", "고영향 해당 여부 확인 요청 검토 필요",
            "고영향 해당 여부가 불명확하거나 쟁점이 있는 시스템이 있습니다.",
            "medium", "법무·경영지원", 30, ["art33"], review, "art33_requested",
            "과기정통부 확인 요청 여부를 결정하고 근거 자료를 준비하십시오.")
    return findings


def no_gap_note(systems: list[dict[str, Any]]) -> str:
    """발견 사항이 0건일 때 '왜 0건인지'를 설명하는 문장. 오류가 아니라 의미 있는 결과임을 알려 준다."""
    if not systems:
        return ""
    internal = [s for s in systems if s["result"]["art31"]["internal_exemption"]]
    no_duty = all(not s["result"]["art31"]["applicable"] and s["result"]["high_impact"]["status"] == "not_applicable"
                  and not s["result"]["art33_recommended"] for s in systems)
    if no_duty and len(internal) == len(systems):
        return ("의무 거의 없음 — 모든 AI 시스템이 내부 업무용이고 이용자에게 제공되지 않아 제31조 고지·표시 의무의 예외이며, "
                "고영향 영역에도 해당하지 않습니다. 남은 일은 (1) 내부 업무용이라는 사실과 이 판정을 기록으로 보관하고 "
                "(2) 나중에 고객에게 AI 기능을 제공하게 되면 다시 판정하는 것입니다.")
    if no_duty:
        return ("의무 거의 없음 — 판정 결과 제31조 고지·표시 의무와 고영향 책무가 적용되는 시스템이 없습니다. "
                "서비스가 바뀌면 다시 판정하십시오.")
    return "갭 없음 — 판정된 의무는 설문상 모두 이행 중입니다. 실제 이행 여부는 증빙(화면 캡처, 약관, 문서)으로 확인하십시오."


def render_html(customer_name: str, kb_version: str, systems: list[dict[str, Any]], findings: list[dict[str, Any]],
                clauses: dict[str, dict[str, Any]], generated_on: str) -> str:
    e = html.escape

    def refs(ids: list[str]) -> str:
        return ", ".join(f"{e(clauses[a]['article'])} {e(clauses[a]['title'])}" if a in clauses else e(a) for a in ids)

    rows = "".join(
        f"<tr><td>{e(f['code'])}</td><td><b>{e(f['title'])}</b><br>{e(f['detail'])}<br><i>권고: {e(f['recommendation'])}</i></td>"
        f"<td>{e(f['severity_label'])}</td><td>{e(f['owner'])}</td><td>{e(f['due_date'])}</td>"
        f"<td>{e(', '.join(s['name'] for s in f['systems']))}</td><td>{refs(f['articles'])}</td></tr>"
        for f in findings)
    sys_rows = "".join(
        f"<tr><td>{e(s['name'])}</td><td>{e(s['result']['operator_role_label'])}</td>"
        f"<td>{'예' if s['result']['is_generative'] else '아니오'}</td>"
        f"<td>{'예외(내부 업무용)' if s['result']['art31']['internal_exemption'] else ('적용' if s['result']['art31']['applicable'] else '해당 없음')}</td>"
        f"<td>{e(s['result']['high_impact']['status_label'])}</td></tr>" for s in systems)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>갭 리포트 — {e(customer_name)}</title>
<style>body{{font-family:sans-serif;margin:2rem;color:#1c2430}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}
td,th{{border:1px solid #c9d1dc;padding:6px 8px;font-size:13px;vertical-align:top;text-align:left}}th{{background:#eef2f7}}
.banner{{background:#fff4d6;border:1px solid #e0b84a;padding:8px 12px;font-size:13px}}</style></head><body>
<div class="banner">가상 데이터 · 법률 자문 아님 · 법령 내용은 요약 — 원문 확인 필요 (KB {e(kb_version)})</div>
<h1>AI 기본법 갭 리포트 — {e(customer_name)}</h1><p>작성일 {e(generated_on)} · 발견 사항 {len(findings)}건</p>
<h2>1. 대상 시스템과 판정 요약</h2>
<table><tr><th>시스템</th><th>사업자 지위</th><th>생성형</th><th>제31조</th><th>고영향</th></tr>{sys_rows}</table>
<h2>2. 발견 사항</h2>
{'' if findings else f'<p class="banner" style="background:#e2f1ed;border-color:#a9d3ca">{e(no_gap_note(systems))}</p>'}
<table><tr><th>코드</th><th>내용</th><th>심각도</th><th>담당</th><th>기한</th><th>대상 시스템</th><th>근거 조문(요약)</th></tr>{rows or '<tr><td colspan="7">발견 사항 없음</td></tr>'}</table>
</body></html>"""
