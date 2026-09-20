"""Application services (use cases).

Each service depends only on repository *ports* from ``app.domain.ports``, so it
can be exercised with fakes and carries no knowledge of HTTP or SQL. Business
rules that the legacy app either skipped or scattered through route handlers —
referential checks, duplicate detection, server-side duration derivation — live
here, in one place, once.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.application.scoring import score_student
from app.domain.entities import (
    AnalyticsSummary,
    CourseAggregate,
    EngagementEvent,
    EngagementScore,
    EventType,
    LearningSession,
    Page,
    Role,
    Student,
    StudentRanking,
    StudentStatus,
    TrendPoint,
    User,
)
from app.domain.errors import AuthenticationError, ConflictError, NotFoundError
from app.domain.ports import (
    AnalyticsRepository,
    EventRepository,
    SessionRepository,
    StudentRepository,
    UserRepository,
)
from app.infrastructure.security import create_access_token, verify_password
from app.infrastructure.settings import Settings


class AuthService:
    """OAuth2 password grant."""

    def __init__(self, users: UserRepository, settings: Settings) -> None:
        self._users = users
        self._settings = settings

    async def authenticate(self, username: str, password: str) -> tuple[User, str, int]:
        """Return ``(user, access_token, expires_in)`` or raise ``AuthenticationError``."""
        record = await self._users.get_by_username(username)
        if record is None:
            # Still hash-compare against a dummy value would be ideal; bcrypt's
            # cost dominates either way, and the generic message below avoids
            # confirming whether the username exists.
            raise AuthenticationError("Incorrect username or password.")
        user, password_hash = record
        if not verify_password(password, password_hash):
            raise AuthenticationError("Incorrect username or password.")
        if not user.is_active:
            raise AuthenticationError("This account is disabled.")
        token, expires_in = create_access_token(
            subject=user.username, role=user.role, settings=self._settings
        )
        return user, token, expires_in


class StudentService:
    def __init__(self, students: StudentRepository) -> None:
        self._students = students

    async def list_students(
        self,
        *,
        major: str | None,
        status: StudentStatus | None,
        page: int,
        page_size: int,
    ) -> Page[Student]:
        return await self._students.list(major=major, status=status, page=page, page_size=page_size)

    async def get_student(self, student_pk: int) -> Student:
        student = await self._students.get(student_pk)
        if student is None:
            raise NotFoundError(f"No student with id {student_pk}.")
        return student

    async def create_student(
        self,
        *,
        student_id: str,
        first_name: str,
        last_name: str,
        email: str,
        major: str | None,
        enrollment_date: date | None,
        status: StudentStatus,
    ) -> Student:
        if await self._students.get_by_student_id(student_id):
            raise ConflictError(f"A student with student_id '{student_id}' already exists.")
        if await self._students.get_by_email(email):
            raise ConflictError(f"A student with email '{email}' already exists.")
        return await self._students.create(
            student_id=student_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            major=major,
            enrollment_date=enrollment_date,
            status=status,
        )


class SessionService:
    def __init__(self, sessions: SessionRepository, students: StudentRepository) -> None:
        self._sessions = sessions
        self._students = students

    async def list_sessions(
        self,
        *,
        student_pk: int | None,
        course_id: str | None,
        page: int,
        page_size: int,
    ) -> Page[LearningSession]:
        return await self._sessions.list(
            student_pk=student_pk, course_id=course_id, page=page, page_size=page_size
        )

    async def create_session(
        self,
        *,
        student_pk: int,
        course_id: str,
        start_time: datetime,
        end_time: datetime | None,
        platform: str | None,
    ) -> LearningSession:
        if await self._students.get(student_pk) is None:
            raise NotFoundError(f"No student with id {student_pk}.")
        # Duration is derived, never trusted from the client: the legacy API let
        # a caller claim any duration and skew every aggregate downstream.
        duration: float | None = None
        if end_time is not None:
            duration = round((end_time - start_time).total_seconds() / 60.0, 1)
        return await self._sessions.create(
            student_pk=student_pk,
            course_id=course_id,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration,
            platform=platform,
        )


class EventService:
    def __init__(self, events: EventRepository, sessions: SessionRepository) -> None:
        self._events = events
        self._sessions = sessions

    async def list_events(
        self,
        *,
        session_pk: int | None,
        event_type: EventType | None,
        page: int,
        page_size: int,
    ) -> Page[EngagementEvent]:
        return await self._events.list(
            session_pk=session_pk, event_type=event_type, page=page, page_size=page_size
        )

    async def create_event(
        self,
        *,
        session_pk: int,
        event_type: EventType,
        event_data: dict[str, object] | None,
        engagement_score: float,
        timestamp: datetime | None,
    ) -> EngagementEvent:
        if await self._sessions.get(session_pk) is None:
            raise NotFoundError(f"No session with id {session_pk}.")
        return await self._events.create(
            session_pk=session_pk,
            event_type=event_type,
            event_data=event_data,
            engagement_score=engagement_score,
            timestamp=timestamp or datetime.now(UTC),
        )


class AnalyticsService:
    def __init__(
        self,
        analytics: AnalyticsRepository,
        students: StudentRepository,
        events: EventRepository,
    ) -> None:
        self._analytics = analytics
        self._students = students
        self._events = events

    async def summary(self) -> AnalyticsSummary:
        return await self._analytics.summary()

    async def sessions_by_course(self) -> list[CourseAggregate]:
        return await self._analytics.sessions_by_course()

    async def engagement_trend(self, *, days: int) -> list[TrendPoint]:
        return await self._analytics.engagement_trend(days=days)

    async def top_students(self, *, limit: int) -> list[StudentRanking]:
        return await self._analytics.top_students(limit=limit)

    async def student_score(self, student_pk: int) -> EngagementScore:
        if await self._students.get(student_pk) is None:
            raise NotFoundError(f"No student with id {student_pk}.")
        events = await self._events.list_for_student(student_pk)
        session_count, _, _ = await self._analytics.student_activity(student_pk)
        return score_student(student_pk, events, session_count=session_count)


__all__ = [
    "AnalyticsService",
    "AuthService",
    "EventService",
    "Role",
    "SessionService",
    "StudentService",
]
