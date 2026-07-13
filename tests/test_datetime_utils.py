from __future__ import annotations

from datetime import date, time
from zoneinfo import ZoneInfo

import pytest

from parser.datetime_utils import (
    AmbiguousLocalTimeError,
    NonexistentLocalTimeError,
    parse_date_value,
    parse_time_value,
    to_utc_string,
)


@pytest.mark.parametrize(
    "value",
    ["2026-07-09", "2026/07/09", "09/07/2026", "09-07-2026", "09.07.2026"],
)
def test_supported_date_strings_are_day_first(value: str) -> None:
    assert parse_date_value(value) == date(2026, 7, 9)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("18:05", time(18, 5)),
        ("18:05:12", time(18, 5, 12)),
        ("6:05 PM", time(18, 5)),
        ("6:05:12 pm", time(18, 5, 12)),
    ],
)
def test_supported_time_strings(value: str, expected: time) -> None:
    assert parse_time_value(value) == expected


def test_lima_time_normalizes_to_utc() -> None:
    result = to_utc_string(
        date(2026, 6, 27), time(10, 0), ZoneInfo("America/Lima")
    )
    assert result == "2026-06-27T15:00:00Z"


def test_nonexistent_dst_time_is_rejected() -> None:
    with pytest.raises(NonexistentLocalTimeError):
        to_utc_string(
            date(2026, 3, 8), time(2, 30), ZoneInfo("America/New_York")
        )


def test_ambiguous_dst_time_uses_fold_zero() -> None:
    result = to_utc_string(
        date(2026, 11, 1), time(1, 30), ZoneInfo("America/New_York")
    )
    assert result == "2026-11-01T05:30:00Z"


def test_ambiguous_dst_time_can_be_blocking() -> None:
    with pytest.raises(AmbiguousLocalTimeError):
        to_utc_string(
            date(2026, 11, 1),
            time(1, 30),
            ZoneInfo("America/New_York"),
            ambiguous_policy="blocking_error",
        )


@pytest.mark.parametrize("value", ["07/09/26", "July 9, 2026", True])
def test_unsupported_dates_are_rejected(value) -> None:
    with pytest.raises(ValueError):
        parse_date_value(value)


@pytest.mark.parametrize("value", ["24:00", "18.30", 1, True])
def test_unsupported_times_are_rejected(value) -> None:
    with pytest.raises(ValueError):
        parse_time_value(value)
