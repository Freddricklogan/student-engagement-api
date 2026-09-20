"""Domain entities and value objects.

These are framework-free: no SQLAlchemy, no FastAPI, no Pydantic. They describe
what the business talks about, and they are what the application layer reasons
over. The persistence and API adapters map to and from them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class Role(StrEnum):
    """Authorization roles, ordered least to most privileged."""

    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMIN = "admin"


#: Roles permitted to mutate data.
WRITE_ROLES: frozenset[Role] = frozenset({Role.ANALYST, Role.ADMIN})
#: Roles permitted to read data (every role).
READ_ROLES: frozenset[Role] = frozenset({Role.VIEWER, Role.ANALYST, Role.ADMIN})


class StudentStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    GRADUATED = "graduated"
    WITHDRAWN = "withdrawn"


class EventType(StrEnum):
    """Engagement event taxonomy. Weights live in the scoring service."""

    PAGE_VIEW = "page_view"
    VIDEO_WATCH = "video_watch"
    QUIZ_ATTEMPT = "quiz_attempt"
    DISCUSSION_POST = "discussion_post"
    ASSIGNMENT_SUBMIT = "assignment_submit"
    RESOURCE_DOWNLOAD = "resource_download"
    LAB_EXERCISE = "lab_exercise"
    PEER_REVIEW = "peer_review"


@dataclass(frozen=True, slots=True)
class User:
    id: int
    username: str
    role: Role
    is_active: bool


@dataclass(frozen=True, slots=True)
class Student:
    id: int
    student_id: str
    first_name: str
    last_name: str
    email: str
    major: str | None
    enrollment_date: date | None
    status: StudentStatus
    created_at: datetime

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


@dataclass(frozen=True, slots=True)
class LearningSession:
    id: int
    student_id: int
    course_id: str
    start_time: datetime
    end_time: datetime | None
    duration_minutes: float | None
    platform: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EngagementEvent:
    id: int
    session_id: int
    event_type: EventType
    event_data: dict[str, object] | None
    engagement_score: float
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class Page[T]:
    """A slice of a collection plus the totals needed to paginate it."""

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size


@dataclass(frozen=True, slots=True)
class AnalyticsSummary:
    total_students: int
    total_sessions: int
    total_events: int
    avg_session_duration: float
    avg_engagement_score: float


@dataclass(frozen=True, slots=True)
class CourseAggregate:
    course_id: str
    session_count: int
    avg_duration: float


@dataclass(frozen=True, slots=True)
class TrendPoint:
    date: str
    avg_score: float
    event_count: int


@dataclass(frozen=True, slots=True)
class StudentRanking:
    student_id: int
    name: str
    major: str | None
    avg_engagement_score: float
    session_count: int


@dataclass(frozen=True, slots=True)
class EngagementScore:
    """Output of the engagement scoring model for one student."""

    student_id: int
    score: float
    band: str
    event_count: int
    session_count: int
    components: dict[str, float]
