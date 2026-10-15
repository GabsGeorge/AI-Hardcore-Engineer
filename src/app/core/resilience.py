"""Async retry com backoff e jitter + circuit breaker in-process (REQ-REL-01, REQ-REL-03).

O circuit breaker é por chave (``openai``, ``duckduckgo``, ``reranker`` …) e vive por processo
(``shortcut:`` documentado em docs/limitations.md — num cluster real, migrar para Redis). Após
N falhas consecutivas abre e responde ``CircuitOpen`` sem esperar; depois de ``recovery_s``
entra em half-open e um único probe pode fechar o circuito.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

T = TypeVar("T")


class CircuitOpen(RuntimeError):
    """Circuito aberto para a chave informada: a chamada responde degradado."""


@dataclass
class _Breaker:
    failures: int = 0
    opened_at: float = 0.0
    half_open: bool = False


class CircuitBreaker:
    """Breaker por chave, com três estados (closed/open/half-open)."""

    def __init__(self, failure_threshold: int = 5, recovery_seconds: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._breakers: dict[str, _Breaker] = {}
        self._lock = asyncio.Lock()

    async def before(self, key: str) -> None:
        """Levanta ``CircuitOpen`` quando o circuito está aberto; promove a half-open quando
        o tempo de recuperação já passou."""
        async with self._lock:
            b = self._breakers.setdefault(key, _Breaker())
            if b.opened_at and not b.half_open:
                if time.monotonic() - b.opened_at >= self.recovery_seconds:
                    b.half_open = True
                else:
                    raise CircuitOpen(f"circuit open for {key}")

    async def record_success(self, key: str) -> None:
        async with self._lock:
            self._breakers[key] = _Breaker()  # fecha o circuito

    async def record_failure(self, key: str) -> None:
        async with self._lock:
            b = self._breakers.setdefault(key, _Breaker())
            b.failures += 1
            if b.half_open or b.failures >= self.failure_threshold:
                b.opened_at = time.monotonic()
                b.half_open = False

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._breakers.clear()
        else:
            self._breakers.pop(key, None)


_GLOBAL = CircuitBreaker()


def get_breaker() -> CircuitBreaker:
    return _GLOBAL


def with_circuit_breaker(
    key: str, breaker: CircuitBreaker | None = None
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decora uma função async com o breaker por chave. ``CircuitOpen`` propaga para o chamador,
    que decide a resposta degradada."""

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            cb = breaker or _GLOBAL
            await cb.before(key)
            try:
                result = await fn(*args, **kwargs)
            except Exception:
                await cb.record_failure(key)
                raise
            await cb.record_success(key)
            return result

        return wrapper

    return decorator


def with_retry(
    *,
    attempts: int = 3,
    multiplier: float = 0.1,
    max_wait: float = 1.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorate an async function with exponential backoff + jitter. Opt-in per call site; the
    per-tool timeout in `call_tool` still caps total time."""

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(attempts),
                wait=wait_exponential_jitter(multiplier=multiplier, max=max_wait),
                retry=retry_if_exception_type(retry_on),
                reraise=True,
            ):
                with attempt:
                    return await fn(*args, **kwargs)
            raise RuntimeError("unreachable")  # tenacity always yields at least once

        return wrapper

    return decorator
