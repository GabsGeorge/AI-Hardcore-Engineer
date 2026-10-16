"""Shared fixtures. Tests run against real Postgres/Redis on an internal Docker network and
never call external services: chat models, embeddings and reranker are fakes (ADR 0006)."""

import os
import secrets
from collections.abc import AsyncIterator, Iterator

# Test environment must be set before the app reads its settings.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", secrets.token_hex(32))
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SEED_REFERENCE_DATE", "2026-10-13")
os.environ.setdefault("METRICS_PORT", "0")  # no exporter thread in tests; read the registry
os.environ.setdefault("EVAL_SAMPLE_RATE", "0")  # no background judge calls in tests
os.environ.setdefault("SESSION_SECRET", secrets.token_hex(32))
os.environ.setdefault("PASSWORD_PEPPER", secrets.token_hex(32))

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from psycopg_pool import AsyncConnectionPool  # noqa: E402

from app.api.auth import create_token  # noqa: E402
from app.core import llm  # noqa: E402
from app.db import pool as pool_module  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.fakes import FakeLLM, SpyGraph, fake_embeddings  # noqa: E402

TEST_USERS = [
    ("cliente1988", "merchant", "Loja Exemplo 1988"),
    ("cliente2024", "merchant", "Loja Exemplo 2024"),
    ("operador01", "operator", "Operador 01"),
]

# Order matters only for readability; TRUNCATE ... CASCADE handles dependencies.
APP_TABLES = [
    "auth_login_attempts",
    "auth_one_time_tokens",
    "auth_sessions",
    "auth_credentials",
    "auth_accounts",
    "audit_events",
    "feedback",
    "handoffs",
    "conversations",
    "chunks",
    "documents",
    "settlements",
    "transactions",
    "terminals",
    "merchants",
    "decline_codes",
    "users",
    # LangGraph checkpoint tables (created by AsyncPostgresSaver.setup in the app lifespan)
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
]


@pytest.fixture(scope="session")
async def app() -> AsyncIterator[FastAPI]:
    application = create_app()
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture(scope="session")
async def session_pool(app: FastAPI) -> AsyncConnectionPool:
    return pool_module.get_pool()


@pytest.fixture
async def db_pool(session_pool: AsyncConnectionPool) -> AsyncConnectionPool:
    """Clean app tables with the test users recreated, for every test that touches the DB."""
    async with session_pool.connection() as conn:
        await conn.execute(f"TRUNCATE {', '.join(APP_TABLES)} RESTART IDENTITY CASCADE")
        for user_id, role, name in TEST_USERS:
            await conn.execute(
                "INSERT INTO users (id, role, display_name) VALUES (%s, %s, %s)",
                (user_id, role, name),
            )
    return session_pool


@pytest.fixture
def fake_llm() -> Iterator[FakeLLM]:
    fake = FakeLLM()
    llm.set_overrides(model_factory=fake.model, embeddings=fake_embeddings())
    yield fake
    llm.set_overrides(model_factory=None, embeddings=None)


@pytest.fixture
async def client(
    app: FastAPI, fake_llm: FakeLLM, db_pool: AsyncConnectionPool
) -> AsyncIterator[httpx.AsyncClient]:
    # Zera limites e idempotência entre testes para que a janela fixa não vaze entre casos.
    await app.state.redis.flushdb()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def spy_graph(app: FastAPI) -> Iterator[SpyGraph]:
    original = app.state.graph
    app.state.graph = spy = SpyGraph()
    yield spy
    app.state.graph = original


@pytest.fixture
def auth_headers() -> dict[str, dict[str, str]]:
    return {
        user_id: {"Authorization": f"Bearer {create_token(user_id, role)}"}
        for user_id, role, _ in TEST_USERS
    }
