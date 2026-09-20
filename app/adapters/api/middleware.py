"""ASGI middleware: correlation id, access logging, security headers.

Written as pure ASGI rather than with Starlette's ``BaseHTTPMiddleware``.
``BaseHTTPMiddleware`` runs the downstream app in a task group behind memory
object streams, which breaks exception propagation to the error handlers and
leaks unclosed streams when a request raises. Pure ASGI has neither problem and
lets us mutate the response headers without buffering the body.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.infrastructure.logging import get_logger

REQUEST_ID_HEADER = "X-Request-ID"

#: A client-supplied correlation id outside this range is replaced with a UUID,
#: so an attacker cannot stuff arbitrary content into the log stream.
_MIN_ID_LEN = 8
_MAX_ID_LEN = 128

_logger = get_logger("http")


def current_request_id() -> str:
    """Return the correlation id bound to the current request, if any."""
    value = structlog.contextvars.get_contextvars().get("request_id", "")
    return str(value)


class RequestContextMiddleware:
    """Accept or mint an ``X-Request-ID``, bind it to the log context, echo it back.

    The legacy app had no correlation at all: a client-visible 500 could not be
    tied to any server-side line.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = ""
        for key, value in scope.get("headers", []):
            if key == b"x-request-id":
                incoming = value.decode("latin-1").strip()
                break
        request_id = incoming if _MIN_ID_LEN <= len(incoming) <= _MAX_ID_LEN else str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id

        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            _logger.exception(
                "request_failed",
                method=scope.get("method"),
                path=scope.get("path"),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            raise

        state: dict[str, Any] = scope.get("state", {})
        _logger.info(
            "request_completed",
            method=scope.get("method"),
            path=scope.get("path"),
            status_code=status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            user=state.get("username"),
            role=state.get("role"),
        )


class SecurityHeadersMiddleware:
    """Add the response headers the legacy app shipped none of."""

    def __init__(self, app: ASGIApp, *, enable_hsts: bool = False) -> None:
        self.app = app
        self._enable_hsts = enable_hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
                if self._enable_hsts:
                    headers.setdefault(
                        "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)
