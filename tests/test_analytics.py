"""Analytics endpoints: the aggregates must equal what the raw rows say."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient


async def _all_events(client: AsyncClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    page = 1
    while True:
        response = await client.get(f"/api/v1/events?page={page}&per_page=100", headers=headers)
        assert response.status_code == 200
        body = response.json()
        events.extend(body["events"])
        if page >= body["pages"]:
            return events
        page += 1


async def _all_sessions(client: AsyncClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    page = 1
    while True:
        response = await client.get(f"/api/v1/sessions?page={page}&per_page=100", headers=headers)
        body = response.json()
        sessions.extend(body["sessions"])
        if page >= body["pages"]:
            return sessions
        page += 1


async def test_summary_totals_match_the_collections(
    client: AsyncClient, viewer_headers: dict[str, str]
) -> None:
    summary = (await client.get("/api/v1/analytics/summary", headers=viewer_headers)).json()
    students = (await client.get("/api/v1/students?per_page=100", headers=viewer_headers)).json()
    sessions = (await client.get("/api/v1/sessions?per_page=1", headers=viewer_headers)).json()
    events = (await client.get("/api/v1/events?per_page=1", headers=viewer_headers)).json()

    assert summary["total_students"] == students["total"]
    assert summary["total_sessions"] == sessions["total"]
    assert summary["total_events"] == events["total"]


async def test_summary_averages_match_a_python_recomputation(
    client: AsyncClient, viewer_headers: dict[str, str]
) -> None:
    summary = (await client.get("/api/v1/analytics/summary", headers=viewer_headers)).json()

    sessions = await _all_sessions(client, viewer_headers)
    durations = [
        float(s["duration_minutes"]) for s in sessions if s["duration_minutes"] is not None
    ]
    assert summary["avg_session_duration"] == round(sum(durations) / len(durations), 1)

    events = await _all_events(client, viewer_headers)
    scores = [float(e["engagement_score"]) for e in events]
    assert summary["avg_engagement_score"] == round(sum(scores) / len(scores), 2)


async def test_sessions_by_course_counts_sum_to_the_session_total(
    client: AsyncClient, viewer_headers: dict[str, str]
) -> None:
    by_course = (
        await client.get("/api/v1/analytics/sessions-by-course", headers=viewer_headers)
    ).json()
    summary = (await client.get("/api/v1/analytics/summary", headers=viewer_headers)).json()

    assert sum(row["session_count"] for row in by_course) == summary["total_sessions"]
    assert len({row["course_id"] for row in by_course}) == len(by_course)
    assert all(row["avg_duration"] >= 0 for row in by_course)


async def test_sessions_by_course_average_matches_recomputation(
    client: AsyncClient, viewer_headers: dict[str, str]
) -> None:
    by_course = (
        await client.get("/api/v1/analytics/sessions-by-course", headers=viewer_headers)
    ).json()
    sessions = await _all_sessions(client, viewer_headers)

    target = by_course[0]
    durations = [
        float(s["duration_minutes"])
        for s in sessions
        if s["course_id"] == target["course_id"] and s["duration_minutes"] is not None
    ]
    assert target["session_count"] == len(
        [s for s in sessions if s["course_id"] == target["course_id"]]
    )
    assert target["avg_duration"] == round(sum(durations) / len(durations), 1)


async def test_engagement_trend_event_counts_sum_within_the_window(
    client: AsyncClient, viewer_headers: dict[str, str]
) -> None:
    trend = (
        await client.get("/api/v1/analytics/engagement-trend?days=730", headers=viewer_headers)
    ).json()
    summary = (await client.get("/api/v1/analytics/summary", headers=viewer_headers)).json()

    assert sum(point["event_count"] for point in trend) == summary["total_events"]
    assert [p["date"] for p in trend] == sorted(p["date"] for p in trend)
    assert all(0.0 <= p["avg_score"] <= 1.0 for p in trend)


async def test_engagement_trend_window_is_honoured(
    client: AsyncClient, viewer_headers: dict[str, str]
) -> None:
    wide = (
        await client.get("/api/v1/analytics/engagement-trend?days=730", headers=viewer_headers)
    ).json()
    narrow = (
        await client.get("/api/v1/analytics/engagement-trend?days=30", headers=viewer_headers)
    ).json()
    assert len(narrow) <= len(wide)
    assert sum(p["event_count"] for p in narrow) <= sum(p["event_count"] for p in wide)


async def test_top_students_is_ordered_and_limited(
    client: AsyncClient, viewer_headers: dict[str, str]
) -> None:
    rows = (
        await client.get("/api/v1/analytics/top-students?limit=5", headers=viewer_headers)
    ).json()
    assert len(rows) == 5
    scores = [row["avg_engagement_score"] for row in rows]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert all(row["session_count"] >= 1 for row in rows)


async def test_top_students_average_matches_that_student_s_events(
    client: AsyncClient, viewer_headers: dict[str, str]
) -> None:
    top = (
        await client.get("/api/v1/analytics/top-students?limit=1", headers=viewer_headers)
    ).json()[0]

    sessions = await _all_sessions(client, viewer_headers)
    session_ids = {s["id"] for s in sessions if s["student_id"] == top["student_id"]}
    events = await _all_events(client, viewer_headers)
    scores = [float(e["engagement_score"]) for e in events if e["session_id"] in session_ids]

    assert top["session_count"] == len(session_ids)
    assert top["avg_engagement_score"] == round(sum(scores) / len(scores), 2)


async def test_top_students_limit_is_bounded(
    client: AsyncClient, viewer_headers: dict[str, str]
) -> None:
    assert (
        await client.get("/api/v1/analytics/top-students?limit=0", headers=viewer_headers)
    ).status_code == 422
    assert (
        await client.get("/api/v1/analytics/top-students?limit=500", headers=viewer_headers)
    ).status_code == 422


async def test_student_score_endpoint(client: AsyncClient, viewer_headers: dict[str, str]) -> None:
    response = await client.get("/api/v1/analytics/students/1/score", headers=viewer_headers)
    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["score"] <= 1.0
    assert body["band"] in {"high", "moderate", "at-risk", "disengaged"}
    assert set(body["components"]) == {"quality", "breadth", "recency"}
    assert body["event_count"] > 0


async def test_student_score_for_unknown_student_is_404(
    client: AsyncClient, viewer_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/analytics/students/999999/score", headers=viewer_headers)
    assert response.status_code == 404


async def test_a_new_event_moves_the_summary(
    client: AsyncClient, viewer_headers: dict[str, str], analyst_headers: dict[str, str]
) -> None:
    before = (await client.get("/api/v1/analytics/summary", headers=viewer_headers)).json()
    created = await client.post(
        "/api/v1/events",
        json={"session_id": 1, "event_type": "peer_review", "engagement_score": 1.0},
        headers=analyst_headers,
    )
    assert created.status_code == 201
    after = (await client.get("/api/v1/analytics/summary", headers=viewer_headers)).json()
    assert after["total_events"] == before["total_events"] + 1
