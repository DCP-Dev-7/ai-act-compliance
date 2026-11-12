import json
from types import SimpleNamespace

import httpx
import pytest

from app.config import get_settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import BudgetExceeded, LLMError, LLMResult, PolicyViolation
from app.llm.openai_compat import OpenAICompatibleProvider
from app.llm.router import ModelRouter
from app.models import Customer, LLMUsage


class FakeExternal:
    name = "anthropic"
    model = "claude-fable-5-2"
    external = True

    def __init__(self):
        self.calls = []

    def complete(self, system, prompt, max_tokens=2000):
        self.calls.append((system, prompt))
        return LLMResult(text="담당자 [휴대전화_1] 확인", input_tokens=1_000_000, output_tokens=100_000,
                         provider=self.name, model=self.model)


class FakeInternal:
    name = "openai_compatible"
    model = "internal"
    external = False

    def complete(self, system, prompt, max_tokens=2000):
        return LLMResult("ok", 10, 5, self.name, self.model)


def settings(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return get_settings()


def customer(db) -> Customer:
    return db.query(Customer).first()


def test_default_is_mock_without_key(db, monkeypatch):
    r = ModelRouter(settings(monkeypatch))
    sel = r.select(db, customer(db), "t")
    assert sel.provider.name == "mock" and sel.reason == "configured" and not sel.provider.external


def test_external_used_when_allowed_and_cost_accounted(db, monkeypatch):
    fake = FakeExternal()
    r = ModelRouter(settings(monkeypatch, LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="k"), {"anthropic": fake})
    c = customer(db)
    res, info = r.complete(db, c, "inventory_extract", "sys", "연락처 010-1234-5678 로 문의")
    # 비식별화: 외부로 나간 프롬프트에는 원문 번호가 없어야 하고, 응답에서는 복원되어야 한다
    assert "010-1234-5678" not in fake.calls[0][1] and "[휴대전화_1]" in fake.calls[0][1]
    assert info["deidentified"] and info["pii_counts"] == {"휴대전화": 1}
    assert res.text == "담당자 010-1234-5678 확인"
    u = db.query(LLMUsage).filter_by(provider="anthropic").one()
    assert u.customer_id == c.id and u.task == "inventory_extract"
    assert u.cost_usd == pytest.approx(8.0 + 4.0)  # 1M in × $8 + 0.1M out × $40


def test_policy_blocks_external_and_falls_back(db, monkeypatch):
    fake = FakeExternal()
    r = ModelRouter(settings(monkeypatch, LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="k"), {"anthropic": fake})
    c = customer(db)
    c.allow_external = False
    sel = r.select(db, c, "t")
    assert sel.provider.name == "mock" and sel.reason == "data_policy"
    with pytest.raises(PolicyViolation):
        r.select(db, c, "t", require_external=True)
    r.complete(db, c, "t", "s", "p")
    assert fake.calls == []  # 외부 호출이 한 번도 일어나지 않아야 한다


def test_policy_prefers_internal_endpoint(db, monkeypatch):
    r = ModelRouter(settings(monkeypatch, LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="k"),
                    {"anthropic": FakeExternal(), "openai_compatible": FakeInternal()})
    c = customer(db)
    c.allow_external = False
    assert r.select(db, c, "t").provider.name == "openai_compatible"


def test_complete_refuses_external_selection_for_restricted_customer(db, monkeypatch):
    from app.llm.router import Selection

    fake = FakeExternal()
    r = ModelRouter(settings(monkeypatch, LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="k"), {"anthropic": fake})
    c = customer(db)
    c.allow_external = False
    with pytest.raises(PolicyViolation):
        r.complete(db, c, "t", "s", "p", sel=Selection(fake, "configured", "anthropic"))
    assert fake.calls == []


def test_budget_guardrail(db, monkeypatch):
    fake = FakeExternal()
    r = ModelRouter(settings(monkeypatch, LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="k"), {"anthropic": fake})
    c = customer(db)
    c.monthly_budget_usd = 10.0
    r.complete(db, c, "t", "s", "p")  # $12 사용 → 예산 초과
    sel = r.select(db, c, "t")
    assert sel.provider.name == "mock" and sel.reason == "budget_exceeded"
    strict = ModelRouter(settings(monkeypatch, BUDGET_FALLBACK_TO_MOCK="0"), {"anthropic": fake})
    with pytest.raises(BudgetExceeded):
        strict.select(db, c, "t")


def test_anthropic_provider_with_mocked_sdk():
    captured = {}

    class Messages:
        def create(self, **kw):
            captured.update(kw)
            return SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking="..."),
                                            SimpleNamespace(type="text", text="안녕"),
                                            SimpleNamespace(type="text", text="하세요")],
                                   usage=SimpleNamespace(input_tokens=12, output_tokens=7),
                                   stop_reason="end_turn", model="claude-fable-5-2")

    p = AnthropicProvider("key", "claude-fable-5-2", client=SimpleNamespace(messages=Messages()))
    res = p.complete("시스템", "질문", max_tokens=321)
    assert res.text == "안녕하세요" and (res.input_tokens, res.output_tokens) == (12, 7)
    assert captured == {"model": "claude-fable-5-2", "max_tokens": 321, "system": "시스템",
                        "messages": [{"role": "user", "content": "질문"}]}
    assert p.external is True


