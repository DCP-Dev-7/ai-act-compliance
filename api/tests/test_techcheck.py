import httpx
import pytest

from app.techcheck import TargetNotAllowed, ai_metadata, ensure_allowed, find_notice, run_check

from .conftest import DEMO_DIR, demo_transport

CFG = {"notice_pages": ["/", "/generate.html"], "image_pages": ["/generate.html"], "generated_image_prefix": "/generated/"}


def test_demo_service_has_exactly_two_gaps():
    client = httpx.Client(transport=demo_transport())
    results = run_check("http://demo.test", CFG, ("http://demo.test",), client=client)
    failed = [r for r in results if not r["passed"]]
    passed = [r for r in results if r["passed"]]
    assert len(results) == 4 and len(failed) == 2 and len(passed) == 2
    assert {(r["check"], r["target"]) for r in failed} == {
        ("prior_notice", "http://demo.test/"),
        ("image_metadata", "http://demo.test/generated/sample-noncompliant.png")}
    assert all(r["article"] in ("art31-1", "art31-2") for r in results)
    assert not any("logo.png" in r["target"] for r in results)  # UI 이미지는 점검 대상 아님


def test_allowlist_enforced():
    with pytest.raises(TargetNotAllowed):
        run_check("http://evil.example", CFG, ("http://demo.test",))
    with pytest.raises(TargetNotAllowed):
        ensure_allowed("http://demo.test:8080/x", ("http://demo.test",))  # 포트가 다르면 다른 대상
    with pytest.raises(TargetNotAllowed):
        ensure_allowed("file:///etc/passwd", ("http://demo.test",))
    ensure_allowed("http://DEMO.test/a", ("http://demo.test/",))


def test_images_on_other_origins_are_not_fetched():
    hits = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        if request.url.host == "demo.test":
            return httpx.Response(200, text='<img src="http://169.254.169.254/generated/x.png"><img src="/generated/a.png">')
        return httpx.Response(200, content=b"secret")

    results = run_check("http://demo.test", {"notice_pages": [], "image_pages": ["/"], "generated_image_prefix": "/generated/"},
                        ("http://demo.test",), client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert not any("169.254" in h for h in hits)
    assert any("169.254" in r["target"] and not r["passed"] and "허용 목록" in r["detail"] for r in results)


def test_metadata_detection():
    assert ai_metadata((DEMO_DIR / "generated/sample-compliant.png").read_bytes())["found"]
    assert not ai_metadata((DEMO_DIR / "generated/sample-noncompliant.png").read_bytes())["found"]
    assert ai_metadata(b"\xff\xd8...<xmp>trainedAlgorithmicMedia</xmp>")["found"]


def test_notice_detection_ignores_scripts_and_comments():
    assert find_notice("<p>이 서비스는 생성형 AI를 활용합니다.</p>")
    assert find_notice("<script>var s='AI 기반 생성';</script><!-- 인공지능 기반 --><p>환영합니다</p>") is None
    assert find_notice((DEMO_DIR / "index.html").read_text()) is None
    assert find_notice((DEMO_DIR / "generate.html").read_text())
