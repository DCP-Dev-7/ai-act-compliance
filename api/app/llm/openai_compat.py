from __future__ import annotations

import httpx

from .base import LLMError, LLMResult


class OpenAICompatibleProvider:
    """OpenAI 호환 /chat/completions 엔드포인트(vLLM, llama.cpp server, NPU 게이트웨이 등).

    DCP 내부 GPU/NPU 추론 서버 연결용. base_url 예: http://gpu-node:8000/v1
    주의: 실제 내부 서버 대상 호출은 검증되지 않았다(단위 테스트는 HTTP를 mock).
    """

    name = "openai_compatible"

    def __init__(self, base_url: str, model: str, api_key: str = "", *, external: bool = False,
                 client: httpx.Client | None = None, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.external = external
        self.client = client or httpx.Client(timeout=timeout)

    def complete(self, system: str, prompt: str, max_tokens: int = 2000) -> LLMResult:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        try:
            r = self.client.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as e:
            raise LLMError(f"내부 LLM 호출 실패: {e}") from e
        if r.status_code >= 400:
            raise LLMError(f"내부 LLM 오류 HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError("내부 LLM 응답 형식 오류") from e
        usage = data.get("usage") or {}
        return LLMResult(text=text, input_tokens=int(usage.get("prompt_tokens", 0) or 0),
                         output_tokens=int(usage.get("completion_tokens", 0) or 0),
                         provider=self.name, model=data.get("model") or self.model)
