"""Async retry with exponential backoff and jitter for flaky external calls (REQ-REL-01)."""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

T = TypeVar("T")


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
