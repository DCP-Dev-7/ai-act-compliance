from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMError(RuntimeError):
    """LLM 호출 실패."""


class PolicyViolation(RuntimeError):
    """고객 데이터 정책(allow_external=false)에 위배되는 외부 호출 시도."""


class BudgetExceeded(RuntimeError):
    """고객 월 예산 초과."""


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    provider: str
    model: str


class LLMProvider(Protocol):
    name: str
    model: str
    external: bool  # True = 고객 데이터가 DCP 밖(외부 API)으로 나감

    def complete(self, system: str, prompt: str, max_tokens: int = 2000) -> LLMResult: ...


def estimate_tokens(text: str) -> int:
    """mock 모드용 대략적 토큰 추정(한글 기준 글자 수/2)."""
    return max(1, len(text) // 2)
