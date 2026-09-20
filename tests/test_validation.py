"""Input validation: every legacy crash-on-bad-input path now returns 422/404/409."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def test_missing_required_fields_is_422_not_500(
    client: AsyncClient, analyst_headers: dict[str, str]
) -> None:
    """The legacy handler indexed `data['course_id']` and raised KeyError -> 500."""
    response = await client.post(
        "/api/v1/sessions", json={"student_id": 1}, headers=analyst_headers
    )
    assert response.status_code == 422
    fields = {err["field"] for err in response.json()["errors"]}
    assert {"course_id", "start_time"} <= fields


async def test_malformed_datetime_is_422_not_500(
    client: AsyncClient, analyst_headers: dict[str, str]
) -> None:
    """`datetime.fromisoformat` on client input used to raise ValueError -> 500."""
    response = await client.post(
        "/api/v1/sessions",
        json={"student_id": 1, "course_id": "CS101", "start_time": "not-a-date"},
        headers=analyst_headers,
    )
    assert response.status_code == 422
    assert any(e["field"] == "start_time" for e in response.json()["errors"])


async def test_end_time_must_follow_start_time(
    client: AsyncClient, analyst_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/sessions",
        json={
            "student_id": 1,
            "course_id": "CS101",
            "start_time": "2026-01-05T11:00:00Z",
            "end_time": "2026-01-05T10:00:00Z",
        },
        headers=analyst_headers,
    )
    assert response.status_code == 422
    assert "end_time must be after start_time" in response.text


@pytest.mark.parametrize("score", [-0.1, 1.5, 42.0])
async def test_engagement_score_outside_zero_to_one_is_rejected(
    client: AsyncClient, analyst_headers: dict[str, str], score: float
) -> None:
    """Out-of-range scores used to be stored and then averaged into analytics."""
    response = await client.post(
        "/api/v1/events",
        json={"session_id": 1, "event_type": "quiz_attempt", "engagement_score": score},
        headers=analyst_headers,
    )
    assert response.status_code == 422


async def test_unknown_event_type_is_rejected(
    client: AsyncClient, analyst_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/events",
        json={"session_id": 1, "event_type": "definitely_not_real", "engagement_score": 0.5},
        headers=analyst_headers,
    )
    assert response.status_code == 422


async def test_unknown_parent_session_is_404(
    client: AsyncClient, analyst_headers: dict[str, str]
) -> None:
    """Legacy SQLite accepted orphan rows because the FK pragma was never set."""
    response = await client.post(
        "/api/v1/events",
        json={"session_id": 999_999, "event_type": "page_view", "engagement_score": 0.2},
        headers=analyst_headers,
    )
    assert response.status_code == 404
    assert "No session with id 999999" in response.json()["detail"]


async def test_unknown_parent_student_is_404(
    client: AsyncClient, analyst_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/sessions",
        json={
            "student_id": 999_999,
            "course_id": "CS101",
            "start_time": "2026-01-05T10:00:00Z",
        },
        headers=analyst_headers,
    )
    assert response.status_code == 404


async def test_duplicate_student_id_is_409(
    client: AsyncClient, analyst_headers: dict[str, str]
) -> None:
    payload = {
        "student_id": "STU54321",
        "first_name": "Dupe",
        "last_name": "Test",
        "email": "dupe.test@example.edu",
    }
    first = await client.post("/api/v1/students", json=payload, headers=analyst_headers)
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/students",
        json={**payload, "email": "different.email@example.edu"},
        headers=analyst_headers,
    )
    assert second.status_code == 409
    assert "student_id" in second.json()["detail"]


async def test_duplicate_email_is_409(client: AsyncClient, analyst_headers: dict[str, str]) -> None:
    payload = {
        "student_id": "STU54322",
        "first_name": "Dupe",
        "last_name": "Email",
        "email": "dupe.email@example.edu",
    }
    assert (
        await client.post("/api/v1/students", json=payload, headers=analyst_headers)
    ).status_code == 201
    second = await client.post(
        "/api/v1/students",
        json={**payload, "student_id": "STU54323"},
        headers=analyst_headers,
    )
    assert second.status_code == 409
    assert "email" in second.json()["detail"]


async def test_unknown_field_is_rejected(
    client: AsyncClient, analyst_headers: dict[str, str]
) -> None:
    """`extra="forbid"` stops a typo'd field from being silently dropped."""
    response = await client.post(
        "/api/v1/students",
        json={
            "student_id": "STU54324",
            "first_name": "Extra",
            "last_name": "Field",
            "email": "extra.field@example.edu",
            "is_admin": True,
        },
        headers=analyst_headers,
    )
    assert response.status_code == 422


async def test_invalid_email_is_rejected(
    client: AsyncClient, analyst_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/students",
        json={
            "student_id": "STU54325",
            "first_name": "Bad",
            "last_name": "Email",
            "email": "not-an-email",
        },
        headers=analyst_headers,
    )
    assert response.status_code == 422


@pytest.mark.parametrize("per_page", [0, 101, 1_000_000])
async def test_page_size_is_bounded(
    client: AsyncClient, viewer_headers: dict[str, str], per_page: int
) -> None:
    """`?per_page=1000000` used to materialize the whole table."""
    response = await client.get(f"/api/v1/students?per_page={per_page}", headers=viewer_headers)
    assert response.status_code == 422


async def test_page_number_must_be_positive(
    client: AsyncClient, viewer_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/students?page=0", headers=viewer_headers)
    assert response.status_code == 422


async def test_missing_student_is_404(client: AsyncClient, viewer_headers: dict[str, str]) -> None:
    response = await client.get("/api/v1/students/999999", headers=viewer_headers)
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_duration_is_derived_not_trusted(
    client: AsyncClient, analyst_headers: dict[str, str]
) -> None:
    """A client cannot claim a duration; it comes from the timestamps."""
    response = await client.post(
        "/api/v1/sessions",
        json={
            "student_id": 1,
            "course_id": "CS101",
            "start_time": "2026-01-05T10:00:00Z",
            "end_time": "2026-01-05T10:45:00Z",
            "duration_minutes": 9999,
        },
        headers=analyst_headers,
    )
    # duration_minutes is not an accepted input field at all.
    assert response.status_code == 422

    accepted = await client.post(
        "/api/v1/sessions",
        json={
            "student_id": 1,
            "course_id": "CS101",
            "start_time": "2026-01-05T10:00:00Z",
            "end_time": "2026-01-05T10:45:00Z",
        },
        headers=analyst_headers,
    )
    assert accepted.status_code == 201
    assert accepted.json()["duration_minutes"] == 45.0


async def test_event_data_key_count_is_bounded(
    client: AsyncClient, analyst_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/events",
        json={
            "session_id": 1,
            "event_type": "page_view",
            "engagement_score": 0.3,
            "event_data": {f"k{i}": i for i in range(40)},
        },
        headers=analyst_headers,
    )
    assert response.status_code == 422