def test_anthropic_provider_errors_and_refusal():
    class Boom:
        def create(self, **kw):
            raise RuntimeError("rate limited")

    with pytest.raises(LLMError):
        AnthropicProvider("k", "m", client=SimpleNamespace(messages=Boom())).complete("s", "p")

    class Refuse:
        def create(self, **kw):
            return SimpleNamespace(content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=0),
                                   stop_reason="refusal", model="m")

    with pytest.raises(LLMError):
        AnthropicProvider("k", "m", client=SimpleNamespace(messages=Refuse())).complete("s", "p")


def test_anthropic_provider_builds_real_sdk_client():
    import anthropic

    p = AnthropicProvider("sk-test-not-real", "claude-fable-5-2")
    assert isinstance(p.client, anthropic.Anthropic) and hasattr(p.client.messages, "create")


def test_default_model_id(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    assert get_settings().anthropic_model == "claude-fable-5-2"
    monkeypatch.setenv("ANTHROPIC_MODEL", "other-model")
    assert get_settings().anthropic_model == "other-model"


def test_openai_compatible_provider_with_mocked_http():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"model": "local-llm", "choices": [{"message": {"content": "내부 응답"}}],
                                         "usage": {"prompt_tokens": 20, "completion_tokens": 4}})

    p = OpenAICompatibleProvider("http://gpu-node:8000/v1/", "local-llm", "tok",
                                 client=httpx.Client(transport=httpx.MockTransport(handler)))
    res = p.complete("sys", "user", max_tokens=50)
    assert seen["url"] == "http://gpu-node:8000/v1/chat/completions" and seen["auth"] == "Bearer tok"
    assert seen["body"]["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "user"}]
    assert seen["body"]["model"] == "local-llm" and seen["body"]["max_tokens"] == 50
    assert res.text == "내부 응답" and (res.input_tokens, res.output_tokens) == (20, 4)
    assert p.external is False


def test_openai_compatible_error():
    p = OpenAICompatibleProvider("http://x/v1", "m", client=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(500, text="oops"))))
    with pytest.raises(LLMError):
        p.complete("s", "p")


def test_router_builds_internal_provider_from_env(db, monkeypatch):
    r = ModelRouter(settings(monkeypatch, INTERNAL_LLM_BASE_URL="http://npu:8080/v1", INTERNAL_LLM_MODEL="npu-m"))
    sel = r.select(db, customer(db), "t")
    assert sel.provider.name == "openai_compatible" and sel.provider.model == "npu-m" and not sel.provider.external
    assert r.cost(sel.provider, 10**6, 10**6) == 0.0
