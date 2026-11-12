#!/usr/bin/env python3
"""A사(가상) 전체 흐름 E2E 스모크 테스트 — 실행 중인 API(와 웹)에 HTTP 로 붙어 역할별로 흐름을 따라간다.

사용: python3 scripts/e2e_smoke.py [--api http://127.0.0.1:8000] [--web http://127.0.0.1:3000]
실패하면 0 이 아닌 코드로 끝난다. 새로 시드한 DB(자료 미접수 상태)에서 실행하는 것을 전제로 한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from app.seed import SAMPLE_DOCS, SEED_DIR  # noqa: E402  (가상 샘플 자료)

STEP = 0


def step(msg: str) -> None:
    global STEP
    STEP += 1
    print(f"[{STEP:02d}] {msg}")


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"  ✗ 실패: {msg}")
        sys.exit(1)
    print(f"  ✓ {msg}")


class Role:
    def __init__(self, api: str, email: str):
        self.c = httpx.Client(base_url=api, timeout=60.0)
        r = self.c.post("/auth/login", json={"email": email, "password": "demo1234"})
        if r.status_code != 200:
            print(f"로그인 실패 {email}: {r.status_code} {r.text}")
            sys.exit(1)
        self.c.cookies.clear()
        self.c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        self.user = r.json()["user"]

    def call(self, method: str, path: str, expect: int = 200, **kw):
        r = self.c.request(method, path, **kw)
        if r.status_code != expect:
            print(f"  ✗ {method} {path} → {r.status_code} (기대 {expect}): {r.text[:400]}")
            sys.exit(1)
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--web", default="")
    args = ap.parse_args()

    step("상태 확인(/health, /meta)")
    anon = httpx.Client(base_url=args.api, timeout=30.0)
    check(anon.get("/health").json()["status"] == "ok", "/health ok")
    meta = anon.get("/meta").json()
    check(meta["banner"] == "가상 데이터 · 법률 자문 아님", "배너 문구")
    print(f"  · LLM 모드: {meta['llm']['configured']} ({meta['llm']['model']}), KB {meta['kb_version']}")
    check(anon.get("/customers").status_code == 401, "비로그인 접근은 401")

    step("역할별 로그인")
    cust, cons, ops = Role(args.api, "a-company@demo"), Role(args.api, "consultant@demo"), Role(args.api, "ops@demo")
    check([cust.user["role"], cons.user["role"], ops.user["role"]] == ["customer", "consultant", "ops"], "세 역할 로그인")
    customers = cons.call("GET", "/customers")
    a = next(c for c in customers if c["name"] == "A사 (가상)")
    cid = a["id"]
    check(a["state"] == "intake" and a["is_synthetic"], "A사 (가상) 초기 상태 intake")

    step("고객 담당자: 자료 4건 업로드")
    for d in SAMPLE_DOCS:
        body = {"kind": d["kind"], "title": d["title"], "data": d["data"],
                "content": (SEED_DIR / d["file"]).read_text(encoding="utf-8")}
        cust.call("POST", f"/customers/{cid}/documents", 201, json=body)
    check(len(cust.call("GET", f"/customers/{cid}/documents")) == 4, "자료 4건 접수")
    cust.call("POST", f"/customers/{cid}/inventory/extract", 403)
    print("  ✓ 고객 담당자는 인벤토리 추출 불가(403)")

    step("컨설턴트: AI 인벤토리 추출")
    inv = cons.call("POST", f"/customers/{cid}/inventory/extract")
    names = [s["name"] for s in inv["systems"]]
    check(names == ["상품 이미지 생성", "상품 설명 문구 생성", "고객문의 요약"], f"시스템 3개 추출: {names}")
    docs = {d["id"]: d["content"] for d in cons.call("GET", f"/customers/{cid}/documents")}
    cited = [f for s in inv["systems"] for f in s["facts"] if f["source"] == "extracted"]
    check(len(cited) >= 15 and all(docs[f["doc_id"]][f["span_start"]:f["span_end"]] == f["quote"] for f in cited),
          f"추출 사실 {len(cited)}건 모두 문서 인용 구간과 일치")

    step("컨설턴트: 판정 초안 → 확정")
    drafts = cons.call("POST", f"/customers/{cid}/classify")
    by = {d["system_name"]: d for d in drafts}
    img, txt, summ = by["상품 이미지 생성"]["result"], by["상품 설명 문구 생성"]["result"], by["고객문의 요약"]["result"]
    check(img["operator_role"] == "deployer" and img["art31"]["prior_notice"] and img["art31"]["output_labeling"],
          "상품 이미지 생성: 이용사업자, 제31조 사전고지·생성물표시")
    check(txt["art31"]["prior_notice"] and txt["art31"]["output_labeling"], "상품 설명 문구 생성: 제31조 적용")
    check(summ["art31"]["internal_exemption"] and not summ["art31"]["applicable"], "고객문의 요약: 내부 업무용 예외")
    check(all(d["result"]["high_impact"]["status"] == "not_applicable" for d in drafts), "고영향 해당 없음")
    check(all(r["articles"] for d in drafts for r in d["result"]["rationale"]), "모든 근거 문장에 조문 연결")
    cons.call("POST", f"/customers/{cid}/gap-report", 409)
    print("  ✓ 확정 전 갭 리포트는 거절(409)")
    cust.call("POST", f"/classifications/{drafts[0]['id']}/confirm", 403)
    ops.call("POST", f"/classifications/{drafts[0]['id']}/confirm", 403)
    print("  ✓ 고객·운영자는 확정 불가(403)")
    for d in drafts:
        cons.call("POST", f"/classifications/{d['id']}/confirm")
    check(cons.call("GET", f"/customers/{cid}")["state"] == "classification_confirmed", "상태 classification_confirmed")

    step("컨설턴트: 갭 리포트")
    gap = cons.call("POST", f"/customers/{cid}/gap-report")
    codes = [f["code"] for f in gap["findings"]]
    check(codes == ["GAP-NOTICE", "GAP-METADATA", "GAP-TOS"], f"갭 3건: {codes}")
    check(all(f["owner"] and f["due_date"] and f["articles"] and f["severity"] for f in gap["findings"]), "심각도·담당·기한·조문 포함")

    step("컨설턴트: 문서 초안 → 승인")
    gen = cons.call("POST", f"/customers/{cid}/generated-documents/generate")
    check({d["kind"] for d in gen} == {"notice_texts", "tos_clause", "gap_report"}, "문서 3종 생성(고영향 문서 없음)")
    full = cust.call("GET", f"/customers/{cid}/generated-documents")["items"]
    notice = next(d for d in full if d["kind"] == "notice_texts")
    heads = [p["heading"] for p in notice["paragraphs"]]
    check(sum(h.startswith("문구 ") for h in heads) >= 3, f"사전 고지 문구 3종 이상: {heads}")
    check(all(p["articles"] for d in full for p in d["paragraphs"] if p["kind"] == "normative" and p["supported"]),
          "지원되는 규범 문단은 모두 조문 참조 보유")
    print(f"  · 근거 미확인 표시 문단: {sum(d['unsupported'] for d in full)}건")
    cust.call("POST", f"/customers/{cid}/approve", 403)
    print("  ✓ 고객 담당자는 승인 불가(403)")
    approved = cons.call("POST", f"/customers/{cid}/approve")
    check(all(d["status"] == "approved" for d in approved), "문서 승인")

    step("컨설턴트: 증적 보관 → 체인 검증")
    ev = cons.call("POST", f"/customers/{cid}/evidence/store-package")
    check(len(ev) == 4 and cons.call("GET", f"/customers/{cid}")["state"] == "evidence_stored", "증적 4건 보관, 상태 evidence_stored")
    check(all(ev[i]["prev_hash"] == ev[i - 1]["chain_hash"] for i in range(1, len(ev))), "해시 체인 연결")
    check(int(ev[0]["retention_until"][:4]) - int(ev[0]["created_at"][:4]) == 5, "보관 기한 5년")
    v = cust.call("POST", f"/customers/{cid}/evidence/verify")
    check(v["ok"] and v["count"] == 4, "체인 검증 OK")

    step("운영자: 기술 점검(demo-service)")
    tc = ops.call("POST", f"/customers/{cid}/tech-check")
    failed = [(r["check"], r["target"]) for r in tc["results"] if not r["passed"]]
    check(tc["failed"] == 2 and tc["passed"] == 2, f"통과 2 / 미흡 2: {failed}")
    check(sorted(c for c, _ in failed) == ["image_metadata", "prior_notice"], "미흡: 고지 없는 페이지 1, 메타데이터 없는 이미지 1")
    check(any(t.endswith("sample-noncompliant.png") for _, t in failed), "메타데이터 없는 이미지 식별")
    check(tc["evidence_id"] is not None, "점검 결과 증적 보관")

    step("운영자: AI 게이트웨이 로그 적재(M9)")
    lines = "\n".join(json.dumps({"ts": f"2026-11-12T00:00:0{i}Z", "model": "가상모델-알파", "tokens": 100 + i}, ensure_ascii=False) for i in range(3))
    g = ops.call("POST", f"/customers/{cid}/gateway-logs", 201, content=lines.encode("utf-8"))
    check(g["records"] == 3, "로그 3건 증적 보관")
    check(ops.call("POST", f"/customers/{cid}/evidence/verify")["count"] == 6, "증적 6건으로 증가, 체인 정상")

    step("컨설턴트: 법령 변경 반영(시뮬레이션) → 재평가 작업")
    ch = cons.call("POST", "/changes/law/simulate")
    tasks = {t["system_name"]: t for t in ch["tasks"]}
    check("상품 이미지 생성" in tasks and "guide-img-edit" in tasks["상품 이미지 생성"]["clause_ids"],
          f"재평가 작업 생성: {sorted(tasks)}")
    check("고객문의 요약" not in tasks, "예외 시스템은 재평가 대상 아님")
    check(anon.get("/meta").json()["kb_version"] == "2026.11-v2-sim", "활성 KB v2(시뮬레이션)")
    cons.call("POST", "/changes/law/simulate", 409)

    step("고객 릴리스 웹훅 → 재평가 작업")
    wh = anon.post("/webhooks/release", headers={"X-Webhook-Token": "demo-webhook-token"},
                   json={"customer_id": cid, "version": "v2.0.0", "system_name": "상품 설명 문구 생성", "notes": "LLM 공급자 교체(가상)"})
    check(wh.status_code == 201 and len(wh.json()["tasks"]) == 1, "웹훅으로 재평가 작업 1건")
    check(len(cust.call("GET", f"/changes?customer_id={cid}")["tasks"]) == len(tasks) + 1, "고객 화면에 작업 표시")

    step("운영자: 자동화 작업 실행·운영 콘솔")
    gr = ops.call("POST", "/ops/jobs/golden_regression/run")
    check(gr["status"] == "ok" and gr["detail"]["rate"] >= 0.9, f"골든셋 일치율 {gr['detail']['matched']}/{gr['detail']['total']} = {gr['detail']['rate']*100:.1f}%")
    check(ops.call("POST", "/ops/jobs/evidence_verify/run")["status"] == "ok", "증적 체인 검증 작업")
    tj = ops.call("POST", "/ops/jobs/tech_check/run")
    check(tj["status"] == "ok" and tj["detail"]["results"][0]["failed"] == 2, "주간 기술 점검 작업")
    check(ops.call("POST", "/ops/jobs/monthly_report/run")["status"] == "ok", "월간 보고서 초안 작업")
    cons.call("POST", "/ops/jobs/golden_regression/run", 403)
    s = ops.call("GET", "/ops/summary")
    check(len(s["job_runs"]) >= 4 and s["golden_runs"][0]["passed"], "운영 콘솔: 작업 실행 기록·골든셋 결과")
    check(any(u["task"] == "inventory_extract" for u in s["usage"]) and s["budgets"][0]["status"] == "정상", "토큰 사용량·예산 상태")
    check(all(j["next_run"] for j in s["jobs"]), "스케줄러 다음 실행 시각 등록")
    m = anon.get("/metrics").text
    check("aiact_golden_match_rate" in m and "aiact_evidence_items_total" in m, "/metrics Prometheus 텍스트")
    actions = {x["action"] for x in ops.call("GET", f"/audit?customer_id={cid}&limit=500")}
    need = {"document.upload", "inventory.extract", "classification.confirm", "gap_report.create", "documents.approve",
            "evidence.store_package", "tech_check.run", "gateway_logs.ingest", "release.webhook"}
    check(need <= actions, "감사 로그에 주요 작업 기록")

    if args.web:
        step("웹 포털(Next.js) 확인")
        w = httpx.Client(base_url=args.web, timeout=60.0)
        r = w.get("/login")
        check(r.status_code == 200 and "AI 기본법 준수 플랫폼" in r.text and 'lang="ko"' in r.text, "/login 200 + 한국어")
        r = w.post("/api/auth/login", json={"email": "consultant@demo", "password": "demo1234"})
        check(r.status_code == 200 and "aiact_session" in w.cookies, "웹 프록시 로그인(httpOnly 쿠키)")
        check(w.get("/api/customers").json()[0]["name"] == "A사 (가상)", "웹 프록시 경유 API 호출(쿠키 세션)")
        for p in ["/", f"/customers/{cid}", f"/customers/{cid}/classification", f"/customers/{cid}/evidence", "/ops", "/kb"]:
            check(w.get(p).status_code == 200, f"페이지 {p} 200")

    print("\nE2E 스모크 테스트 통과")


if __name__ == "__main__":
    main()
