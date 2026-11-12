"""M5 기술 점검기: 허용 목록(allowlist)에 있는 대상만 점검한다.

점검 항목
 1) 지정 페이지에 AI 사전 고지 문구가 보이는가 (제31조 사전 고지)
 2) 생성 이미지에 AI 생성 메타데이터가 있는가 (제31조 생성물 표시 — 기계 판독)
"""
from __future__ import annotations

import re
import struct
import zlib
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

NOTICE_RE = re.compile(
    r"(?:AI|인공지능)[^.。\n]{0,40}(?:생성|기반|활용|사용|이용|운용)|생성형 ?(?:AI|인공지능)|(?:생성|작성)[^.。\n]{0,20}(?:AI|인공지능)[^.。\n]{0,10}(?:입니다|됩니다|했습니다)")
AI_KEYS = {"aigenerated", "ai_generated", "ai-generated", "aigc"}
AI_MARKERS = (b"trainedAlgorithmicMedia", b"AIGenerated", b"ai_generated")


class TargetNotAllowed(RuntimeError):
    pass


def origin(url: str) -> str:
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise TargetNotAllowed(f"잘못된 대상 URL: {url}")
    port = p.port or (443 if p.scheme == "https" else 80)
    return f"{p.scheme}://{p.hostname.lower()}:{port}"


def ensure_allowed(url: str, allowlist: tuple[str, ...] | list[str]) -> None:
    allowed = {origin(a) for a in allowlist}
    if origin(url) not in allowed:
        raise TargetNotAllowed(f"허용 목록에 없는 대상입니다: {url} (허용: {', '.join(sorted(allowed)) or '없음'})")


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.imgs: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript", "template"):
            self._skip += 1
        if tag == "img":
            src = dict(attrs).get("src")
            if src:
                self.imgs.append(src)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "template") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def visible_text_and_images(html_text: str) -> tuple[str, list[str]]:
    p = _Text()
    p.feed(html_text)
    return "\n".join(p.parts), p.imgs


def find_notice(html_text: str) -> str | None:
    text, _ = visible_text_and_images(html_text)
    m = NOTICE_RE.search(text)
    if not m:
        return None
    line = next((ln for ln in text.split("\n") if m.group(0) in ln), m.group(0))
    return line[:200]


def png_text_chunks(data: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return out
    pos = 8
    while pos + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8: pos + 8 + length]
        pos += 12 + length
        try:
            if ctype == b"tEXt":
                k, _, v = body.partition(b"\x00")
                out[k.decode("latin-1")] = v.decode("latin-1")
            elif ctype == b"zTXt":
                k, _, rest = body.partition(b"\x00")
                out[k.decode("latin-1")] = zlib.decompress(rest[1:]).decode("latin-1")
            elif ctype == b"iTXt":
                k, _, rest = body.partition(b"\x00")
                comp_flag = rest[0]
                rest = rest[2:]
                _lang, _, rest = rest.partition(b"\x00")
                _trans, _, text = rest.partition(b"\x00")
                if comp_flag:
                    text = zlib.decompress(text)
                out[k.decode("latin-1")] = text.decode("utf-8", "replace")
        except Exception:
            continue
        if ctype == b"IEND":
            break
    return out


def ai_metadata(data: bytes) -> dict[str, Any]:
    """이미지 바이트에서 AI 생성 표시 메타데이터를 찾는다."""
    chunks = png_text_chunks(data)
    for k, v in chunks.items():
        if k.lower() in AI_KEYS and v.strip().lower() not in ("", "false", "0", "no"):
            return {"found": True, "where": f"PNG 텍스트 청크 {k}={v[:60]}"}
        if any(m.decode() in v for m in AI_MARKERS):
            return {"found": True, "where": f"PNG 텍스트 청크 {k} (XMP/설명 내 AI 생성 표시)"}
    if not chunks:
        for m in AI_MARKERS:
            if m in data:
                return {"found": True, "where": f"파일 내 메타데이터 문자열 {m.decode()}"}
    return {"found": False, "where": ""}


def run_check(base_url: str, config: dict[str, Any], allowlist: tuple[str, ...] | list[str],
              client: httpx.Client | None = None) -> list[dict[str, Any]]:
    ensure_allowed(base_url, allowlist)
    own = client is None
    client = client or httpx.Client(timeout=10.0, follow_redirects=False)
    results: list[dict[str, Any]] = []
    try:
        def get(url: str) -> httpx.Response:
            ensure_allowed(url, allowlist)  # 페이지가 가리키는 외부 주소는 따라가지 않는다
            return client.get(url)

        for path in config.get("notice_pages", ["/"]):
            url = urljoin(base_url + "/", path.lstrip("/"))
            try:
                r = get(url)
                if r.status_code != 200:
                    results.append({"check": "prior_notice", "target": url, "passed": False, "article": "art31-1",
                                    "detail": f"페이지를 가져오지 못했습니다(HTTP {r.status_code})"})
                    continue
                hit = find_notice(r.text)
                results.append({"check": "prior_notice", "target": url, "passed": bool(hit), "article": "art31-1",
                                "detail": f"고지 문구 확인: “{hit}”" if hit else "AI 사용 사실 사전 고지 문구를 찾지 못했습니다"})
            except (httpx.HTTPError, TargetNotAllowed) as e:
                results.append({"check": "prior_notice", "target": url, "passed": False, "article": "art31-1",
                                "detail": f"점검 실패: {e}"})

        prefix = config.get("generated_image_prefix", "/")
        seen: set[str] = set()
        for path in config.get("image_pages", []):
            page = urljoin(base_url + "/", path.lstrip("/"))
            try:
                r = get(page)
                _, imgs = visible_text_and_images(r.text if r.status_code == 200 else "")
            except (httpx.HTTPError, TargetNotAllowed) as e:
                results.append({"check": "image_metadata", "target": page, "passed": False, "article": "art31-2",
                                "detail": f"점검 실패: {e}"})
                continue
            for src in imgs:
                url = urljoin(page, src)
                if url in seen or not urlsplit(url).path.startswith(prefix):
                    continue
                seen.add(url)
                try:
                    ir = get(url)
                    if ir.status_code != 200:
                        results.append({"check": "image_metadata", "target": url, "passed": False, "article": "art31-2",
                                        "detail": f"이미지를 가져오지 못했습니다(HTTP {ir.status_code})"})
                        continue
                    md = ai_metadata(ir.content)
                    results.append({"check": "image_metadata", "target": url, "passed": md["found"], "article": "art31-2",
                                    "detail": f"AI 생성 메타데이터 확인: {md['where']}" if md["found"]
                                    else "이미지 파일에 AI 생성 메타데이터가 없습니다"})
                except (httpx.HTTPError, TargetNotAllowed) as e:
                    results.append({"check": "image_metadata", "target": url, "passed": False, "article": "art31-2",
                                    "detail": f"점검 실패: {e}"})
    finally:
        if own:
            client.close()
    return results
