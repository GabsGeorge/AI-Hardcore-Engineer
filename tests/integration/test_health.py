import httpx
import pytest

from app.db import pool as db_pool_module

pytestmark = pytest.mark.req("REQ-API-04")


async def test_healthz_is_ok(client: httpx.AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readyz_is_ready_when_dependencies_are_up(client: httpx.AsyncClient) -> None:
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "ok"
    assert body["checks"]["index"] in {"ok", "empty"}


class _BrokenPool:
    def connection(self) -> object:
        raise ConnectionError("database down")


async def test_readyz_returns_503_when_database_is_down(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db_pool_module, "_pool", _BrokenPool())
    resp = await client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "fail"
