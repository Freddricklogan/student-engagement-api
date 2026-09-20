"""SQLAlchemy implementations of the domain repository ports.

Every method returns domain entities, never ORM rows, so the application layer
never accidentally triggers lazy loading or leaks the schema to the API layer.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.models import (
    EngagementEventRow,
    LearningSessionRow,
    StudentRow,
    UserRow,
)
from app.domain.entities import (
    AnalyticsSummary,
    CourseAggregate,
    EngagementEvent,
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


def _as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; normalise everything to aware UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _to_student(row: StudentRow) -> Student:
    return Student(
        id=row.id,
        student_id=row.student_id,
        first_name=row.first_name,
        last_name=row.last_name,
        email=row.email,
        major=row.major,
        enrollment_date=row.enrollment_date,
        status=StudentStatus(row.status),
        created_at=_as_utc(row.created_at),
    )


def _to_session(row: LearningSessionRow) -> LearningSession:
    return LearningSession(
        id=row.id,
        student_id=row.student_id,
        course_id=row.course_id,
        start_time=_as_utc(row.start_time),
        end_time=_as_utc(row.end_time) if row.end_time else None,
        duration_minutes=row.duration_minutes,
        platform=row.platform,
        created_at=_as_utc(row.created_at),
    )


def _to_event(row: EngagementEventRow) -> EngagementEvent:
    payload: dict[str, object] | None = None
    if row.event_data:
        try:
            decoded = json.loads(row.event_data)
            payload = decoded if isinstance(decoded, dict) else {"value": decoded}
        except json.JSONDecodeError:  # pragma: no cover - legacy rows only
            payload = {"raw": row.event_data}
    return EngagementEvent(
        id=row.id,
        session_id=row.session_id,
        event_type=EventType(row.event_type),
        event_data=payload,
        engagement_score=row.engagement_score,
        timestamp=_as_utc(row.timestamp),
    )


class SqlAlchemyUserRepository:
    """User lookup and creation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_username(self, username: str) -> tuple[User, str] | None:
        row = (
            await self._session.execute(select(UserRow).where(UserRow.username == username))
        ).scalar_one_or_none()
        if row is None:
            return None
        user = User(id=row.id, username=row.username, role=Role(row.role), is_active=row.is_active)
        return user, row.password_hash

    async def create(self, username: str, password_hash: str, role: str) -> User:
        row = UserRow(username=username, password_hash=password_hash, role=role)
        self._session.add(row)
        await self._session.flush()
        return User(id=row.id, username=row.username, role=Role(row.role), is_active=row.is_active)

    async def count(self) -> int:
        total = (await self._session.execute(select(func.count()).select_from(UserRow))).scalar()
        return int(total or 0)


class _PagingMixin:
    _session: AsyncSession

    async def _paginate[T](
        self,
        stmt: Select[Any],
        mapper: Any,
        page: int,
        page_size: int,
    ) -> Page[T]:
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int((await self._session.execute(count_stmt)).scalar() or 0)
        rows = (
            (await self._session.execute(stmt.limit(page_size).offset((page - 1) * page_size)))
            .scalars()
            .all()
        )
        items: list[T] = [mapper(row) for row in rows]
        return Page(items=items, total=total, page=page, page_size=page_size)


