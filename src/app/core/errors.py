"""Typed errors rendered as the `Error` schema of contracts/openapi.yaml."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.details, self.headers = details, headers


def unauthorized() -> AppError:
    return AppError(401, "unauthorized", "Missing or invalid credentials.")


def forbidden(code: str = "forbidden_role", message: str = "Not allowed.") -> AppError:
    return AppError(403, code, message)


def not_found() -> AppError:
    return AppError(404, "not_found", "Resource not found.")


def error_response(
    status: int,
    code: str,
    message: str,
    trace_id: str,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return JSONResponse({"error": error, "trace_id": trace_id}, status_code=status, headers=headers)


def _trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", "")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(
            exc.status, exc.code, exc.message, _trace_id(request), exc.details, exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Only location and type: the rejected input may contain PII and is never echoed.
        details = [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
        return error_response(
            422, "validation_error", "Invalid request.", _trace_id(request), details
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # No exception text in the body: it may carry internals or user data.
        return error_response(500, "internal_error", "Unexpected error.", _trace_id(request))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error_response(exc.status_code, code, str(exc.detail), _trace_id(request))
