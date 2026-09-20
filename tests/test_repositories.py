"""Repository and infrastructure unit tests (filters, lookups, engine config)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.repositories import (
    SqlAlchemyAnalyticsRepository,
    SqlAlchemyEventRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyStudentRepository,
    SqlAlchemyUserRepository,
)
from app.domain.entities import EventType, Page, Student, StudentStatus
from app.infrastructure import db as db_module
from app.infrastructure.settings import Settings


@pytest.fixture
async def session(engine: None) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        db_module.get_engine(), expire_on_commit=False
    )
    async with factory() as db:
        yield db


async def test_lookup_by_student_id_and_email(session: AsyncSession) -> None:
    repo = SqlAlchemyStudentRepository(session)
    first = (await repo.list(major=None, status=None, page=1, page_size=1)).items[0]

    assert (await repo.get_by_student_id(first.student_id)) == first
    assert (await repo.get_by_email(first.email)) == first
    assert await repo.get_by_student_id("STU-DOES-NOT-EXIST") is None
    assert await repo.get_by_email("nobody@example.edu") is None
    assert await repo.get(999_999) is None


async def test_student_filters_narrow_the_result(session: AsyncSession) -> None:
    repo = SqlAlchemyStudentRepository(session)
    everyone = await repo.list(major=None, status=None, page=1, page_size=100)
    a_major = everyone.items[0].major
    assert a_major is not None

    filtered = await repo.list(major=a_major, status=None, page=1, page_size=100)
    assert 0 < filtered.total <= everyone.total
    assert all(s.major == a_major for s in filtered.items)

    graduated = await repo.list(major=None, status=StudentStatus.GRADUATED, page=1, page_size=100)
    assert graduated.total == 0
    assert graduated.items == []


async def test_session_filters(session: AsyncSession) -> None:
    repo = SqlAlchemySessionRepository(session)
    everything = await repo.list(student_pk=None, course_id=None, page=1, page_size=100)
    sample = everything.items[0]

    by_student = await repo.list(
        student_pk=sample.student_id, course_id=None, page=1, page_size=100
    )
    assert all(s.student_id == sample.student_id for s in by_student.items)

    by_course = await repo.list(student_pk=None, course_id=sample.course_id, page=1, page_size=100)
    assert all(s.course_id == sample.course_id for s in by_course.items)

    assert await repo.get(sample.id) == sample
    assert await repo.get(999_999) is None


async def test_event_filters_and_student_rollup(session: AsyncSession) -> None:
    events = SqlAlchemyEventRepository(session)
    by_type = await events.list(
        session_pk=None, event_type=EventType.PEER_REVIEW, page=1, page_size=50
    )
    assert all(e.event_type is EventType.PEER_REVIEW for e in by_type.items)

    first = (await events.list(session_pk=None, event_type=None, page=1, page_size=1)).items[0]
    by_session = await events.list(
        session_pk=first.session_id, event_type=None, page=1, page_size=100
    )
    assert all(e.session_id == first.session_id for e in by_session.items)

    for_student = await events.list_for_student(1)
    assert for_student
    assert [e.timestamp for e in for_student] == sorted(e.timestamp for e in for_student)


async def test_event_payload_round_trips_as_json(session: AsyncSession) -> None:
    events = SqlAlchemyEventRepository(session)
    created = await events.create(
        session_pk=1,
        event_type=EventType.LAB_EXERCISE,
        event_data={"nested": {"ok": True}, "n": 3},
        engagement_score=0.42,
        timestamp=(await events.list_for_student(1))[0].timestamp,
    )
    assert created.event_data == {"nested": {"ok": True}, "n": 3}

    plain = await events.create(
        session_pk=1,
        event_type=EventType.PAGE_VIEW,
        event_data=None,
        engagement_score=0.1,
        timestamp=created.timestamp,
    )
    assert plain.event_data is None


async def test_student_activity_rollup(session: AsyncSession) -> None:
    analytics = SqlAlchemyAnalyticsRepository(session)
    session_count, event_count, last_event = await analytics.student_activity(1)
    assert session_count > 0
    assert event_count > 0
    assert last_event is not None

    empty = await analytics.student_activity(999_999)
    assert empty == (0, 0, None)


async def test_user_repository_create_and_count(session: AsyncSession) -> None:
    users = SqlAlchemyUserRepository(session)
    before = await users.count()
    created = await users.create("temporary", "$2b$12$notarealhashbutastring", "analyst")
    assert created.username == "temporary"
    assert await users.count() == before + 1

    found = await users.get_by_username("temporary")
    assert found is not None
    assert found[0].role.value == "analyst"
    assert await users.get_by_username("absent") is None


# --- pure domain / infrastructure --------------------------------------------


def test_page_pages_rounds_up() -> None:
    page: Page[Student] = Page(items=[], total=21, page=1, page_size=20)
    assert page.pages == 2
    assert Page(items=[], total=0, page=1, page_size=20).pages == 0
    assert Page(items=[], total=5, page=1, page_size=0).pages == 0


def test_student_full_name() -> None:
    from datetime import UTC, datetime

    student = Student(
        id=1,
        student_id="STU1",
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.edu",
        major=None,
        enrollment_date=None,
        status=StudentStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )
    assert student.full_name == "Ada Lovelace"


def test_postgres_url_builds_a_pooled_engine() -> None:
    """Postgres readiness is a configuration change, not a code change."""
    settings = Settings(
        jwt_secret_key="x" * 40,
        database_url="postgresql+asyncpg://user:pass@db.internal:5432/engagement",
    )
    engine = db_module.create_engine(settings)
    assert engine.url.get_backend_name() == "postgresql"
    # Postgres gets a real pool; SQLite is forced to NullPool.
    assert "NullPool" not in type(engine.pool).__name__


def test_engine_accessors_fail_loudly_before_initialisation() -> None:
    saved_engine = db_module._engine
    saved_factory = db_module._sessionmaker
    db_module._engine = None
    db_module._sessionmaker = None
    try:
        with pytest.raises(RuntimeError, match="engine has not been initialised"):
            db_module.get_engine()
        with pytest.raises(RuntimeError, match="sessionmaker has not been initialised"):
            db_module.get_sessionmaker()
    finally:
        db_module._engine = saved_engine
        db_module._sessionmaker = saved_factory


def test_password_longer_than_bcrypts_limit_is_refused() -> None:
    from app.infrastructure.security import hash_password

    with pytest.raises(ValueError, match="at most 72 bytes"):
        hash_password("x" * 200)


# --- centralized 500 handling --------------------------------------------------


async def test_unhandled_exception_becomes_a_500_problem_document(
    engine: None, settings: Settings
) -> None:
    """A bug must not leak a traceback; it becomes a problem document with an id."""
    from app.main import create_app

    application = create_app(settings)

    @application.get("/boom", include_in_schema=False)
    async def boom() -> None:
        msg = "a deliberate failure with a secret in it"
        raise RuntimeError(msg)

    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        response = await http.get("/boom", headers={"X-Request-ID": "boom-correlation-id"})

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["request_id"] == "boom-correlation-id"
    assert "secret" not in body["detail"]
    assert "Traceback" not in response.text


# --- rate limiting -----------------------------------------------------------


async def test_token_endpoint_is_rate_limited(engine: None, settings: Settings) -> None:
    """The credential endpoint gets a tighter bucket than the rest of the API."""
    from app.adapters.api.ratelimit import configure_limiter, reset_limits
    from app.main import create_app

    limited = settings.model_copy(
        update={"rate_limit_enabled": True, "rate_limit_auth": "3/minute"}
    )
    application = create_app(limited)
    await reset_limits()
    transport = ASGITransport(app=application)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as http:
            statuses = [
                (
                    await http.post(
                        "/api/v1/auth/token",
                        data={"username": limited.demo_viewer_username, "password": "wrong"},
                    )
                ).status_code
                for _ in range(5)
            ]
            assert statuses[:3] == [401, 401, 401], statuses
            assert statuses[3:] == [429, 429], statuses

            final = await http.post(
                "/api/v1/auth/token",
                data={"username": limited.demo_viewer_username, "password": "wrong"},
            )
            assert final.status_code == 429
            assert final.headers["content-type"].startswith("application/problem+json")
            assert final.json()["title"] == "Too Many Requests"
            assert final.headers["Retry-After"] == "60"
    finally:
        configure_limiter(settings)
        await reset_limits()


async def test_rate_limit_is_skipped_when_disabled(client: AsyncClient, settings: Settings) -> None:
    """With limiting off, repeated bad logins are all 401 and never 429."""
    for _ in range(12):
        response = await client.post(
            "/api/v1/auth/token",
            data={"username": settings.demo_viewer_username, "password": "wrong"},
        )
        assert response.status_code == 401
