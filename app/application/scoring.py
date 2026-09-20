"""Engagement scoring model.

The legacy repo had no scoring logic at all: the API stored whatever float a
client posted, and the only weighting lived in the *seed script's* random number
generator. Scoring is a domain concept, so it lives here — pure, deterministic
and unit-testable with no database and no HTTP.

The composite score for a student blends three normalised components:

``quality``   weighted mean of the student's event scores, where active
              participation (discussion, submission, peer review) counts for
              more than passive consumption (page views, downloads).
``breadth``   how many distinct high-value event types the student has produced,
              normalised against the number of high-value types that exist.
``recency``   exponential decay on days since the student's last event, with a
              14-day half-life.

Composite = 0.60·quality + 0.20·breadth + 0.20·recency, clamped to [0, 1].
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime

from app.domain.entities import EngagementEvent, EngagementScore, EventType

#: How much each event type contributes to the quality component.
EVENT_WEIGHTS: dict[EventType, float] = {
    EventType.PAGE_VIEW: 0.4,
    EventType.RESOURCE_DOWNLOAD: 0.5,
    EventType.VIDEO_WATCH: 0.6,
    EventType.QUIZ_ATTEMPT: 0.9,
    EventType.LAB_EXERCISE: 1.0,
    EventType.DISCUSSION_POST: 1.1,
    EventType.PEER_REVIEW: 1.2,
    EventType.ASSIGNMENT_SUBMIT: 1.3,
}

#: Event types treated as active participation for the breadth component.
HIGH_VALUE_TYPES: frozenset[EventType] = frozenset(
    {
        EventType.QUIZ_ATTEMPT,
        EventType.LAB_EXERCISE,
        EventType.DISCUSSION_POST,
        EventType.PEER_REVIEW,
        EventType.ASSIGNMENT_SUBMIT,
    }
)

QUALITY_WEIGHT = 0.60
BREADTH_WEIGHT = 0.20
RECENCY_WEIGHT = 0.20
RECENCY_HALF_LIFE_DAYS = 14.0

#: Score bands used for the executive-facing label.
BANDS: tuple[tuple[float, str], ...] = (
    (0.75, "high"),
    (0.50, "moderate"),
    (0.25, "at-risk"),
    (0.00, "disengaged"),
)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp a float into ``[low, high]``."""
    return max(low, min(high, value))


def quality_component(events: Sequence[EngagementEvent]) -> float:
    """Weighted mean of per-event scores, normalised by the weights used."""
    if not events:
        return 0.0
    numerator = sum(EVENT_WEIGHTS[e.event_type] * e.engagement_score for e in events)
    denominator = sum(EVENT_WEIGHTS[e.event_type] for e in events)
    if denominator == 0:  # pragma: no cover - weights are all positive
        return 0.0
    return clamp(numerator / denominator)


def breadth_component(events: Sequence[EngagementEvent]) -> float:
    """Fraction of high-value event types the student has actually produced."""
    if not events:
        return 0.0
    distinct = {e.event_type for e in events} & HIGH_VALUE_TYPES
    return clamp(len(distinct) / len(HIGH_VALUE_TYPES))


def recency_component(events: Sequence[EngagementEvent], *, now: datetime | None = None) -> float:
    """Exponential decay on days since the most recent event (14-day half-life)."""
    if not events:
        return 0.0
    reference = now or datetime.now(UTC)
    last = max(e.timestamp for e in events)
    days = max(0.0, (reference - last).total_seconds() / 86_400.0)
    return clamp(math.pow(0.5, days / RECENCY_HALF_LIFE_DAYS))


def band_for(score: float) -> str:
    """Map a composite score onto its executive-facing band label."""
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return BANDS[-1][1]  # pragma: no cover - the 0.0 threshold always matches


def score_student(
    student_pk: int,
    events: Sequence[EngagementEvent],
    *,
    session_count: int,
    now: datetime | None = None,
) -> EngagementScore:
    """Compute the composite engagement score for one student."""
    quality = quality_component(events)
    breadth = breadth_component(events)
    recency = recency_component(events, now=now)
    composite = clamp(
        QUALITY_WEIGHT * quality + BREADTH_WEIGHT * breadth + RECENCY_WEIGHT * recency
    )
    return EngagementScore(
        student_id=student_pk,
        score=round(composite, 4),
        band=band_for(composite),
        event_count=len(events),
        session_count=session_count,
        components={
            "quality": round(quality, 4),
            "breadth": round(breadth, 4),
            "recency": round(recency, 4),
        },
    )
