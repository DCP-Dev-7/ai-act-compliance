from app.golden import load_cases, run_golden


def test_golden_set_shape():
    cases = load_cases()
    assert len(cases) >= 20
    assert all(c["synthetic"] is True for c in cases)
    assert len({c["id"] for c in cases}) == len(cases)


def test_golden_engine_and_pipeline_rate_at_least_90_percent():
    r = run_golden(threshold=0.9)
    print(f"golden: pipeline {r['matched']}/{r['total']}={r['rate']:.3f}, engine {r['engine_matched']}/{r['total']}")
    assert r["engine_rate"] >= 0.9, r["mismatches"]
    assert r["rate"] >= 0.9, r["mismatches"]
    assert r["passed"]


def test_golden_fails_below_threshold():
    # 추출기가 아무것도 못 찾는 경우(빈 사실) → 일치율이 임계 미만 → 실패로 판정되어야 한다
    r = run_golden(lambda name, text: {}, threshold=0.9)
    assert r["rate"] < 0.9 and not r["passed"]
