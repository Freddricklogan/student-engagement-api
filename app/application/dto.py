"""Pydantic v2 request/response models.

These are the wire contract. ORM rows are never serialized directly (the legacy
app used ``Model.to_dict()``, which coupled the schema to the JSON surface and
made an accidental field leak one column away).

Response field names are byte-for-byte identical to the legacy API so the
existing dashboard and any existing client keep working.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.domain.entities import EventType, Role, StudentStatus

# --- shared -------------------------------------------------------------------

PageNumber = Annotated[int, Field(ge=1, le=100_000)]
PageSize = Annotated[int, Field(ge=1, le=100)]


class Problem(BaseModel):
    """RFC 9457 problem detail. Every error response uses this shape."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "https://freddricklogan.github.io/student-engagement-api/problems/forbidden",
                "title": "Forbidden",
                "status": 403,
                "detail": "Role 'viewer' may not perform this action. Required: analyst, admin.",
                "instance": "/api/v1/students",
                "request_id": "6f1c2b0e-3f9a-4a6b-8a19-0d2f5f2f1c77",
            }
        }
    )

    type: str
    title: str
    status: int
    detail: str
    instance: str
    request_id: str
    errors: list[dict[str, Any]] | None = None


# --- auth ---------------------------------------------------------------------


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - an OAuth2 type, not a secret
    expires_in: int
    role: Role


class CurrentUserResponse(BaseModel):
    username: str
    role: Role


# --- students -------------------------------------------------------------------


class StudentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: Annotated[str, Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9._-]+$")]
    first_name: Annotated[str, Field(min_length=1, max_length=50)]
    last_name: Annotated[str, Field(min_length=1, max_length=50)]
    email: EmailStr
    major: Annotated[str, Field(max_length=100)] | None = None
    enrollment_date: date | None = None
    status: StudentStatus = StudentStatus.ACTIVE


class StudentResponse(BaseModel):
    id: int
    student_id: str
    first_name: str
    last_name: str
    email: str
    major: str | None
    enrollment_date: date | None
    status: StudentStatus
    created_at: datetime


class StudentListResponse(BaseModel):
    students: list[StudentResponse]
    total: int
    page: int
    pages: int


# --- sessions ---------------------------------------------------------------------


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: Annotated[int, Field(ge=1)]
    course_id: Annotated[str, Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9._-]+$")]
    start_time: datetime
    end_time: datetime | None = None
    platform: Annotated[str, Field(max_length=50)] | None = None

    @model_validator(mode="after")
    def _end_after_start(self) -> SessionCreate:
        if self.end_time is not None and self.end_time <= self.start_time:
            msg = "end_time must be after start_time"
            raise ValueError(msg)
        return self


class SessionResponse(BaseModel):
    id: int
    student_id: int
    course_id: str
    start_time: datetime
    end_time: datetime | None
    duration_minutes: float | None
    platform: str | None
    created_at: datetime


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
    total: int
    page: int
    pages: int


# --- events ------------------------------------------------------------------------


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: Annotated[int, Field(ge=1)]
    event_type: EventType
    event_data: dict[str, Any] | None = None
    engagement_score: Annotated[float, Field(ge=0.0, le=1.0)]
    timestamp: datetime | None = None

    @model_validator(mode="after")
    def _bound_payload(self) -> EventCreate:
        if self.event_data is not None and len(self.event_data) > 32:
            msg = "event_data may contain at most 32 keys"
            raise ValueError(msg)
        return self


class EventResponse(BaseModel):
    id: int
    session_id: int
    event_type: EventType
    event_data: dict[str, Any] | None
    engagement_score: float
    timestamp: datetime


class EventListResponse(BaseModel):
    events: list[EventResponse]
    total: int
    page: int
    pages: int


# --- analytics -----------------------------------------------------------------------


class AnalyticsSummaryResponse(BaseModel):
    total_students: int
    total_sessions: int
    total_events: int
    avg_session_duration: float
    avg_engagement_score: float


class CourseAggregateResponse(BaseModel):
    course_id: str
    session_count: int
    avg_duration: float


class TrendPointResponse(BaseModel):
    date: str
    avg_score: float
    event_count: int


class StudentRankingResponse(BaseModel):
    student_id: int
    name: str
    major: str | None
    avg_engagement_score: float
    session_count: int


class EngagementScoreResponse(BaseModel):
    student_id: int
    score: float
    band: str
    event_count: int
    session_count: int
    components: dict[str, float]


# --- health ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not-ready"]
    database: Literal["ok", "unavailable"]
