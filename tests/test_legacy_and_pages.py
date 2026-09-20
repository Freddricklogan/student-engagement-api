"""Backwards compatibility, static pages, health, docs and settings."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.infrastructure.settings import Settings

LEGACY_TO_V1: tuple[tuple[str, str], ...] = (
    ("/api/students", "/api/v1/students"),
    ("/api/sessions", "/api/v1/sessions"),
    ("/api/events", "/api/v1/events"),
    ("/api/analytics/overview", "/api/v1/analytics/summary"),
    ("/api/analytics/sessions-by-course", "/api/v1/analytics/sessions-by-course"),
    ("/api/analytics/engagement-trend", "/api/v1/analytics/engagement-trend"),
    ("/api/analytics/top-students", "/api/v1/analytics/top-students"),
)


@pytest.mark.parametrize(("legacy", "v1"), LEGACY_TO_V1)
async def test_legacy_alias_returns_an_identical_body(
    client: AsyncClient, viewer_headers: dict[str, str], legacy: str, v1: str
) -> None:
    old = await client.get(legacy, headers=viewer_headers)
    new = await client.get(v1, headers=viewer_headers)
    assert old.status_code == new.status_code == 200
    assert old.json() == new.json()


async def test_legacy_single_student_alias(
    client: AsyncClient, viewer_headers: dict[str, str]
) -> None:
    old = await client.get("/api/students/1", headers=viewer_headers)
    new = await client.get("/api/v1/students/1", headers=viewer_headers)
    assert old.status_code == 200
    assert old.json() == new.json()


async def test_legacy_writes_still_work_for_an_analyst(
    client: AsyncClient, analyst_headers: dict[str, str]
) -> None:
    created = await client.post(
        "/api/students",
        json={
            "student_id": "STU60001",
            "first_name": "Legacy",
            "last_name": "Writer",
            "email": "legacy.writer@example.edu",
        },
        headers=analyst_headers,
    )
    assert created.status_code == 201
    student_pk = created.json()["id"]

    session = await client.post(
        "/api/sessions",
        json={
            "student_id": student_pk,
            "course_id": "CS101",
            "start_time": "2026-02-01T09:00:00Z",
            "end_time": "2026-02-01T10:30:00Z",
            "platform": "Zoom",
        },
        headers=analyst_headers,
    )
    assert session.status_code == 201
    assert session.json()["duration_minutes"] == 90.0

    evt = await client.post(
        "/api/events",
        json={
            "session_id": session.json()["id"],
            "event_type": "lab_exercise",
            "engagement_score": 0.72,
            "event_data": {"action": "lab_exercise", "index": 0},
        },
        headers=analyst_headers,
    )
    assert evt.status_code == 201
    assert evt.json()["event_data"] == {"action": "lab_exercise", "index": 0}


async def test_legacy_docs_path_redirects_to_the_reference(client: AsyncClient) -> None:
    response = await client.get("/api/docs")
    assert response.status_code == 308
    assert response.headers["location"] == "/docs"


async def test_legacy_aliases_are_absent_from_the_openapi_schema(
    client: AsyncClient,
) -> None:
    schema = (await client.get("/openapi.json")).json()
    assert "/api/students" not in schema["paths"]
    assert "/api/v1/students" in schema["paths"]


# --- pages --------------------------------------------------------------------


async def test_root_serves_the_landing_page(client: AsyncClient) -> None:
    """GET / must keep working — it is the documented entry point."""
    response = await client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Open dashboard" in response.text
    assert "Open API explorer" in response.text


async def test_dashboard_is_served(client: AsyncClient) -> None:
    response = await client.get("/dashboard")
    assert response.status_code == 200
    assert "Student Engagement Analytics" in response.text


async def test_scalar_reference_is_served_at_docs(client: AsyncClient) -> None:
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "openapi.json" in response.text


async def test_redoc_is_kept(client: AsyncClient) -> None:
    assert (await client.get("/redoc")).status_code == 200


async def test_openapi_document_is_generated(client: AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    assert schema["info"]["title"]
    assert "/api/v1/auth/token" in schema["paths"]
    assert "/api/v1/analytics/summary" in schema["paths"]


async def test_static_assets_are_mounted(client: AsyncClient) -> None:
    assert (await client.get("/static/css/style.css")).status_code == 200
    assert (await client.get("/static/js/dashboard.js")).status_code == 200


async def test_demo_credentials_endpoint_is_off_when_demo_mode_is_off(
    client: AsyncClient,
) -> None:
    """The test settings have DEMO_MODE off, so the helper must 404."""
    assert (await client.get("/demo-credentials")).status_code == 404


async def test_demo_credentials_endpoint_when_demo_mode_is_on(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    from httpx import ASGITransport

    from app.infrastructure import db as db_module
    from app.main import create_app

    db_path = tmp_path_factory.mktemp("demo") / "demo.db"
    demo_settings = Settings(
        environment="ci",
        demo_mode=True,
        database_url=f"sqlite+aiosqlite:///{db_path}",
        jwt_secret_key="another-test-secret-long-enough-0123456789abcdef",
        rate_limit_enabled=False,
        log_format="console",
        log_level="WARNING",
    )
    application = create_app(demo_settings)
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://testserver"
    ) as http:
        # Lifespan is not run by ASGITransport, so bring the engine up by hand.
        from app.infrastructure.seed import bootstrap_demo

        engine = db_module.init_engine(demo_settings)
        await bootstrap_demo(engine, demo_settings)

        response = await http.get("/demo-credentials")
        assert response.status_code == 200
        body = response.json()
        assert body["username"] == demo_settings.demo_viewer_username
        assert body["role"] == "viewer"
        assert body["token_url"].endswith("/api/v1/auth/token")

        # And the advertised credentials actually work.
        token = await http.post(
            "/api/v1/auth/token",
            data={"username": body["username"], "password": body["password"]},
        )
        assert token.status_code == 200
        assert token.json()["role"] == "viewer"

        await db_module.dispose_engine()


# --- health ---------------------------------------------------------------------


async def test_health_needs_no_token(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness_reports_the_database(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


# --- settings ----------------------------------------------------------------------


def test_csv_env_values_are_split_into_lists() -> None:
    settings = Settings(
        jwt_secret_key="x" * 40,
        cors_allow_origins="https://a.example, https://b.example",
    )
    assert settings.cors_allow_origins == ["https://a.example", "https://b.example"]


def test_json_list_env_values_still_work() -> None:
    settings = Settings(
        jwt_secret_key="x" * 40,
        cors_allow_origins='["https://c.example"]',
    )
    assert settings.cors_allow_origins == ["https://c.example"]


def test_production_without_a_secret_fails_fast() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET_KEY must be set"):
        Settings(environment="production", demo_mode=False, jwt_secret_key="")


def test_a_short_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 32 characters"):
        Settings(environment="production", demo_mode=False, jwt_secret_key="too-short")


def test_demo_mode_generates_an_ephemeral_secret() -> None:
    settings = Settings(environment="local", demo_mode=True, jwt_secret_key="")
    assert len(settings.jwt_secret_key) >= 32


def test_is_sqlite_flag() -> None:
    assert Settings(jwt_secret_key="x" * 40).is_sqlite
    assert not Settings(
        jwt_secret_key="x" * 40,
        database_url="postgresql+asyncpg://u:p@localhost/db",
    ).is_sqlite


# --- lifespan -----------------------------------------------------------------


async def test_lifespan_seeds_demo_mode_and_disposes_the_engine(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """The startup hook must create the schema, the demo users and the data."""
    from app.infrastructure import db as db_module
    from app.main import create_app, lifespan

    db_path = tmp_path_factory.mktemp("lifespan") / "life.db"
    demo_settings = Settings(
        environment="ci",
        demo_mode=True,
        database_url=f"sqlite+aiosqlite:///{db_path}",
        jwt_secret_key="lifespan-test-secret-long-enough-0123456789ab",
        rate_limit_enabled=False,
        log_format="console",
        log_level="WARNING",
    )
    application = create_app(demo_settings)

    async with lifespan(application):
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.adapters.persistence.repositories import (
            SqlAlchemyAnalyticsRepository,
            SqlAlchemyUserRepository,
        )

        factory = async_sessionmaker(db_module.get_engine(), expire_on_commit=False)
        async with factory() as db:
            assert await SqlAlchemyUserRepository(db).count() == 3
            summary = await SqlAlchemyAnalyticsRepository(db).summary()
            assert summary.total_students > 0
            assert summary.total_events > 0

    # The engine is released on shutdown.
    with pytest.raises(RuntimeError, match="not been initialised"):
        db_module.get_engine()


async def test_lifespan_without_demo_mode_creates_an_empty_schema(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.adapters.persistence.repositories import SqlAlchemyUserRepository
    from app.infrastructure import db as db_module
    from app.main import create_app, lifespan

    db_path = tmp_path_factory.mktemp("bare") / "bare.db"
    bare = Settings(
        environment="ci",
        demo_mode=False,
        database_url=f"sqlite+aiosqlite:///{db_path}",
        jwt_secret_key="bare-test-secret-long-enough-0123456789abcdef",
        rate_limit_enabled=False,
        log_format="console",
        log_level="WARNING",
    )
    application = create_app(bare)
    async with lifespan(application):
        factory = async_sessionmaker(db_module.get_engine(), expire_on_commit=False)
        async with factory() as db:
            assert await SqlAlchemyUserRepository(db).count() == 0
