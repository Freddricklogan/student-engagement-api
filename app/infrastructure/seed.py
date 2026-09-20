"""Deterministic demo-data generator and demo-user bootstrap.

Differences from the legacy ``seed_data.py``:

* No import of the web application — this module depends on the database layer
  only, so seeding never boots an HTTP server.
* A local ``random.Random(seed)`` instance instead of reseeding the global RNG
  at import time.
* Bulk inserts inside a single transaction instead of row-by-row ORM adds with
  intermediate commits.
* ``drop_all`` is opt-in (``reset=True``) rather than unconditional.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.adapters.persistence.models import (
    Base,
    EngagementEventRow,
    LearningSessionRow,
    StudentRow,
    UserRow,
)
from app.domain.entities import EventType, Role
from app.infrastructure.logging import get_logger
from app.infrastructure.security import hash_password
from app.infrastructure.settings import Settings

_logger = get_logger("seed")

MAJORS = (
    "Computer Science",
    "Information Technology",
    "Data Science",
    "Cybersecurity",
    "Electrical Engineering",
    "Business Analytics",
    "Digital Media",
    "Software Engineering",
)

COURSES = ("CS101", "CS201", "IT330", "DS410", "CYB200", "SE350", "BA220", "IT430")

PLATFORMS = ("Canvas LMS", "Zoom", "Lab Workstation", "Mobile App", "Library Portal")

FIRST_NAMES = (
    "Alex",
    "Jordan",
    "Taylor",
    "Morgan",
    "Casey",
    "Riley",
    "Quinn",
    "Avery",
    "Cameron",
    "Drew",
    "Skyler",
    "Reese",
    "Dakota",
    "Sage",
    "Finley",
    "Emery",
    "Hayden",
    "Rowan",
    "Phoenix",
    "Blake",
    "Kai",
    "Arden",
    "Jesse",
    "Noor",
    "Amara",
    "Priya",
    "Wei",
    "Min",
    "Yuki",
    "Ravi",
)

LAST_NAMES = (
    "Chen",
    "Williams",
    "Johnson",
    "Patel",
    "Kim",
    "Garcia",
    "Nguyen",
    "Brown",
    "Martinez",
    "Lee",
    "Taylor",
    "Anderson",
    "Thomas",
    "Jackson",
    "White",
    "Harris",
    "Martin",
    "Thompson",
    "Robinson",
    "Clark",
    "Lewis",
    "Walker",
    "Hall",
    "Allen",
    "Young",
    "King",
    "Wright",
    "Scott",
    "Hill",
    "Green",
)

#: Score ranges per event type, mirroring the weighting in ``app.application.scoring``.
_SCORE_RANGES: dict[EventType, tuple[float, float]] = {
    EventType.DISCUSSION_POST: (0.60, 1.00),
    EventType.ASSIGNMENT_SUBMIT: (0.60, 1.00),
    EventType.PEER_REVIEW: (0.60, 1.00),
    EventType.QUIZ_ATTEMPT: (0.40, 0.90),
    EventType.LAB_EXERCISE: (0.40, 0.90),
    EventType.PAGE_VIEW: (0.10, 0.70),
    EventType.VIDEO_WATCH: (0.10, 0.70),
    EventType.RESOURCE_DOWNLOAD: (0.10, 0.70),
}

_EVENT_TYPES: tuple[EventType, ...] = tuple(EventType)


async def create_schema(engine: AsyncEngine, *, reset: bool = False) -> None:
    """Create (optionally recreate) all tables."""
    async with engine.begin() as conn:
        if reset:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def ensure_demo_users(session: AsyncSession, settings: Settings) -> list[str]:
    """Create the three demo accounts if they are not already present."""
    created: list[str] = []
    accounts = (
        (settings.demo_viewer_username, settings.demo_viewer_password, Role.VIEWER),
        (settings.demo_analyst_username, settings.demo_analyst_password, Role.ANALYST),
        (settings.demo_admin_username, settings.demo_admin_password, Role.ADMIN),
    )
    for username, password, role in accounts:
        exists = (
            await session.execute(select(UserRow.id).where(UserRow.username == username))
        ).scalar_one_or_none()
        if exists is not None:
            continue
        session.add(
            UserRow(
                username=username,
                password_hash=hash_password(password),
                role=role.value,
            )
        )
        created.append(f"{username} ({role.value})")
    await session.flush()
    return created


async def is_empty(session: AsyncSession) -> bool:
    """True when no student rows exist."""
    total = (await session.execute(select(func.count()).select_from(StudentRow))).scalar()
    return not total


async def seed_demo_data(
    session: AsyncSession,
    *,
    seed: int = 42,
    student_count: int = 40,
    now: datetime | None = None,
) -> dict[str, int]:
    """Insert a deterministic demo dataset. Returns per-table counts."""
    # Demo data, not cryptography.
    rng = random.Random(seed)  # noqa: S311  # nosec B311
    reference = now or datetime.now(UTC)
    # Anchor the window on "today" so the dashboard's trend chart is never empty
    # and the recency component of the scoring model has something to decay from.
    window_start = reference - timedelta(days=180)

    student_rows: list[StudentRow] = []
    used_ids: set[str] = set()
    used_emails: set[str] = set()

    for _ in range(student_count):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)

        sid = f"STU{rng.randint(10000, 99999)}"
        while sid in used_ids:
            sid = f"STU{rng.randint(10000, 99999)}"
        used_ids.add(sid)

        email = f"{first.lower()}.{last.lower()}{rng.randint(1, 999)}@example.edu"
        while email in used_emails:
            email = f"{first.lower()}.{last.lower()}{rng.randint(1, 9999)}@example.edu"
        used_emails.add(email)

        student_rows.append(
            StudentRow(
                student_id=sid,
                first_name=first,
                last_name=last,
                email=email,
                major=rng.choice(MAJORS),
                enrollment_date=(window_start + timedelta(days=rng.randint(0, 30))).date(),
                status="active",
            )
        )

    session.add_all(student_rows)
    await session.flush()

    session_rows: list[LearningSessionRow] = []
    for student in student_rows:
        for _ in range(rng.randint(8, 25)):
            start = window_start + timedelta(
                days=rng.randint(0, 179),
                hours=rng.randint(8, 22),
                minutes=rng.randint(0, 59),
            )
            duration = round(rng.uniform(10.0, 120.0), 1)
            session_rows.append(
                LearningSessionRow(
                    student_id=student.id,
                    course_id=rng.choice(COURSES),
                    start_time=start,
                    end_time=start + timedelta(minutes=duration),
                    duration_minutes=duration,
                    platform=rng.choice(PLATFORMS),
                )
            )

    session.add_all(session_rows)
    await session.flush()

    event_rows: list[EngagementEventRow] = []
    for learning_session in session_rows:
        span = learning_session.duration_minutes or 30.0
        for index in range(rng.randint(2, 8)):
            event_type = rng.choice(_EVENT_TYPES)
            low, high = _SCORE_RANGES[event_type]
            payload: dict[str, Any] = {"action": event_type.value, "index": index}
            event_rows.append(
                EngagementEventRow(
                    session_id=learning_session.id,
                    event_type=event_type.value,
                    event_data=json.dumps(payload),
                    engagement_score=round(rng.uniform(low, high), 3),
                    timestamp=learning_session.start_time
                    + timedelta(minutes=rng.uniform(0.0, span)),
                )
            )

    session.add_all(event_rows)
    await session.flush()

    counts = {
        "students": len(student_rows),
        "sessions": len(session_rows),
        "events": len(event_rows),
    }
    _logger.info("demo_data_seeded", **counts)
    return counts


async def bootstrap_demo(engine: AsyncEngine, settings: Settings) -> None:
    """Startup hook for ``DEMO_MODE=true``: schema, demo users, data if empty."""
    await create_schema(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        created = await ensure_demo_users(session, settings)
        if created:
            _logger.info("demo_users_created", accounts=created)
        if await is_empty(session):
            await seed_demo_data(session, seed=settings.demo_seed)
        await session.commit()
