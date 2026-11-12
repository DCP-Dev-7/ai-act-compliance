"""환경 변수 기반 설정. 모든 값은 호출 시점에 읽어 테스트에서 쉽게 바꿀 수 있게 한다."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    cookie_name: str
    cookie_secure: bool
    session_hours: int
    # LLM
    llm_provider: str  # auto | mock | anthropic | openai_compatible
    anthropic_api_key: str
    anthropic_model: str
    internal_llm_base_url: str
    internal_llm_model: str
    internal_llm_api_key: str
    price_in_per_mtok: float
    price_out_per_mtok: float
    budget_fallback_to_mock: bool
    # 증적
    evidence_backend: str  # filesystem | s3
    evidence_dir: str
    retention_years: int
    # 기술 점검
    demo_service_url: str
    tech_check_allowlist: tuple[str, ...]
    # 운영
    scheduler_enabled: bool
    golden_threshold: float
    cors_origins: tuple[str, ...]


def get_settings() -> Settings:
    demo_url = os.environ.get("DEMO_SERVICE_URL", "http://localhost:8081").rstrip("/")
    allow = os.environ.get("TECH_CHECK_ALLOWLIST", "") or demo_url
    return Settings(
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql+psycopg://aiact:aiact@localhost:5432/aiact"
        ),
        jwt_secret=os.environ.get("JWT_SECRET", "demo-only-secret-change-me-please-32b"),
        cookie_name="aiact_session",
        cookie_secure=_bool("COOKIE_SECURE", False),
        session_hours=int(os.environ.get("SESSION_HOURS", "12")),
        llm_provider=os.environ.get("LLM_PROVIDER", "auto").strip().lower() or "auto",
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-fable-5-2").strip(),
        internal_llm_base_url=os.environ.get("INTERNAL_LLM_BASE_URL", "").strip().rstrip("/"),
        internal_llm_model=os.environ.get("INTERNAL_LLM_MODEL", "internal-model").strip(),
        internal_llm_api_key=os.environ.get("INTERNAL_LLM_API_KEY", "").strip(),
        price_in_per_mtok=float(os.environ.get("LLM_PRICE_IN_PER_MTOK", "8")),
        price_out_per_mtok=float(os.environ.get("LLM_PRICE_OUT_PER_MTOK", "40")),
        budget_fallback_to_mock=_bool("BUDGET_FALLBACK_TO_MOCK", True),
        evidence_backend=os.environ.get("EVIDENCE_BACKEND", "filesystem").strip().lower(),
        evidence_dir=os.environ.get("EVIDENCE_DIR", str(BASE_DIR / "var" / "evidence")),
        retention_years=int(os.environ.get("EVIDENCE_RETENTION_YEARS", "5")),
        demo_service_url=demo_url,
        tech_check_allowlist=tuple(a.strip().rstrip("/") for a in allow.split(",") if a.strip()),
        scheduler_enabled=_bool("SCHEDULER_ENABLED", True),
        golden_threshold=float(os.environ.get("GOLDEN_THRESHOLD", "0.9")),
        cors_origins=tuple(
            o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()
        ),
    )
