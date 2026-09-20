"""Analytics endpoints.

`/analytics/summary` is the canonical name for what the legacy API called
`/api/analytics/overview`; the old path survives as an alias (see `legacy.py`)
and returns an identical body.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.adapters.api.deps import AnalyticsServiceDep, RequireReader
from app.application.dto import (
    AnalyticsSummaryResponse,
    CourseAggregateResponse,
    EngagementScoreResponse,
    Problem,
    StudentRankingResponse,
    TrendPointResponse,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])

_AUTH_RESPONSES: dict[int | str, dict[str, object]] = {
    401: {"model": Problem},
    403: {"model": Problem},
}


@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
    summary="Headline engagement metrics",
    responses=_AUTH_RESPONSES,
)
async def summary(_user: RequireReader, service: AnalyticsServiceDep) -> AnalyticsSummaryResponse:
    """Active students, total sessions and events, mean duration and mean score."""
    result = await service.summary()
    return AnalyticsSummaryResponse(
        total_students=result.total_students,
        total_sessions=result.total_sessions,
        total_events=result.total_events,
        avg_session_duration=result.avg_session_duration,
        avg_engagement_score=result.avg_engagement_score,
    )


@router.get(
    "/sessions-by-course",
    response_model=list[CourseAggregateResponse],
    summary="Session count and mean duration per course",
    responses=_AUTH_RESPONSES,
)
async def sessions_by_course(
    _user: RequireReader, service: AnalyticsServiceDep
) -> list[CourseAggregateResponse]:
    return [
        CourseAggregateResponse(
            course_id=row.course_id,
            session_count=row.session_count,
            avg_duration=row.avg_duration,
        )
        for row in await service.sessions_by_course()
    ]


@router.get(
    "/engagement-trend",
    response_model=list[TrendPointResponse],
    summary="Daily mean engagement score",
    responses=_AUTH_RESPONSES,
)
async def engagement_trend(
    _user: RequireReader,
    service: AnalyticsServiceDep,
    days: Annotated[int, Query(ge=1, le=730)] = 365,
) -> list[TrendPointResponse]:
    """Bounded to a window so the scan cannot grow without limit."""
    return [
        TrendPointResponse(date=row.date, avg_score=row.avg_score, event_count=row.event_count)
        for row in await service.engagement_trend(days=days)
    ]


@router.get(
    "/top-students",
    response_model=list[StudentRankingResponse],
    summary="Students ranked by mean event score",
    responses=_AUTH_RESPONSES,
)
async def top_students(
    _user: RequireReader,
    service: AnalyticsServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[StudentRankingResponse]:
    return [
        StudentRankingResponse(
            student_id=row.student_id,
            name=row.name,
            major=row.major,
            avg_engagement_score=row.avg_engagement_score,
            session_count=row.session_count,
        )
        for row in await service.top_students(limit=limit)
    ]


@router.get(
    "/students/{student_id}/score",
    response_model=EngagementScoreResponse,
    summary="Composite engagement score for one student",
    responses={**_AUTH_RESPONSES, 404: {"model": Problem}},
)
async def student_score(
    _user: RequireReader,
    service: AnalyticsServiceDep,
    student_id: Annotated[int, Path(ge=1)],
) -> EngagementScoreResponse:
    """Blends event quality (60%), participation breadth (20%) and recency (20%)."""
    result = await service.student_score(student_id)
    return EngagementScoreResponse(
        student_id=result.student_id,
        score=result.score,
        band=result.band,
        event_count=result.event_count,
        session_count=result.session_count,
        components=result.components,
    )
