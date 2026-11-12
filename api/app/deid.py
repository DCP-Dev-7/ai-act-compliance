"""비식별화: 외부 LLM 호출 전에 한국 개인정보 패턴을 가역 토큰으로 치환한다.

매핑(token -> 원문)은 서버 메모리에만 두고 외부로 보내지 않는다.
정규식 기반이므로 이름·주소 등 비정형 PII는 잡지 못한다(알려진 한계).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 순서가 중요하다: 더 구체적인 패턴을 먼저 적용한다.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("주민등록번호", re.compile(r"(?<!\d)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?:\s?-\s?)?[1-8]\d{6}(?!\d)")),
    ("카드번호", re.compile(r"(?<!\d)\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}(?!\d)")),
    ("카드번호", re.compile(r"(?<![\d-])(?:4\d{15}|5[1-5]\d{14}|9\d{15})(?![\d-])")),
    ("이메일", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")),
    ("사업자등록번호", re.compile(r"(?<![\d-])\d{3}-\d{2}-\d{5}(?![\d-])")),
    ("휴대전화", re.compile(r"(?<![\d-])01[016789][- .]?\d{3,4}[- .]?\d{4}(?![\d-])")),
    ("전화번호", re.compile(r"(?<![\d-])0(?:2|[3-6][1-5]|70|50\d?)[- .]\d{3,4}[- .]\d{4}(?![\d-])")),
    # 계좌번호: '계좌/은행/입금/예금' 문맥 뒤의 숫자열, 또는 하이픈으로 묶인 10~14자리
    ("계좌번호", re.compile(r"(?<=계좌)[^\d\n]{0,12}(\d[\d-]{8,18}\d)")),
    ("계좌번호", re.compile(r"(?:은행|입금|예금주|예금)[^\d\n]{0,12}(\d[\d-]{8,18}\d)")),
    ("계좌번호", re.compile(r"(?<![\d-])(\d{2,6}-\d{2,6}-\d{2,8}(?:-\d{1,3})?)(?![\d-])")),
]


@dataclass
class DeidResult:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)


class Deidentifier:
    def deidentify(self, text: str, mapping: dict[str, str] | None = None) -> DeidResult:
        mapping = dict(mapping or {})
        reverse = {v: k for k, v in mapping.items()}
        counts: dict[str, int] = {}

        for label, pat in _PATTERNS:
            def repl(m: re.Match[str], label: str = label) -> str:
                if m.lastindex:
                    raw = m.group(1)
                    s, e = m.span(1)
                else:
                    raw = m.group(0)
                    s, e = m.span(0)
                if label == "계좌번호":
                    digits = re.sub(r"\D", "", raw)
                    if not (10 <= len(digits) <= 16):
                        return m.group(0)
                token = reverse.get(raw)
                if token is None:
                    n = sum(1 for t in mapping if t.startswith(f"[{label}_")) + 1
                    token = f"[{label}_{n}]"
                    mapping[token] = raw
                    reverse[raw] = token
                counts[label] = counts.get(label, 0) + 1
                ms = m.start(0)
                return m.group(0)[: s - ms] + token + m.group(0)[e - ms:]

            text = pat.sub(repl, text)
        return DeidResult(text=text, mapping=mapping, counts=counts)

    @staticmethod
    def restore(text: str, mapping: dict[str, str]) -> str:
        for token, raw in mapping.items():
            text = text.replace(token, raw)
        return text
