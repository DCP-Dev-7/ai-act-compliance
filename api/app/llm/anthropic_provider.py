from __future__ import annotations

from typing import Any

from .base import LLMError, LLMResult


class AnthropicProvider:
    """공식 `anthropic` SDK(Messages API)를 쓰는 외부 공급자.

    주의: 이 데모 환경에는 API 키가 없어 실호출은 검증되지 않았다(단위 테스트는 SDK 클라이언트를 mock).
    """

    name = "anthropic"
    external = True

    def __init__(self, api_key: str, model: str, client: Any | None = None, timeout: float = 120.0):
        self.model = model
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self.client = client

    def complete(self, system: str, prompt: str, max_tokens: int = 2000) -> LLMResult:
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:  # SDK 예외(APIError 등)를 도메인 예외로 감싼다
            raise LLMError(f"Anthropic 호출 실패: {type(e).__name__}: {e}") from e
        if getattr(resp, "stop_reason", None) == "refusal":
            raise LLMError("Anthropic 모델이 요청을 거절했습니다(stop_reason=refusal)")
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        usage = resp.usage
        return LLMResult(
            text=text,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            provider=self.name,
            model=getattr(resp, "model", None) or self.model,
        )
