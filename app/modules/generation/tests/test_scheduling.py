"""Unit tests for putting a planned item on a real day.

The rule these pin down is the one the app was missing: whatever the planner
answers, every item comes out with a date inside its module.
"""

from datetime import date

from app.modules.generation.domain.item_kinds import (
    ItemKind,
    is_graded,
    normalize_kind,
)
from app.modules.generation.domain.scheduling import (
    parse_planned_date,
    schedule_items,
    spread_over,
)

START = date(2026, 3, 2)
END = date(2026, 3, 27)


def test_an_iso_day_inside_the_module_is_kept() -> None:
    assert parse_planned_date("2026-03-10", start=START, end=END) == date(2026, 3, 10)


def test_a_datetime_is_read_as_its_day() -> None:
    assert parse_planned_date("2026-03-10T00:00:00", start=START, end=END) == date(
        2026, 3, 10
    )


def test_prose_is_rejected() -> None:
    # The exact answer the planner used to give, and the reason every item
    # showed up unscheduled.
    assert parse_planned_date("semana 3", start=START, end=END) is None
    assert parse_planned_date("dia 20", start=START, end=END) is None
    assert parse_planned_date(None, start=START, end=END) is None


def test_a_day_outside_the_module_is_rejected() -> None:
    assert parse_planned_date("2026-05-01", start=START, end=END) is None
    assert parse_planned_date("2026-01-01", start=START, end=END) is None


def test_spread_puts_the_first_item_at_the_start_and_the_last_at_the_end() -> None:
    days = spread_over(START, END, 4)

    assert days[0] == START
    assert days[-1] == END
    assert days == sorted(days)


def test_spread_of_one_lands_on_the_first_day() -> None:
    assert spread_over(START, END, 1) == [START]


def test_spread_of_none_is_empty() -> None:
    assert spread_over(START, END, 0) == []


def test_a_zero_length_module_puts_everything_on_its_single_day() -> None:
    assert spread_over(START, START, 3) == [START, START, START]


def test_every_item_gets_a_day_even_when_the_planner_gave_none() -> None:
    days = schedule_items([None, None, None], start=START, end=END)

    assert len(days) == 3
    assert all(START <= day <= END for day in days)


def test_the_planners_dates_are_honoured_and_the_rest_filled_in() -> None:
    days = schedule_items(
        ["2026-03-05", "semana 2", "2026-03-20"], start=START, end=END
    )

    assert date(2026, 3, 5) in days
    assert date(2026, 3, 20) in days
    assert all(START <= day <= END for day in days)


def test_the_result_reads_forward_in_time() -> None:
    # The planner listed a later item first; the feed must not.
    days = schedule_items(["2026-03-20", "2026-03-05"], start=START, end=END)

    assert days == sorted(days)


def test_known_kinds_survive_the_round_trip() -> None:
    for kind in ItemKind:
        assert normalize_kind(kind.value) is kind


def test_kinds_in_other_languages_are_recognised() -> None:
    assert normalize_kind("exam") is ItemKind.EXAM
    assert normalize_kind("Prova escrita") is ItemKind.EXAM
    assert normalize_kind("hands-on activity") is ItemKind.ACTIVITY
    assert normalize_kind("Trabalho em grupo") is ItemKind.ASSIGNMENT


def test_an_unknown_kind_falls_back_instead_of_failing() -> None:
    # Losing a whole roadmap, and the AI call that produced it, over one
    # unexpected label would be the worse trade.
    assert normalize_kind("something the model invented") is ItemKind.ACTIVITY
    assert normalize_kind("") is ItemKind.ACTIVITY
    assert normalize_kind(None) is ItemKind.ACTIVITY


def test_only_assessed_kinds_are_graded() -> None:
    assert is_graded(ItemKind.EXAM)
    assert is_graded(ItemKind.ASSIGNMENT)
    assert not is_graded(ItemKind.CONTENT)
    assert not is_graded(ItemKind.READING)
