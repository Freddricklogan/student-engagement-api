"""RFC 9457 problem+json shape, and X-Request-ID propagation."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

REQUIRED_MEMBERS = {"type", "title", "status", "detail", "instance", "request_id"}


async def _problem(client: AsyncClient, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    response = await client.request(method, path, **kwargs)
    assert response.headers["content-type"].startswith("application/problem+json")
    body: dict[str, Any] = response.json()
    assert set(body) >= REQUIRED_MEMBERS
    assert body["status"] == response.status_code
    assert body["instance"] == path.split("?")[0]
    assert body["type"].startswith("https://")
    return body


async def test_401_problem_shape(client: AsyncClient) -> None:
    body = await _problem(client, "GET", "/api/v1/analytics/summary")
    assert body["status"] == 401
    assert body["title"] == "Unauthorized"


async def test_403_problem_shape(client: AsyncClient, viewer_headers: dict[str, str]) -> None:
    body = await _problem(
        client,
        "POST",
        "/api/v1/students",
        json={
            "student_id": "STU77777",
            "first_name": "No",
            "last_name": "Write",
            "email": "no.write@example.edu",
        },
        headers=viewer_headers,
    )
    assert body["status"] == 403
    assert body["title"] == "Forbidden"


async def test_404_problem_shape(client: AsyncClient, viewer_headers: dict[str, str]) -> None:
    body = await _problem(client, "GET", "/api/v1/students/424242", headers=viewer_headers)
    assert body["status"] == 404


async def test_422_problem_carries_field_errors(
    client: AsyncClient, analyst_headers: dict[str, str]
) -> None:
    body = await _problem(client, "POST", "/api/v1/events", json={}, headers=analyst_headers)
    assert body["status"] == 422
    assert isinstance(body["errors"], list)
    assert body["errors"]
    for err in body["errors"]:
        assert {"field", "message", "type"} <= set(err)


async def test_405_problem_shape(client: AsyncClient) -> None:
    body = await _problem(client, "DELETE", "/api/v1/students")
    assert body["status"] == 405


async def test_unknown_route_is_a_problem_document(client: AsyncClient) -> None:
    body = await _problem(client, "GET", "/api/v1/no-such-thing")
    assert body["status"] == 404


async def test_409_problem_shape(client: AsyncClient, analyst_headers: dict[str, str]) -> None:
    payload = {
        "student_id": "STU31337",
        "first_name": "Con",
        "last_name": "Flict",
        "email": "con.flict@example.edu",
    }
    assert (
        await client.post("/api/v1/students", json=payload, headers=analyst_headers)
    ).status_code == 201
    body = await _problem(client, "POST", "/api/v1/students", json=payload, headers=analyst_headers)
    assert body["status"] == 409


# --- correlation id ------------------------------------------------------------


async def test_request_id_is_minted_when_absent(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    generated = response.headers["X-Request-ID"]
    uuid.UUID(generated)  # must parse as a UUID


async def test_client_supplied_request_id_is_echoed(client: AsyncClient) -> None:
    supplied = "trace-0123456789-abcdef"
    response = await client.get("/health", headers={"X-Request-ID": supplied})
    assert response.headers["X-Request-ID"] == supplied


async def test_request_id_appears_in_the_problem_body(client: AsyncClient) -> None:
    supplied = "corr-id-for-a-failing-call"
    response = await client.get("/api/v1/analytics/summary", headers={"X-Request-ID": supplied})
    assert response.status_code == 401
    assert response.json()["request_id"] == supplied
    assert response.headers["X-Request-ID"] == supplied


@pytest.mark.parametrize("supplied", ["", "short", "x" * 200])
async def test_implausible_request_ids_are_replaced(client: AsyncClient, supplied: str) -> None:
    """A too-short or absurdly long value is not echoed back verbatim."""
    response = await client.get("/health", headers={"X-Request-ID": supplied})
    returned = response.headers["X-Request-ID"]
    assert returned != supplied
    uuid.UUID(returned)


async def test_each_request_gets_a_distinct_id(client: AsyncClient) -> None:
    first = (await client.get("/health")).headers["X-Request-ID"]
    second = (await client.get("/health")).headers["X-Request-ID"]
    assert first != second


async def test_security_headers_are_present(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
