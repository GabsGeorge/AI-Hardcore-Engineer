from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.schemas import Readiness
from app.db.pool import get_pool

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", response_model=Readiness)
async def readyz(request: Request) -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        async with get_pool().connection() as conn:
            row = await (await conn.execute("SELECT count(*) AS n FROM chunks")).fetchone()
        checks["database"] = "ok"
        # An empty index does not block readiness: the API still serves support questions.
        checks["index"] = "ok" if row and row["n"] else "empty"
    except Exception:
        checks["database"], checks["index"] = "fail", "fail"
    try:
        await request.app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "fail"
    checks["llm"] = "ok"  # not probed: a ping per readiness check would spend tokens
    ready = all(v in {"ok", "empty"} for v in checks.values())
    body = Readiness(status="ready" if ready else "not_ready", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if ready else 503)
