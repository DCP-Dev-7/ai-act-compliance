#!/usr/bin/env python3
"""브라우저(Playwright/Chromium)로 컨설턴트 화면을 클릭해 A사 흐름을 따라가는 UI 스모크. 새로 시드한 상태에서 실행.
필요: pip install playwright && python -m playwright install chromium. 사용: python3 scripts/ui_click_smoke.py"""
from playwright.sync_api import sync_playwright
B="http://127.0.0.1:3000"
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":1280,"height":900})
    pg.on("dialog", lambda d: d.accept())
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B+"/login"); pg.fill("#email","consultant@demo"); pg.click("button[type=submit]"); pg.wait_for_url(B+"/")
    pg.click("text=A사 (가상)"); pg.wait_for_url("**/customers/1")
    def click(label, wait_text):
        pg.get_by_role("button", name=label, exact=True).first.click()
        pg.wait_for_function("t => document.querySelector('.spread .tag.navy')?.innerText.includes(t)", arg=wait_text, timeout=15000)
        print("OK", label, "→", wait_text)
    pg.get_by_role("button", name="샘플 자료 불러오기(가상)").click(); pg.wait_for_selector("text=접수 자료 (4건)"); print("OK 샘플 자료 4건")
    click("인벤토리 추출","인벤토리 검토"); click("판정 초안 생성","판정 초안")
    pg.click("text=판정 화면으로"); pg.wait_for_selector("text=이 판정 확정")
    for i in range(3):
        pg.get_by_role("button", name="이 판정 확정").first.click(); pg.wait_for_timeout(900)
    pg.wait_for_function("document.querySelector('.spread .tag.navy')?.innerText.includes('판정 확정')"); print("OK 판정 3건 확정")
    pg.click(".tabs >> text=갭 리포트"); click("갭 리포트 생성","갭 리포트"); pg.wait_for_selector("text=GAP-METADATA")
    pg.click(".tabs >> text=문서 초안"); click("문서 초안 생성","문서 초안"); pg.wait_for_selector("text=문구 1 — 앱 첫 화면 고지")
    click("문서 승인","승인 완료")
    pg.click(".tabs >> text=증적함"); click("증적 보관(승인본)","증적 보관")
    pg.get_by_role("button", name="체인 검증").click(); pg.wait_for_selector("text=체인 검증 정상 — 4건"); print("OK 체인 검증 정상 4건")
    pg.click(".tabs >> text=기술 점검"); pg.get_by_role("button", name="지금 점검").click(); pg.wait_for_selector("text=미흡 2"); print("OK 기술 점검 미흡 2")
    pg.click(".tabs >> text=변경·재평가"); pg.get_by_role("button", name="법령 변경 반영(시뮬레이션)").click(); pg.wait_for_selector("text=미해결"); print("OK 재평가 작업", len(pg.query_selector_all("text=미해결")))
    print("pageerrors", errs); b.close()
