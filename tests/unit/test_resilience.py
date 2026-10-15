"""Retry com jitter e circuit breaker in-process (REQ-REL-01, REQ-REL-03)."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.core.resilience import (
    CircuitBreaker,
    CircuitOpen,
    with_circuit_breaker,
    with_retry,
)


@pytest.mark.req("REQ-REL-01")
async def test_retry_recovers_after_transient_failure() -> None:
    """Falha transitória → nova tentativa; sucesso na próxima; backoff bounded."""
    tries = {"n": 0}

    @with_retry(attempts=3, multiplier=0.0, max_wait=0.0)
    async def flaky() -> str:
        tries["n"] += 1
        if tries["n"] < 2:
            raise RuntimeError("boom")
        return "ok"

    assert await flaky() == "ok"
    assert tries["n"] == 2


@pytest.mark.req("REQ-REL-01")
async def test_retry_gives_up_and_reraises() -> None:
    """Persistindo o erro, a função devolve a última exceção para o chamador."""

    @with_retry(attempts=2, multiplier=0.0, max_wait=0.0)
    async def always_fails() -> str:
        raise RuntimeError("still broken")

    with pytest.raises(RuntimeError, match="still broken"):
        await always_fails()


@pytest.mark.req("REQ-REL-03")
async def test_circuit_opens_after_threshold_and_fails_fast() -> None:
    """N falhas consecutivas abrem o circuito; a próxima chamada responde sem esperar."""
    cb = CircuitBreaker(failure_threshold=3, recovery_seconds=10)

    @with_circuit_breaker("test", breaker=cb)
    async def external() -> str:
        raise RuntimeError("downstream unavailable")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await external()

    started = time.monotonic()
    with pytest.raises(CircuitOpen):
        await external()
    assert time.monotonic() - started < 0.05, "aberto deve falhar imediatamente"


@pytest.mark.req("REQ-REL-03")
async def test_circuit_half_opens_and_closes_on_success() -> None:
    """Depois de ``recovery_seconds`` entra em half-open; um sucesso fecha o circuito."""
    cb = CircuitBreaker(failure_threshold=1, recovery_seconds=0.01)
    call_count = {"n": 0}

    @with_circuit_breaker("test", breaker=cb)
    async def external() -> str:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("boom")
        return "ok"

    with pytest.raises(RuntimeError):
        await external()
    # Imediatamente após: aberto
    with pytest.raises(CircuitOpen):
        await external()
    # Após recovery_seconds: entra em half-open, probe de sucesso fecha o circuito
    await asyncio.sleep(0.02)
    assert await external() == "ok"
    # Fechado novamente: chamadas seguintes passam direto
    assert await external() == "ok"
