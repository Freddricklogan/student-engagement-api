"""Authentication: token issue, claim verification, rejection paths."""

from __future__ import annotations

from datetime import timedelta

import jwt
import pytest
from httpx import AsyncClient

from app.domain.entities import Role
from app.domain.errors import AuthenticationError
from app.infrastructure.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.infrastructure.settings import Settings


async def test_token_issued_for_valid_credentials(client: AsyncClient, settings: Settings) -> None:
    response = await client.post(
        "/api/v1/auth/token",
        data={
            "username": settings.demo_viewer_username,
            "password": settings.demo_viewer_password,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "viewer"
    assert body["expires_in"] == settings.access_token_expire_minutes * 60


async def test_wrong_password_is_rejected(client: AsyncClient, settings: Settings) -> None:
    response = await client.post(
        "/api/v1/auth/token",
        data={"username": settings.demo_viewer_username, "password": "not-the-password"},
    )
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == "Incorrect username or password."


async def test_unknown_user_gives_the_same_message(client: AsyncClient, settings: Settings) -> None:
    """No user enumeration: unknown username and wrong password read identically."""
    response = await client.post(
        "/api/v1/auth/token",
        data={"username": "no-such-user", "password": settings.demo_viewer_password},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password."


async def test_protected_route_requires_a_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/analytics/summary")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_garbage_token_is_rejected(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/analytics/summary", headers={"Authorization": "Bearer not.a.jwt"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Access token is invalid."


async def test_token_signed_with_another_key_is_rejected(client: AsyncClient) -> None:
    forged = jwt.encode(
        {
            "sub": "mallory",
            "role": "admin",
            "iat": 0,
            "exp": 9_999_999_999,
            "iss": "student-engagement-api",
            "aud": "student-engagement-clients",
        },
        "a-different-secret-entirely-0123456789abcdef",
        algorithm="HS256",
    )
    response = await client.get(
        "/api/v1/analytics/summary", headers={"Authorization": f"Bearer {forged}"}
    )
    assert response.status_code == 401


async def test_expired_token_is_rejected(settings: Settings) -> None:
    token, _ = create_access_token(
        subject="demo",
        role=Role.VIEWER,
        settings=settings,
        expires_delta=timedelta(seconds=-10),
    )
    with pytest.raises(AuthenticationError, match="expired"):
        decode_access_token(token, settings)


async def test_token_with_unknown_role_is_rejected(settings: Settings) -> None:
    token = jwt.encode(
        {
            "sub": "demo",
            "role": "superuser",
            "iat": 0,
            "exp": 9_999_999_999,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(AuthenticationError, match="required claims"):
        decode_access_token(token, settings)


async def test_whoami_reports_identity_and_role(
    client: AsyncClient, viewer_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/auth/me", headers=viewer_headers)
    assert response.status_code == 200
    assert response.json() == {"username": "demo", "role": "viewer"}


def test_password_hashing_round_trip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_password_survives_a_malformed_hash() -> None:
    assert not verify_password("anything", "not-a-bcrypt-hash")


async def test_query_string_credentials_are_not_accepted(client: AsyncClient) -> None:
    """The legacy API accepted `?api_key=`. That path must be gone."""
    response = await client.get("/api/v1/analytics/summary?api_key=dev-api-key-2026")
    assert response.status_code == 401
