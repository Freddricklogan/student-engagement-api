"""Learning-session endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.adapters.api.deps import RequireReader, RequireWriter, SessionServiceDep
from app.application.dto import (
    PageNumber,
    PageSize,
    Problem,
    SessionCreate,
    SessionListResponse,
    SessionResponse,
)
from app.domain.entities import LearningSession

router = APIRouter(prefix="/sessions", tags=["sessions"])


def to_response(item: LearningSession) -> SessionResponse:
    return SessionResponse(
        id=item.id,
        student_id=item.student_id,
        course_id=item.course_id,
        start_time=item.start_time,
        end_time=item.end_time,
        duration_minutes=item.duration_minutes,
        platform=item.platform,
        created_at=item.created_at,
    )


@router.get(
    "",
    response_model=SessionListResponse,
    summary="List learning sessions",
    responses={401: {"model": Problem}, 403: {"model": Problem}},
)
async def list_sessions(
    _user: RequireReader,
    service: SessionServiceDep,
    student_id: Annotated[int | None, Query(ge=1)] = None,
    course_id: Annotated[str | None, Query(max_length=20)] = None,
    page: Annotated[PageNumber, Query()] = 1,
    per_page: Annotated[PageSize, Query(alias="per_page")] = 20,
) -> SessionListResponse:
    result = await service.list_sessions(
        student_pk=student_id, course_id=course_id, page=page, page_size=per_page
    )
    return SessionListResponse(
        sessions=[to_response(s) for s in result.items],
        total=result.total,
        page=result.page,
        pages=result.pages,
    )


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a learning session",
    responses={
        401: {"model": Problem},
        403: {"model": Problem},
        404: {"model": Problem, "description": "Unknown student_id"},
        422: {"model": Problem},
    },
)
async def create_session(
    _user: RequireWriter,
    service: SessionServiceDep,
    payload: SessionCreate,
) -> SessionResponse:
    """`duration_minutes` is derived from the timestamps, never taken from the client."""
    item = await service.create_session(
        student_pk=payload.student_id,
        course_id=payload.course_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        platform=payload.platform,
    )
    return to_response(item)
