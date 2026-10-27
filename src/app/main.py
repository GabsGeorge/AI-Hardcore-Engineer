import asyncio
import contextlib
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from prometheus_client import start_http_server
from redis.asyncio import Redis

from app.api import admin, auth_endpoints, chat, conversations, handoffs, health, me
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.db.migrate import migrate
from app.db.pool import close_pool, open_pool
from app.graph.builder import build_graph
from app.observability.logging import configure_logging, get_logger
from app.observability.metrics import HTTP_LATENCY, HTTP_REQUESTS
from app.observability.tracing import configure_tracing, current_trace_id, get_tracer
from app.ops.scheduler import start as start_scheduler


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
    app.state.scheduler_task = await start_scheduler(pool, app.state.graph)
    if settings.metrics_port:
        # Separate port, not published by compose: only Prometheus on the internal network scrapes.
        start_http_server(settings.metrics_port)
    try:
        yield
    finally:
        app.state.scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await app.state.scheduler_task
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
                path = getattr(route, "path", request.url.path)
                elapsed = time.perf_counter() - started
                HTTP_REQUESTS.labels(path, request.method, str(status)).inc()
                HTTP_LATENCY.labels(path).observe(elapsed)
                get_logger().info(
                    "request",
                    route=path,
                    method=request.method,
                    status=status,
                    latency_ms=round(elapsed * 1000),
                )
                structlog.contextvars.clear_contextvars()

    app.include_router(health.router)
    app.include_router(auth_endpoints.router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    app.include_router(handoffs.router)
    app.include_router(me.router)
    app.include_router(admin.router)
    return app


app = create_app()
