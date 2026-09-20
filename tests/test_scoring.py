"""Engagement scoring: the arithmetic, checked against hand-computed values."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.application.scoring import (
    BREADTH_WEIGHT,
    EVENT_WEIGHTS,
    HIGH_VALUE_TYPES,
    QUALITY_WEIGHT,
    RECENCY_WEIGHT,
    band_for,
    breadth_component,
    clamp,
    quality_component,
    recency_component,
    score_student,
)
from app.domain.entities import EngagementEvent, EventType

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def event(
    event_type: EventType, score: float, *, days_ago: float = 0.0, ident: int = 1
) -> EngagementEvent:
    return EngagementEvent(
        id=ident,
        session_id=1,
        event_type=event_type,
        event_data=None,
        engagement_score=score,
        timestamp=NOW - timedelta(days=days_ago),
    )


def test_weights_sum_to_one() -> None:
    assert pytest.approx(1.0) == QUALITY_WEIGHT + BREADTH_WEIGHT + RECENCY_WEIGHT


def test_every_event_type_has_a_weight() -> None:
    assert set(EVENT_WEIGHTS) == set(EventType)


def test_clamp_bounds_both_ends() -> None:
    assert clamp(-3.0) == 0.0
    assert clamp(4.2) == 1.0
    assert clamp(0.37) == 0.37


def test_quality_is_a_weight_normalised_mean() -> None:
    events = [
        event(EventType.PAGE_VIEW, 1.0, ident=1),  # weight 0.4
        event(EventType.ASSIGNMENT_SUBMIT, 0.0, ident=2),  # weight 1.3
    ]
    expected = (0.4 * 1.0 + 1.3 * 0.0) / (0.4 + 1.3)
    assert quality_component(events) == pytest.approx(expected)


def test_quality_favours_high_value_participation() -> None:
    """Same per-event scores, different event types: submissions must win."""
    passive = [event(EventType.PAGE_VIEW, 0.9, ident=1), event(EventType.PAGE_VIEW, 0.1, ident=2)]
    active = [
        event(EventType.ASSIGNMENT_SUBMIT, 0.9, ident=1),
        event(EventType.PAGE_VIEW, 0.1, ident=2),
    ]
    assert quality_component(active) > quality_component(passive)


def test_quality_of_no_events_is_zero() -> None:
    assert quality_component([]) == 0.0


def test_breadth_counts_distinct_high_value_types() -> None:
    events = [
        event(EventType.QUIZ_ATTEMPT, 0.5, ident=1),
        event(EventType.QUIZ_ATTEMPT, 0.5, ident=2),  # duplicate type, no extra credit
        event(EventType.PEER_REVIEW, 0.5, ident=3),
        event(EventType.PAGE_VIEW, 0.5, ident=4),  # not high-value
    ]
    assert breadth_component(events) == pytest.approx(2 / len(HIGH_VALUE_TYPES))


def test_breadth_of_only_passive_events_is_zero() -> None:
    assert breadth_component([event(EventType.PAGE_VIEW, 1.0)]) == 0.0


def test_breadth_of_no_events_is_zero() -> None:
    assert breadth_component([]) == 0.0


def test_recency_is_one_for_an_event_right_now() -> None:
    assert recency_component([event(EventType.PAGE_VIEW, 0.5)], now=NOW) == pytest.approx(1.0)


def test_recency_halves_every_fourteen_days() -> None:
    fourteen = recency_component([event(EventType.PAGE_VIEW, 0.5, days_ago=14)], now=NOW)
    twentyeight = recency_component([event(EventType.PAGE_VIEW, 0.5, days_ago=28)], now=NOW)
    assert fourteen == pytest.approx(0.5)
    assert twentyeight == pytest.approx(0.25)


def test_recency_uses_the_most_recent_event() -> None:
    events = [
        event(EventType.PAGE_VIEW, 0.5, days_ago=200, ident=1),
        event(EventType.PAGE_VIEW, 0.5, days_ago=14, ident=2),
    ]
    assert recency_component(events, now=NOW) == pytest.approx(0.5)


def test_recency_of_no_events_is_zero() -> None:
    assert recency_component([], now=NOW) == 0.0


def test_recency_never_exceeds_one_for_a_future_timestamp() -> None:
    assert recency_component([event(EventType.PAGE_VIEW, 0.5, days_ago=-5)], now=NOW) == 1.0


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (1.0, "high"),
        (0.75, "high"),
        (0.74, "moderate"),
        (0.5, "moderate"),
        (0.49, "at-risk"),
        (0.25, "at-risk"),
        (0.24, "disengaged"),
        (0.0, "disengaged"),
    ],
)
def test_band_thresholds(score: float, expected: str) -> None:
    assert band_for(score) == expected


def test_composite_score_matches_hand_calculation() -> None:
    events = [
        event(EventType.ASSIGNMENT_SUBMIT, 0.8, days_ago=0, ident=1),
        event(EventType.QUIZ_ATTEMPT, 0.6, days_ago=0, ident=2),
    ]
    quality = (1.3 * 0.8 + 0.9 * 0.6) / (1.3 + 0.9)
    breadth = 2 / len(HIGH_VALUE_TYPES)
    recency = 1.0
    expected = 0.60 * quality + 0.20 * breadth + 0.20 * recency

    result = score_student(7, events, session_count=2, now=NOW)
    assert result.score == pytest.approx(round(expected, 4))
    assert result.student_id == 7
    assert result.event_count == 2
    assert result.session_count == 2
    assert result.components["quality"] == pytest.approx(round(quality, 4))


def test_a_student_with_no_events_scores_zero_and_is_disengaged() -> None:
    result = score_student(1, [], session_count=0, now=NOW)
    assert result.score == 0.0
    assert result.band == "disengaged"


def test_score_is_bounded_to_zero_one() -> None:
    all_types: list[EventType] = list(EventType)
    perfect = [event(t, 1.0, ident=i) for i, t in enumerate(all_types, start=1)]
    result = score_student(1, perfect, session_count=8, now=NOW)
    assert 0.0 <= result.score <= 1.0


def test_score_is_deterministic() -> None:
    events = [event(EventType.PEER_REVIEW, 0.7, days_ago=3)]
    first = score_student(1, events, session_count=1, now=NOW)
    second = score_student(1, events, session_count=1, now=NOW)
    assert first == second


def test_recency_uses_wall_clock_when_now_is_omitted() -> None:
    """Default branch: an event 'now' still decays to roughly 1.0."""
    from datetime import datetime as real_datetime

    fresh = EngagementEvent(
        id=1,
        session_id=1,
        event_type=EventType.PAGE_VIEW,
        event_data=None,
        engagement_score=0.5,
        timestamp=real_datetime.now(UTC),
    )
    assert recency_component([fresh]) == pytest.approx(1.0, abs=1e-3)
