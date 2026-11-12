#!/usr/bin/env python3
"""demo-service 용 가상 이미지 생성(표준 라이브러리만 사용).

- generated/sample-compliant.png   : tEXt 청크 AIGenerated=true 포함(준수 예)
- generated/sample-noncompliant.png: 메타데이터 없음(미준수 예)
- img/logo.png                     : UI 로고(생성물 아님 — 점검 제외 대상)
"""
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "demo-service"


def chunk(ctype: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + ctype + body + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF)


def png(width: int, height: int, color_a, color_b, text: dict[str, str] | None = None) -> bytes:
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            t = (x + y) / (width + height)
            in_box = width * 0.3 < x < width * 0.7 and height * 0.35 < y < height * 0.8
            for a, b in zip(color_a, color_b):
                v = int(a + (b - a) * t)
                rows.append(min(255, v + 60) if in_box else v)
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    for k, v in (text or {}).items():
        out += chunk(b"tEXt", k.encode("latin-1") + b"\x00" + v.encode("latin-1"))
    return out + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b"")


if __name__ == "__main__":
    (ROOT / "generated").mkdir(parents=True, exist_ok=True)
    (ROOT / "img").mkdir(parents=True, exist_ok=True)
    (ROOT / "generated" / "sample-compliant.png").write_bytes(
        png(240, 180, (40, 90, 140), (200, 220, 240),
            {"AIGenerated": "true", "Software": "demo-generator (synthetic)", "Comment": "synthetic demo image"}))
    (ROOT / "generated" / "sample-noncompliant.png").write_bytes(png(240, 180, (140, 80, 40), (240, 220, 190)))
    (ROOT / "img" / "logo.png").write_bytes(png(64, 64, (30, 60, 90), (90, 150, 190)))
    print("demo-service 이미지 3개 생성 완료")
