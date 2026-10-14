"""Rate limit e idempotência via Redis (REQ-SEC-08, REQ-API-06).

Rate limit: janela fixa de 60 s por ``user_id`` com ``INCR``+``EXPIRE`` (shortcut: a janela
fixa pode ter uma pequena rajada na borda; aceitável para o perfil de uso e documentado em
``docs/limitations.md`` após T178).

Idempotência: chave ``idem:{user}:{key}`` com corpo hasheado e resposta JSON por 24 h. Mesmo
corpo → mesma resposta sem reexecutar; corpo diferente para a mesma chave → 409.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from fastapi import Request
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.errors import AppError


def _rate_key(user_id: str, window: int) -> str:
    return f"rl:{user_id}:{window}"


async def check_rate_limit(request: Request, user_id: str) -> None:
    """Incrementa o contador da janela corrente. 31ª no minuto → 429 com Retry-After."""
    settings = get_settings()
    redis: Redis = request.app.state.redis
    now_ms = int(request.state.now_ms) if hasattr(request.state, "now_ms") else 0
    import time

    now = time.time() if now_ms == 0 else now_ms / 1000
    window = int(now // 60)
    key = _rate_key(user_id, window)
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 65)
    if count > settings.rate_limit_per_min:
        retry_after = max(1, int(math.ceil(60 - (now % 60))))
        raise AppError(
            429,
            "rate_limited",
            f"Too many requests. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )


def _hash_body(body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def idempotency_get_or_claim(
    request: Request, user_id: str, key: str | None, body: dict[str, Any]
) -> dict[str, Any] | None:
    """Devolve a resposta cacheada quando a chave + corpo batem; levanta 409 quando a chave
    foi reutilizada com corpo diferente. ``None`` significa que a requisição deve prosseguir
    e, ao concluir, chamar ``idempotency_store`` para gravar a resposta."""
    if key is None:
        return None
    redis: Redis = request.app.state.redis
    rec_key = f"idem:{user_id}:{key}"
    raw = await redis.get(rec_key)
    body_hash = _hash_body(body)
    if raw is None:
        placeholder = json.dumps({"body_hash": body_hash, "response": None})
        # Reserva a chave com TTL de 24 h; nunca sobrescreve uma entrada anterior.
        set_ok = await redis.set(rec_key, placeholder, ex=24 * 3600, nx=True)
        if not set_ok:
            raw = await redis.get(rec_key)
            if raw is None:
                return None
        else:
            return None
    rec = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
    if rec.get("body_hash") != body_hash:
        raise AppError(
            409, "idempotency_conflict", "Idempotency-Key reused with a different payload."
        )
    cached = rec.get("response")
    return cached if isinstance(cached, dict) else None


async def idempotency_store(
    request: Request, user_id: str, key: str | None, body: dict[str, Any], response: dict[str, Any]
) -> None:
    if key is None:
        return
    redis: Redis = request.app.state.redis
    rec_key = f"idem:{user_id}:{key}"
    rec = {"body_hash": _hash_body(body), "response": response}
    await redis.set(rec_key, json.dumps(rec), ex=24 * 3600)
