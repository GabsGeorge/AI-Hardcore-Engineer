import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis

from app.api import chat, health
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.db.migrate import migrate
from app.db.pool import close_pool, open_pool
from app.graph.builder import build_graph
from app.observability.logging import configure_logging, get_logger
from app.observability.tracing import configure_tracing, current_trace_id, get_tracer


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    configure_tracing(settings.otel_exporter_otlp_endpoint)
    pool = await open_pool(settings.database_url)
    await migrate(pool)
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()
    app.state.graph = build_graph(checkpointer)
    app.state.redis = Redis.from_url(settings.redis_url)
    try:
        yield
    finally:
        await app.state.redis.aclose()
        await close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="Getnet Multi-Agent Support API", version="1.0.0", lifespan=lifespan)
    install_error_handlers(app)

    @app.middleware("http")
    async def trace_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        with get_tracer().start_as_current_span("http.request"):
            trace_id = current_trace_id()
            request.state.trace_id = trace_id
            structlog.contextvars.bind_contextvars(trace_id=trace_id)
            started = time.perf_counter()
            status = 500
            try:
                response = await call_next(request)
                status = response.status_code
                return response
            finally:
                route = request.scope.get("route")
                get_logger().info(
                    "request",
                    route=getattr(route, "path", request.url.path),
                    method=request.method,
                    status=status,
                    latency_ms=round((time.perf_counter() - started) * 1000),
                )
                structlog.contextvars.clear_contextvars()

    app.include_router(health.router)
    app.include_router(chat.router)
    return app


app = create_app()
