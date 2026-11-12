"""ModelRouter: 고객 데이터 정책·예산에 따라 LLM 공급자를 고르고, 비식별화·사용량 집계를 한다."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..deid import Deidentifier
from ..models import Customer, LLMUsage
from .anthropic_provider import AnthropicProvider
from .base import BudgetExceeded, LLMProvider, LLMResult, PolicyViolation, estimate_tokens
from .mock import MockProvider
from .openai_compat import OpenAICompatibleProvider


@dataclass
class Selection:
    provider: LLMProvider
    reason: str  # configured | data_policy | budget_exceeded
    configured: str

    @property
    def is_mock(self) -> bool:
        return self.provider.name == "mock"


class ModelRouter:
    def __init__(self, settings: Settings | None = None, providers: dict[str, LLMProvider] | None = None):
        self.settings = settings or get_settings()
        self._providers: dict[str, LLMProvider] = dict(providers or {})
        self.deid = Deidentifier()

    # ---- 공급자 구성 ----
    def configured_name(self) -> str:
        s = self.settings
        name = s.llm_provider
        if name == "auto":
            if s.anthropic_api_key:
                return "anthropic"
            if s.internal_llm_base_url:
                return "openai_compatible"
            return "mock"
        if name == "anthropic" and not s.anthropic_api_key and "anthropic" not in self._providers:
            return "mock"
        if name == "openai_compatible" and not s.internal_llm_base_url and "openai_compatible" not in self._providers:
            return "mock"
        return name if name in ("mock", "anthropic", "openai_compatible") else "mock"

    def has_internal(self) -> bool:
        return "openai_compatible" in self._providers or bool(self.settings.internal_llm_base_url)

    def provider(self, name: str) -> LLMProvider:
        if name not in self._providers:
            s = self.settings
            if name == "anthropic":
                self._providers[name] = AnthropicProvider(s.anthropic_api_key, s.anthropic_model)
            elif name == "openai_compatible":
                self._providers[name] = OpenAICompatibleProvider(
                    s.internal_llm_base_url, s.internal_llm_model, s.internal_llm_api_key, external=False)
            else:
                self._providers[name] = MockProvider()
        return self._providers[name]

    # ---- 예산 ----
    def month_cost(self, db: Session, customer_id: int) -> float:
        now = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        total = db.scalar(
            select(func.coalesce(func.sum(LLMUsage.cost_usd), 0.0)).where(
                LLMUsage.customer_id == customer_id, LLMUsage.created_at >= start)
        )
        return float(total or 0.0)

    def cost(self, provider: LLMProvider, input_tokens: int, output_tokens: int) -> float:
        if provider.name != "anthropic":
            return 0.0  # mock·내부 추론은 토큰만 집계(외부 과금 없음)
        s = self.settings
        return round(input_tokens / 1e6 * s.price_in_per_mtok + output_tokens / 1e6 * s.price_out_per_mtok, 6)

    # ---- 선택 ----
    def select(self, db: Session, customer: Customer | None, task: str, *, require_external: bool = False) -> Selection:
        configured = self.configured_name()
        prov = self.provider(configured)
        if customer is not None and prov.external and not customer.allow_external:
            if require_external:
                raise PolicyViolation(
                    f"고객 '{customer.name}'의 데이터 정책(allow_external=false)상 외부 LLM({prov.name}) 호출이 금지되어 있습니다")
            fallback = self.provider("openai_compatible") if self.has_internal() else self.provider("mock")
            if fallback.external:
                raise PolicyViolation("내부 공급자가 external로 구성되어 있어 사용할 수 없습니다")
            return Selection(fallback, "data_policy", configured)
        if require_external and not prov.external:
            if customer is not None and not customer.allow_external:
                raise PolicyViolation(
                    f"고객 '{customer.name}'의 데이터 정책(allow_external=false)상 외부 LLM 호출이 금지되어 있습니다")
        if customer is not None and prov.external:
            spent = self.month_cost(db, customer.id)
            if spent >= (customer.monthly_budget_usd or 0):
                if not self.settings.budget_fallback_to_mock:
                    raise BudgetExceeded(
                        f"고객 '{customer.name}' 월 예산 초과: ${spent:.4f} / ${customer.monthly_budget_usd:.2f}")
                return Selection(self.provider("mock"), "budget_exceeded", configured)
        return Selection(prov, "configured", configured)

    # ---- 호출 ----
    def record(self, db: Session, customer: Customer | None, task: str, provider: LLMProvider,
               input_tokens: int, output_tokens: int, note: str = "") -> LLMUsage:
        u = LLMUsage(customer_id=customer.id if customer else None, task=task, provider=provider.name,
                     model=provider.model, input_tokens=input_tokens, output_tokens=output_tokens,
                     cost_usd=self.cost(provider, input_tokens, output_tokens), note=note)
        db.add(u)
        db.flush()
        return u

    def record_mock(self, db: Session, customer: Customer | None, task: str, sel: Selection,
                    input_text: str, output_text: str) -> LLMUsage:
        note = "" if sel.reason == "configured" else f"대체 사유: {sel.reason}"
        return self.record(db, customer, task, sel.provider, estimate_tokens(input_text),
                           estimate_tokens(output_text), note)

    def complete(self, db: Session, customer: Customer | None, task: str, system: str, prompt: str,
                 *, sel: Selection | None = None, max_tokens: int = 2000) -> tuple[LLMResult, dict[str, Any]]:
        """선택된 공급자로 호출한다. 외부 공급자면 프롬프트를 비식별화하고 응답에서 복원한다."""
        sel = sel or self.select(db, customer, task)
        prov = sel.provider
        if customer is not None and prov.external and not customer.allow_external:
            raise PolicyViolation("데이터 정책상 외부 호출 금지")  # 이중 방어
        mapping: dict[str, str] = {}
        info: dict[str, Any] = {"deidentified": False, "pii_counts": {}}
        if prov.external:
            d1 = self.deid.deidentify(system)
            d2 = self.deid.deidentify(prompt, d1.mapping)
            system, prompt, mapping = d1.text, d2.text, d2.mapping
            counts = dict(d1.counts)
            for k, v in d2.counts.items():
                counts[k] = counts.get(k, 0) + v
            info = {"deidentified": True, "pii_counts": counts}
        res = prov.complete(system, prompt, max_tokens=max_tokens)
        if mapping:
            res.text = self.deid.restore(res.text, mapping)
        self.record(db, customer, task, prov, res.input_tokens, res.output_tokens,
                    "" if sel.reason == "configured" else f"대체 사유: {sel.reason}")
        return res, info


_router: ModelRouter | None = None


def get_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


def set_router(r: ModelRouter | None) -> None:
    global _router
    _router = r
