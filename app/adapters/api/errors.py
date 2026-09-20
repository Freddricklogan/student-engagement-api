"""Centralized exception handlers emitting RFC 9457 ``application/problem+json``.

The legacy app handled only 404 and 500 and used an ad-hoc ``{"error": "..."}``
envelope; everything else leaked Flask's HTML error pages.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.adapters.api.middleware import current_request_id
from app.domain.errors import DomainError
from app.infrastructure.logging import get_logger

PROBLEM_CONTENT_TYPE = "application/problem+json"
_PROBLEM_BASE = "https://freddricklogan.github.io/student-engagement-api/problems"
_logger = get_logger("errors")

_TITLES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
}

_SLUGS: dict[int, str] = {
    400: "bad-request",
    401: "unauthorized",
    403: "forbidden",
    404: "not-found",
    405: "method-not-allowed",
    409: "conflict",
    422: "validation-error",
    429: "rate-limit-exceeded",
    500: "internal-server-error",
}


def problem_response(
    request: Request,
    *,
    status_code: int,
    detail: str,
    title: str | None = None,
    problem_type: str | None = None,
    errors: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a problem+json response."""
    body: dict[str, Any] = {
        "type": problem_type or f"{_PROBLEM_BASE}/{_SLUGS.get(status_code, 'error')}",
        "title": title or _TITLES.get(status_code, "Error"),
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
        "request_id": getattr(request.state, "request_id", None) or current_request_id(),
    }
    if errors:
        body["errors"] = errors

    response_headers = {"X-Request-ID": str(body["request_id"])}
    if headers:
        response_headers.update(headers)
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=response_headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach every handler. Nothing may escape as an unformatted response."""

    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        headers: dict[str, str] | None = None
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            headers = {"WWW-Authenticate": "Bearer"}
        elif exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            headers = {"Retry-After": "60"}
        return problem_response(
            request,
            status_code=exc.status_code,
            detail=exc.detail,
            title=exc.title,
            problem_type=exc.problem_type,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(part) for part in err.get("loc", ()) if part != "body"),
                "message": err.get("msg", "invalid value"),
                "type": err.get("type", "value_error"),
            }
            for err in exc.errors()
        ]
        return problem_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The request body or parameters failed validation.",
            errors=errors,
        )

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return problem_response(
            request,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {exc.detail}.",
            headers={"Retry-After": "60"},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        headers = dict(exc.headers or {})
        return problem_response(
            request,
            status_code=exc.status_code,
            detail=str(exc.detail),
            headers=headers or None,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Log the full traceback server-side; return nothing but a correlation id.
        _logger.exception("unhandled_exception", path=request.url.path, error=type(exc).__name__)
        return problem_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Quote the request_id when reporting this.",
        )