class SqlAlchemyStudentRepository(_PagingMixin):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        major: str | None,
        status: StudentStatus | None,
        page: int,
        page_size: int,
    ) -> Page[Student]:
        stmt = select(StudentRow)
        if major:
            stmt = stmt.where(StudentRow.major == major)
        if status:
            stmt = stmt.where(StudentRow.status == status.value)
        stmt = stmt.order_by(StudentRow.id)
        return await self._paginate(stmt, _to_student, page, page_size)

    async def get(self, student_pk: int) -> Student | None:
        row = await self._session.get(StudentRow, student_pk)
        return _to_student(row) if row else None

    async def get_by_student_id(self, student_id: str) -> Student | None:
        row = (
            await self._session.execute(
                select(StudentRow).where(StudentRow.student_id == student_id)
            )
        ).scalar_one_or_none()
        return _to_student(row) if row else None

    async def get_by_email(self, email: str) -> Student | None:
        row = (
            await self._session.execute(select(StudentRow).where(StudentRow.email == email))
        ).scalar_one_or_none()
        return _to_student(row) if row else None

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
    ) -> Student:
        row = StudentRow(
            student_id=student_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            major=major,
            enrollment_date=enrollment_date,
            status=status.value,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_student(row)


class SqlAlchemySessionRepository(_PagingMixin):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        student_pk: int | None,
        course_id: str | None,
        page: int,
        page_size: int,
    ) -> Page[LearningSession]:
        stmt = select(LearningSessionRow)
        if student_pk is not None:
            stmt = stmt.where(LearningSessionRow.student_id == student_pk)
        if course_id:
            stmt = stmt.where(LearningSessionRow.course_id == course_id)
        stmt = stmt.order_by(LearningSessionRow.start_time.desc(), LearningSessionRow.id.desc())
        return await self._paginate(stmt, _to_session, page, page_size)

    async def get(self, session_pk: int) -> LearningSession | None:
        row = await self._session.get(LearningSessionRow, session_pk)
        return _to_session(row) if row else None

    async def create(
        self,
        *,
        student_pk: int,
        course_id: str,
        start_time: datetime,
        end_time: datetime | None,
        duration_minutes: float | None,
        platform: str | None,
    ) -> LearningSession:
        row = LearningSessionRow(
            student_id=student_pk,
            course_id=course_id,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes,
            platform=platform,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_session(row)


class SqlAlchemyEventRepository(_PagingMixin):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        session_pk: int | None,
        event_type: EventType | None,
        page: int,
        page_size: int,
    ) -> Page[EngagementEvent]:
        stmt = select(EngagementEventRow)
        if session_pk is not None:
            stmt = stmt.where(EngagementEventRow.session_id == session_pk)
        if event_type is not None:
            stmt = stmt.where(EngagementEventRow.event_type == event_type.value)
        stmt = stmt.order_by(EngagementEventRow.timestamp.desc(), EngagementEventRow.id.desc())
        return await self._paginate(stmt, _to_event, page, page_size)

    async def create(
        self,
        *,
        session_pk: int,
        event_type: EventType,
        event_data: dict[str, object] | None,
        engagement_score: float,
        timestamp: datetime,
    ) -> EngagementEvent:
        row = EngagementEventRow(
            session_id=session_pk,
            event_type=event_type.value,
            event_data=json.dumps(event_data) if event_data is not None else None,
            engagement_score=engagement_score,
            timestamp=timestamp,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_event(row)

    async def list_for_student(self, student_pk: int) -> Sequence[EngagementEvent]:
        stmt = (
            select(EngagementEventRow)
            .join(LearningSessionRow, EngagementEventRow.session_id == LearningSessionRow.id)
            .where(LearningSessionRow.student_id == student_pk)
            .order_by(EngagementEventRow.timestamp)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_event(row) for row in rows]


class SqlAlchemyAnalyticsRepository:
    """Aggregations. Every number is computed in SQL, never in Python loops."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def summary(self) -> AnalyticsSummary:
        total_students = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(StudentRow)
                    .where(StudentRow.status == StudentStatus.ACTIVE.value)
                )
            ).scalar()
            or 0
        )
        total_sessions = int(
            (
                await self._session.execute(select(func.count()).select_from(LearningSessionRow))
            ).scalar()
            or 0
        )
        total_events = int(
            (
                await self._session.execute(select(func.count()).select_from(EngagementEventRow))
            ).scalar()
            or 0
        )
        avg_duration = (
            await self._session.execute(select(func.avg(LearningSessionRow.duration_minutes)))
        ).scalar()
        avg_score = (
            await self._session.execute(select(func.avg(EngagementEventRow.engagement_score)))
        ).scalar()

        return AnalyticsSummary(
            total_students=total_students,
            total_sessions=total_sessions,
            total_events=total_events,
            avg_session_duration=round(float(avg_duration or 0.0), 1),
            avg_engagement_score=round(float(avg_score or 0.0), 2),
        )

    async def sessions_by_course(self) -> list[CourseAggregate]:
        stmt = (
            select(
                LearningSessionRow.course_id,
                func.count(LearningSessionRow.id).label("session_count"),
                func.avg(LearningSessionRow.duration_minutes).label("avg_duration"),
            )
            .group_by(LearningSessionRow.course_id)
            .order_by(LearningSessionRow.course_id)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            CourseAggregate(
                course_id=row.course_id,
                session_count=int(row.session_count),
                avg_duration=round(float(row.avg_duration or 0.0), 1),
            )
            for row in rows
        ]

    async def engagement_trend(self, *, days: int) -> list[TrendPoint]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        # ``func.date`` is rendered per dialect by SQLAlchemy; the cutoff keeps
        # the scan bounded rather than reading all history like the legacy query.
        day = func.date(EngagementEventRow.timestamp).label("day")
        stmt = (
            select(
                day,
                func.avg(EngagementEventRow.engagement_score).label("avg_score"),
                func.count(EngagementEventRow.id).label("event_count"),
            )
            .where(EngagementEventRow.timestamp >= cutoff)
            .group_by(day)
            .order_by(day)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            TrendPoint(
                date=str(row.day),
                avg_score=round(float(row.avg_score or 0.0), 2),
                event_count=int(row.event_count),
            )
            for row in rows
        ]

    async def top_students(self, *, limit: int) -> list[StudentRanking]:
        avg_score = func.avg(EngagementEventRow.engagement_score).label("avg_score")
        stmt = (
            select(
                StudentRow.id,
                StudentRow.first_name,
                StudentRow.last_name,
                StudentRow.major,
                avg_score,
                func.count(func.distinct(LearningSessionRow.id)).label("session_count"),
            )
            .join(LearningSessionRow, StudentRow.id == LearningSessionRow.student_id)
            .join(EngagementEventRow, LearningSessionRow.id == EngagementEventRow.session_id)
            # Every non-aggregated column is grouped: the legacy query grouped on
            # id alone, which Postgres rejects outright.
            .group_by(StudentRow.id, StudentRow.first_name, StudentRow.last_name, StudentRow.major)
            .order_by(avg_score.desc(), StudentRow.id)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            StudentRanking(
                student_id=row.id,
                name=f"{row.first_name} {row.last_name}",
                major=row.major,
                avg_engagement_score=round(float(row.avg_score or 0.0), 2),
                session_count=int(row.session_count),
            )
            for row in rows
        ]

    async def student_activity(self, student_pk: int) -> tuple[int, int, datetime | None]:
        session_count = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(LearningSessionRow)
                    .where(LearningSessionRow.student_id == student_pk)
                )
            ).scalar()
            or 0
        )
        stmt = (
            select(
                func.count(EngagementEventRow.id),
                func.max(EngagementEventRow.timestamp),
            )
            .join(LearningSessionRow, EngagementEventRow.session_id == LearningSessionRow.id)
            .where(LearningSessionRow.student_id == student_pk)
        )
        event_count, last_event = (await self._session.execute(stmt)).one()
        last: datetime | None = None
        if isinstance(last_event, datetime):
            last = _as_utc(last_event)
        elif isinstance(last_event, str):  # pragma: no cover - dialect dependent
            last = _as_utc(datetime.fromisoformat(last_event))
        return session_count, int(event_count or 0), last
