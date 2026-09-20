"""Role-based access control: every denial path, on every write endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

WRITE_REQUESTS: tuple[tuple[str, dict[str, object]], ...] = (
    (
        "/api/v1/students",
        {
            "student_id": "STU99999",
            "first_name": "Rejected",
            "last_name": "Writer",
            "email": "rejected.writer@example.edu",
        },
    ),
    (
        "/api/v1/sessions",
        {
            "student_id": 1,
            "course_id": "CS101",
            "start_time": "2026-01-05T10:00:00Z",
            "end_time": "2026-01-05T11:00:00Z",
        },
    ),
    (
        "/api/v1/events",
        {"session_id": 1, "event_type": "quiz_attempt", "engagement_score": 0.5},
    ),
)


@pytest.mark.parametrize(("path", "payload"), WRITE_REQUESTS)
async def test_viewer_cannot_write(
    client: AsyncClient, viewer_headers: dict[str, str], path: str, payload: dict[str, object]
) -> None:
    response = await client.post(path, json=payload, headers=viewer_headers)
    assert response.status_code == 403
    body = response.json()
    assert body["title"] == "Forbidden"
    assert "viewer" in body["detail"]
    assert "analyst" in body["detail"] and "admin" in body["detail"]


@pytest.mark.parametrize(("path", "payload"), WRITE_REQUESTS)
async def test_unauthenticated_write_is_401_not_403(
    client: AsyncClient, path: str, payload: dict[str, object]
) -> None:
    """Authentication is checked before authorization, so anonymous gets 401."""
    response = await client.post(path, json=payload)
    assert response.status_code == 401


async def test_analyst_can_write(client: AsyncClient, analyst_headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v1/students",
        json={
            "student_id": "STU00001",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada.lovelace@example.edu",
            "major": "Computer Science",
        },
        headers=analyst_headers,
    )
    assert response.status_code == 201
    assert response.json()["student_id"] == "STU00001"


async def test_admin_can_write(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v1/students",
        json={
            "student_id": "STU00002",
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": "grace.hopper@example.edu",
        },
        headers=admin_headers,
    )
    assert response.status_code == 201


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/students",
        "/api/v1/sessions",
        "/api/v1/events",
        "/api/v1/analytics/summary",
        "/api/v1/analytics/sessions-by-course",
        "/api/v1/analytics/engagement-trend",
        "/api/v1/analytics/top-students",
    ],
)
async def test_viewer_can_read_everything(
    client: AsyncClient, viewer_headers: dict[str, str], path: str
) -> None:
    response = await client.get(path, headers=viewer_headers)
    assert response.status_code == 200


async def test_legacy_alias_enforces_the_same_rbac(
    client: AsyncClient, viewer_headers: dict[str, str]
) -> None:
    """The compatibility surface must not be a privilege back door."""
    response = await client.post(
        "/api/students",
        json={
            "student_id": "STU12121",
            "first_name": "Back",
            "last_name": "Door",
            "email": "back.door@example.edu",
        },
        headers=viewer_headers,
    )
    assert response.status_code == 403
