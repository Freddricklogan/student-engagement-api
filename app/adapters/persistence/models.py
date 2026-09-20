"""SQLAlchemy 2.0 typed ORM models.

Differences from the legacy Flask-SQLAlchemy models, all deliberate:

* ``Mapped[...]`` annotations everywhere, so ``mypy --strict`` sees the schema.
* Timezone-aware UTC timestamps (legacy used naive ``datetime.utcnow``).
* Explicit indexes on every column that is filtered, grouped or ordered on.
* ``lazy="raise"`` relationships so an accidental lazy load fails loudly
  instead of silently becoming an N+1.
* ``Session`` renamed ``LearningSession`` to stop shadowing SQLAlchemy's own
  ``Session``; the table name and JSON field names are unchanged.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


def utcnow() -> datetime:
    """Timezone-aware current time (``datetime.utcnow`` is deprecated in 3.12)."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("role IN ('viewer','analyst','admin')", name="ck_users_role"),
    )


class StudentRow(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    major: Mapped[str | None] = mapped_column(String(100), index=True)
    enrollment_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    sessions: Mapped[list[LearningSessionRow]] = relationship(
        back_populates="student", lazy="raise", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','inactive','graduated','withdrawn')",
            name="ck_students_status",
        ),
        Index("ix_students_major_status", "major", "status"),
    )


class LearningSessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[float | None] = mapped_column(Float)
    platform: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    student: Mapped[StudentRow] = relationship(back_populates="sessions", lazy="raise")
    events: Mapped[list[EngagementEventRow]] = relationship(
        back_populates="session", lazy="raise", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "duration_minutes IS NULL OR duration_minutes >= 0",
            name="ck_sessions_duration_non_negative",
        ),
        Index("ix_sessions_student_start", "student_id", "start_time"),
        Index("ix_sessions_course_start", "course_id", "start_time"),
    )


class EngagementEventRow(Base):
    __tablename__ = "engagement_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_data: Mapped[str | None] = mapped_column(Text)
    engagement_score: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    session: Mapped[LearningSessionRow] = relationship(back_populates="events", lazy="raise")

    __table_args__ = (
        CheckConstraint(
            "engagement_score >= 0.0 AND engagement_score <= 1.0",
            name="ck_events_score_range",
        ),
        Index("ix_events_session_timestamp", "session_id", "timestamp"),
        Index("ix_events_type_timestamp", "event_type", "timestamp"),
    )


__all__ = [
    "Base",
    "EngagementEventRow",
    "LearningSessionRow",
    "StudentRow",
    "UserRow",
    "utcnow",
]
