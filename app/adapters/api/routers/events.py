"""Engagement-event endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.adapters.api.deps import EventServiceDep, RequireReader, RequireWriter
from app.application.dto import (
    EventCreate,
    EventListResponse,
    EventResponse,
    PageNumber,
    PageSize,
    Problem,
)
from app.domain.entities import EngagementEvent, EventType

router = APIRouter(prefix="/events", tags=["events"])


def to_response(item: EngagementEvent) -> EventResponse:
    return EventResponse(
        id=item.id,
        session_id=item.session_id,
        event_type=item.event_type,
        event_data=dict(item.event_data) if item.event_data else None,
        engagement_score=item.engagement_score,
        timestamp=item.timestamp,
    )


@router.get(
    "",
    response_model=EventListResponse,
    summary="List engagement events",
    responses={401: {"model": Problem}, 403: {"model": Problem}},
)
async def list_events(
    _user: RequireReader,
    service: EventServiceDep,
    session_id: Annotated[int | None, Query(ge=1)] = None,
    event_type: Annotated[EventType | None, Query()] = None,
    page: Annotated[PageNumber, Query()] = 1,
    per_page: Annotated[PageSize, Query(alias="per_page")] = 50,
) -> EventListResponse:
    result = await service.list_events(
        session_pk=session_id, event_type=event_type, page=page, page_size=per_page
    )
    return EventListResponse(
        events=[to_response(e) for e in result.items],
        total=result.total,
        page=result.page,
        pages=result.pages,
    )


@router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an engagement event",
    responses={
        401: {"model": Problem},
        403: {"model": Problem},
        404: {"model": Problem, "description": "Unknown session_id"},
        422: {"model": Problem, "description": "Score outside [0,1] or unknown event_type"},
    },
)
async def create_event(
    _user: RequireWriter,
    service: EventServiceDep,
    payload: EventCreate,
) -> EventResponse:
    item = await service.create_event(
        session_pk=payload.session_id,
        event_type=payload.event_type,
        event_data=dict(payload.event_data) if payload.event_data else None,
        engagement_score=payload.engagement_score,
        timestamp=payload.timestamp,
    )
    return to_response(item)
