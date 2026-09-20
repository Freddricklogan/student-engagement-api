"""Repository ports.

The application layer depends on these Protocols, never on SQLAlchemy. The
concrete implementations live in ``app.adapters.persistence.repositories``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Protocol

from app.domain.entities import (
    AnalyticsSummary,
    CourseAggregate,
    EngagementEvent,
    EventType,
    LearningSession,
    Page,
    Student,
    StudentRanking,
    StudentStatus,
    TrendPoint,
    User,
)


class UserRepository(Protocol):
    async def get_by_username(self, username: str) -> tuple[User, str] | None:
        """Return the user and their password hash, or ``None``."""
        ...

    async def create(self, username: str, password_hash: str, role: str) -> User: ...

    async def count(self) -> int: ...


class StudentRepository(Protocol):
    async def list(
        self,
        *,
        major: str | None,
        status: StudentStatus | None,
        page: int,
        page_size: int,
    ) -> Page[Student]: ...

    async def get(self, student_pk: int) -> Student | None: ...

    async def get_by_student_id(self, student_id: str) -> Student | None: ...

    async def get_by_email(self, email: str) -> Student | None: ...

    async def create(
        self,
        *,
        student_id: str,
        first_name: str,
        last_name: str,
        email: str,
        major: str | None,
        enrollment_date: date | None,
        status: StudentStatus,
    ) -> Student: ...


class SessionRepository(Protocol):
    async def list(
        self,
        *,
        student_pk: int | None,
        course_id: str | None,
        page: int,
        page_size: int,
    ) -> Page[LearningSession]: ...

    async def get(self, session_pk: int) -> LearningSession | None: ...

    async def create(
        self,
        *,
        student_pk: int,
        course_id: str,
        start_time: datetime,
        end_time: datetime | None,
        duration_minutes: float | None,
        platform: str | None,
    ) -> LearningSession: ...


class EventRepository(Protocol):
    async def list(
        self,
        *,
        session_pk: int | None,
        event_type: EventType | None,
        page: int,
        page_size: int,
    ) -> Page[EngagementEvent]: ...

    async def create(
        self,
        *,
        session_pk: int,
        event_type: EventType,
        event_data: dict[str, object] | None,
        engagement_score: float,
        timestamp: datetime,
    ) -> EngagementEvent: ...

    async def list_for_student(self, student_pk: int) -> Sequence[EngagementEvent]: ...


class AnalyticsRepository(Protocol):
    async def summary(self) -> AnalyticsSummary: ...

    async def sessions_by_course(self) -> list[CourseAggregate]: ...

    async def engagement_trend(self, *, days: int) -> list[TrendPoint]: ...

    async def top_students(self, *, limit: int) -> list[StudentRanking]: ...

    async def student_activity(self, student_pk: int) -> tuple[int, int, datetime | None]:
        """Return ``(session_count, event_count, last_event_at)`` for a student."""
        ...
