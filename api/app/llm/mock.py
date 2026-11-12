from __future__ import annotations

from .base import LLMResult, estimate_tokens


class MockProvider:
    """결정적 mock. 실제 추론은 각 작업의 규칙/템플릿 구현이 담당하고,
    이 공급자는 '외부 호출 없음'을 보장하는 자리 표시자 + 토큰 추정만 한다."""

    name = "mock"
    model = "mock-rules-1"
    external = False

    def complete(self, system: str, prompt: str, max_tokens: int = 2000) -> LLMResult:
        text = "{}"
        return LLMResult(text=text, input_tokens=estimate_tokens(system + prompt),
                         output_tokens=estimate_tokens(text), provider=self.name, model=self.model)
