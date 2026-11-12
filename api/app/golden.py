"""골든셋 회귀: 합성 사례(설명문)를 추출→판정 파이프라인에 넣어 기대값과의 일치율을 계산한다.

- engine_rate : 정답 사실(facts)을 직접 넣었을 때 결정 트리의 일치율(규칙 자체의 회귀)
- rate        : 설명문 → (mock 휴리스틱 또는 LLM) 추출 → 결정 트리의 일치율(모델·프롬프트 구성의 회귀)
"""
from __future__ import annotations

import json
import sys
from typing import Any, Callable

from .config import DATA_DIR, get_settings
from .engine import COMPARE_FIELDS, classify, flatten
from .extractor import extract_single_mock

GOLDEN_PATH = DATA_DIR / "golden_cases.json"


def load_cases() -> list[dict[str, Any]]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))["cases"]


def _compare(expected: dict[str, Any], got: dict[str, Any]) -> dict[str, Any]:
    return {k: {"expected": expected[k], "got": got.get(k)} for k in COMPARE_FIELDS if expected[k] != got.get(k)}


def run_golden(extract_fn: Callable[[str, str], dict[str, Any]] | None = None,
               threshold: float | None = None) -> dict[str, Any]:
    """extract_fn(name, description) -> attributes dict. 기본은 mock 휴리스틱."""
    extract_fn = extract_fn or (lambda name, text: extract_single_mock(name, text)["attributes"])
    threshold = get_settings().golden_threshold if threshold is None else threshold
    cases = load_cases()
    matched = engine_matched = 0
    mismatches: list[dict[str, Any]] = []
    for c in cases:
        if not _compare(c["expected"], flatten(classify(c["facts"]))):
            engine_matched += 1
        else:
            mismatches.append({"id": c["id"], "title": c["title"], "stage": "engine",
                               "diff": _compare(c["expected"], flatten(classify(c["facts"])))})
        try:
            attrs = extract_fn(c["name"], c["description"])
            diff = _compare(c["expected"], flatten(classify(attrs)))
        except Exception as e:  # 추출 실패도 불일치로 집계
            diff = {"error": {"expected": "추출 성공", "got": f"{type(e).__name__}: {e}"}}
        if not diff:
            matched += 1
        else:
            mismatches.append({"id": c["id"], "title": c["title"], "stage": "pipeline", "diff": diff})
    total = len(cases)
    rate = matched / total if total else 0.0
    return {
        "total": total,
        "matched": matched,
        "rate": round(rate, 4),
        "engine_matched": engine_matched,
        "engine_rate": round(engine_matched / total, 4) if total else 0.0,
        "threshold": threshold,
        "passed": rate >= threshold and (engine_matched / total if total else 0) >= threshold,
        "mismatches": mismatches,
    }


def main() -> int:
    r = run_golden()
    print(f"골든셋(합성 {r['total']}건) 파이프라인 일치율: {r['matched']}/{r['total']} = {r['rate']*100:.1f}% "
          f"| 규칙 엔진 일치율: {r['engine_matched']}/{r['total']} = {r['engine_rate']*100:.1f}% "
          f"| 임계 {r['threshold']*100:.0f}% → {'통과' if r['passed'] else '실패(승격 차단)'}")
    for m in r["mismatches"]:
        print(f"  불일치 [{m['stage']}] {m['id']} {m['title']}: {json.dumps(m['diff'], ensure_ascii=False)}")
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
