"""Legacy `/api/*` aliases.

Every path the Flask app exposed still resolves, with a byte-identical response
body, so the shipped dashboard and any existing client keep working unchanged.
Each alias is a *thin* delegate: it re-declares the route and calls the v1
handler directly, so there is exactly one implementation of every behaviour and
no chance of the two surfaces drifting apart.

Aliases are hidden from the OpenAPI schema (`include_in_schema=False`) so the
API reference presents one clean, versioned surface.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, status
from fastapi.responses import RedirectResponse

from app.adapters.api.deps import (
    AnalyticsServiceDep,
    EventServiceDep,
    RequireReader,
    RequireWriter,
    SessionServiceDep,
    StudentServiceDep,
)
from app.adapters.api.routers import analytics as v1_analytics
from app.adapters.api.routers import events as v1_events
from app.adapters.api.routers import sessions as v1_sessions
from app.adapters.api.routers import students as v1_students
from app.application.dto import (
    AnalyticsSummaryResponse,
    CourseAggregateResponse,
    EventCreate,
    EventListResponse,
    EventResponse,
    PageNumber,
    PageSize,
    SessionCreate,
    SessionListResponse,
    SessionResponse,
    StudentCreate,
    StudentListResponse,
    StudentRankingResponse,
    StudentResponse,
    TrendPointResponse,
)
from app.domain.entities import EventType, StudentStatus

router = APIRouter(prefix="/api", include_in_schema=False)


# --- students ------------------------------------------------------------------


@router.get("/students", response_model=StudentListResponse)
async def legacy_list_students(
    user: RequireReader,
    service: StudentServiceDep,
    major: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[StudentStatus | None, Query(alias="status")] = StudentStatus.ACTIVE,
    page: Annotated[PageNumber, Query()] = 1,
    per_page: Annotated[PageSize, Query(alias="per_page")] = 20,
) -> StudentListResponse:
    return await v1_students.list_students(
        user, service, major=major, status_filter=status_filter, page=page, per_page=per_page
    )


@router.get("/students/{student_id}", response_model=StudentResponse)
async def legacy_get_student(
    user: RequireReader,
    service: StudentServiceDep,
    student_id: Annotated[int, Path(ge=1)],
) -> StudentResponse:
    return await v1_students.get_student(user, service, student_id)


@router.post("/students", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
async def legacy_create_student(
    user: RequireWriter, service: StudentServiceDep, payload: StudentCreate
) -> StudentResponse:
    return await v1_students.create_student(user, service, payload)


# --- sessions --------------------------------------------------------------------


@router.get("/sessions", response_model=SessionListResponse)
async def legacy_list_sessions(
    user: RequireReader,
    service: SessionServiceDep,
    student_id: Annotated[int | None, Query(ge=1)] = None,
    course_id: Annotated[str | None, Query(max_length=20)] = None,
    page: Annotated[PageNumber, Query()] = 1,
    per_page: Annotated[PageSize, Query(alias="per_page")] = 20,
) -> SessionListResponse:
    return await v1_sessions.list_sessions(
        user, service, student_id=student_id, course_id=course_id, page=page, per_page=per_page
    )


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def legacy_create_session(
    user: RequireWriter, service: SessionServiceDep, payload: SessionCreate
) -> SessionResponse:
    return await v1_sessions.create_session(user, service, payload)


# --- events ------------------------------------------------------------------------


@router.get("/events", response_model=EventListResponse)
async def legacy_list_events(
    user: RequireReader,
    service: EventServiceDep,
    session_id: Annotated[int | None, Query(ge=1)] = None,
    event_type: Annotated[EventType | None, Query()] = None,
    page: Annotated[PageNumber, Query()] = 1,
    per_page: Annotated[PageSize, Query(alias="per_page")] = 50,
) -> EventListResponse:
    return await v1_events.list_events(
        user, service, session_id=session_id, event_type=event_type, page=page, per_page=per_page
    )


@router.post("/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def legacy_create_event(
    user: RequireWriter, service: EventServiceDep, payload: EventCreate
) -> EventResponse:
    return await v1_events.create_event(user, service, payload)


# --- analytics ---------------------------------------------------------------------


@router.get("/analytics/overview", response_model=AnalyticsSummaryResponse)
async def legacy_overview(
    user: RequireReader, service: AnalyticsServiceDep
) -> AnalyticsSummaryResponse:
    """Legacy name for `/api/v1/analytics/summary`."""
    return await v1_analytics.summary(user, service)


@router.get("/analytics/sessions-by-course", response_model=list[CourseAggregateResponse])
async def legacy_sessions_by_course(
    user: RequireReader, service: AnalyticsServiceDep
) -> list[CourseAggregateResponse]:
    return await v1_analytics.sessions_by_course(user, service)


@router.get("/analytics/engagement-trend", response_model=list[TrendPointResponse])
async def legacy_engagement_trend(
    user: RequireReader,
    service: AnalyticsServiceDep,
    days: Annotated[int, Query(ge=1, le=730)] = 365,
) -> list[TrendPointResponse]:
    return await v1_analytics.engagement_trend(user, service, days=days)


@router.get("/analytics/top-students", response_model=list[StudentRankingResponse])
async def legacy_top_students(
    user: RequireReader,
    service: AnalyticsServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[StudentRankingResponse]:
    return await v1_analytics.top_students(user, service, limit=limit)


# --- docs ----------------------------------------------------------------------------


@router.get("/docs")
async def legacy_docs() -> RedirectResponse:
    """The old hand-written YAML is gone; the generated reference lives at /docs."""
    return RedirectResponse(url="/docs", status_code=status.HTTP_308_PERMANENT_REDIRECT)
