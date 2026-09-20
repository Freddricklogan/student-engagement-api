"""Shared fixtures: in-memory database, app instance, authenticated clients."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure import db as db_module
from app.infrastructure.seed import create_schema, ensure_demo_users, seed_demo_data
from app.infrastructure.settings import Settings

TEST_SECRET = "test-secret-key-that-is-long-enough-for-validation-0123456789"


def _settings(tmp_path_factory: pytest.TempPathFactory, *, demo_mode: bool = False) -> Settings:
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    return Settings(
        environment="ci",
        demo_mode=demo_mode,
        database_url=f"sqlite+aiosqlite:///{db_path}",
        jwt_secret_key=TEST_SECRET,
        rate_limit_enabled=False,
        log_format="console",
        log_level="WARNING",
    )


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    os.environ.setdefault("PYTHONHASHSEED", "0")
    return _settings(tmp_path_factory)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def engine(settings: Settings) -> AsyncIterator[None]:
    """Fresh schema + deterministic demo dataset for every test."""
    eng = db_module.init_engine(settings)
    await create_schema(eng, reset=True)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(eng, expire_on_commit=False)
    async with factory() as session:
        await ensure_demo_users(session, settings)
        await seed_demo_data(session, seed=settings.demo_seed, student_count=12)
        await session.commit()
    yield
    await db_module.dispose_engine()


@pytest.fixture
async def client(engine: None, settings: Settings) -> AsyncIterator[AsyncClient]:
    """An httpx client bound to the ASGI app, with the engine already initialised.

    ``create_app`` is used directly rather than the module-level ``app`` so each
    test gets its own settings and its own database.
    """
    from app.main import create_app

    application = create_app(settings)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


async def _token(http: AsyncClient, username: str, password: str) -> str:
    response = await http.post(
        "/api/v1/auth/token", data={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    token: str = response.json()["access_token"]
    return token


@pytest.fixture
async def viewer_token(client: AsyncClient, settings: Settings) -> str:
    return await _token(client, settings.demo_viewer_username, settings.demo_viewer_password)


@pytest.fixture
async def analyst_token(client: AsyncClient, settings: Settings) -> str:
    return await _token(client, settings.demo_analyst_username, settings.demo_analyst_password)


@pytest.fixture
async def admin_token(client: AsyncClient, settings: Settings) -> str:
    return await _token(client, settings.demo_admin_username, settings.demo_admin_password)


@pytest.fixture
def viewer_headers(viewer_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {viewer_token}"}


@pytest.fixture
def analyst_headers(analyst_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {analyst_token}"}


@pytest.fixture
def admin_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}
