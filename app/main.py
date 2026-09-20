"""Application factory and ASGI entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from scalar_fastapi import get_scalar_api_reference
from slowapi.middleware import SlowAPIMiddleware

from app.adapters.api.errors import register_exception_handlers
from app.adapters.api.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.adapters.api.ratelimit import configure_limiter
from app.adapters.api.routers import analytics, auth, events, health, legacy, sessions, students
from app.infrastructure.db import dispose_engine, init_engine
from app.infrastructure.logging import configure_logging, get_logger
from app.infrastructure.seed import bootstrap_demo, create_schema
from app.infrastructure.settings import Settings, get_settings

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

DESCRIPTION = """\
Engagement analytics for online learning: students, learning sessions, engagement
events and the aggregates an academic-affairs team actually reads.

### Try it in 30 seconds

1. Expand **auth → POST /api/v1/auth/token** and click **Test Request**.
2. Send `username=demo`, `password=demo-viewer-2026` (read-only).
3. Copy `access_token` into the **Authorize** box, then call
   **GET /api/v1/analytics/summary**.

The `demo` account is a **viewer**: every `GET` succeeds, every write returns
`403` as an RFC 9457 `application/problem+json` document. `analyst` /
`analyst-demo-2026` can write.

### Conventions

* Errors are always `application/problem+json` (RFC 9457) and always carry the
  `request_id` that also appears in the `X-Request-ID` response header and in
  the server's JSON logs.
* Legacy `/api/*` paths from v1.x of this service still resolve and return
  identical bodies. They are omitted from this reference on purpose.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the engine's lifetime and run the demo bootstrap if enabled."""
    settings: Settings = app.state.settings
    engine = init_engine(settings)
    logger = get_logger("startup")
    if settings.demo_mode:
        await bootstrap_demo(engine, settings)
        logger.info("demo_mode_ready", demo_user=settings.demo_viewer_username)
    else:
        await create_schema(engine)
    logger.info(
        "application_started",
        version=settings.app_version,
        environment=settings.environment,
        database="sqlite" if settings.is_sqlite else "postgres",
    )
    try:
        yield
    finally:
        await dispose_engine()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRIPTION,
        lifespan=lifespan,
        # /docs is served by Scalar below; ReDoc is kept per the standard.
        docs_url=None,
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={"name": "Freddrick Logan", "url": "https://fredlogan.phd"},
        license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    )
    app.state.settings = settings

    app.state.limiter = configure_limiter(settings)

    # Order matters: request context is outermost so every log line and every
    # problem document carries the correlation id.
    if settings.rate_limit_enabled:
        # slowapi's middleware is BaseHTTPMiddleware-based, so it is only added
        # when it will actually do something.
        app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=settings.environment == "production")
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(auth.router)
    v1.include_router(students.router)
    v1.include_router(sessions.router)
    v1.include_router(events.router)
    v1.include_router(analytics.router)
    app.include_router(v1)
    app.include_router(health.router)
    app.include_router(legacy.router)

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    _register_pages(app, settings)
    return app


def _register_pages(app: FastAPI, settings: Settings) -> None:
    """Landing page, dashboard and the Scalar API reference."""

    @app.get("/", include_in_schema=False)
    async def landing() -> FileResponse:
        """GET / stays the entry point it always was — now a chooser rather than
        a straight render, so neither the dashboard nor the explorer is buried."""
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(STATIC_DIR / "dashboard.html")

    @app.get("/docs", include_in_schema=False)
    async def scalar_docs() -> HTMLResponse:
        """Scalar reference with the generated OpenAPI document preloaded."""
        reference: HTMLResponse = get_scalar_api_reference(
            openapi_url=app.openapi_url or "/openapi.json",
            title=f"{settings.app_name} — API reference",
        )
        return reference

    @app.get("/demo-credentials", include_in_schema=False)
    async def demo_credentials(request: Request) -> dict[str, Any]:
        """The read-only demo login, so the explorer page needs no hard-coded secret.

        Served only while ``DEMO_MODE`` is on; returns 404 otherwise.
        """
        if not settings.demo_mode:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Demo mode is disabled.")
        return {
            "username": settings.demo_viewer_username,
            "password": settings.demo_viewer_password,
            "role": "viewer",
            "note": "Read-only. Writes return 403 problem+json.",
            "token_url": str(request.url_for("issue_token")),
        }


app = create_app()
