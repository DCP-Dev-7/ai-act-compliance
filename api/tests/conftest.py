import os
import sys
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DEMO_SERVICE_URL"] = "http://demo.test"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("INTERNAL_LLM_BASE_URL", None)
os.environ["LLM_PROVIDER"] = "auto"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """SQLite 메모리 DB + 임시 증적 디렉터리 + 시드."""
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "evidence"))
    from app import models  # noqa: F401
    from app.db import Base, init_engine, session_factory
    from app.llm.router import ModelRouter, set_router
    from app.seed import seed

    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    set_router(ModelRouter())
    with session_factory()() as db:
        seed(db)
    yield tmp_path
    set_router(None)
    engine.dispose()


@pytest.fixture()
def db(env):
    from app.db import session_factory

    with session_factory()() as s:
        yield s


@pytest.fixture()
def client(env):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def login(client, email, password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def auth(client):
    client.cookies.clear()
    out = {role: login(client, email) for role, email in
           [("customer", "a-company@demo"), ("consultant", "consultant@demo"), ("ops", "ops@demo")]}
    client.cookies.clear()
    return out


DEMO_DIR = API_DIR.parent / "demo-service"


def demo_transport():
    """demo-service 정적 파일을 그대로 돌려주는 httpx MockTransport."""
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host != "demo.test":
            return httpx.Response(599)
        path = request.url.path.lstrip("/") or "index.html"
        f = DEMO_DIR / path
        if not f.is_file():
            return httpx.Response(404)
        return httpx.Response(200, content=f.read_bytes())

    return httpx.MockTransport(handler)
