"""Deterministic date, time, and timezone conversion helpers."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from openpyxl.utils.datetime import WINDOWS_EPOCH, from_excel


DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
)
TIME_FORMATS: tuple[str, ...] = (
    "%H:%M",
    "%H:%M:%S",
    "%I:%M %p",
    "%I:%M:%S %p",
)


class NonexistentLocalTimeError(ValueError):
    """Raised when a wall-clock time falls inside a DST gap."""


class AmbiguousLocalTimeError(ValueError):
    """Raised when a wall-clock time is ambiguous and strict handling is requested."""


def normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def parse_date_value(value: Any, epoch: datetime = WINDOWS_EPOCH) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, bool):
        raise ValueError("Boolean values are not dates.")
    if isinstance(value, (int, float)):
        parsed = from_excel(value, epoch=epoch)
        if isinstance(parsed, datetime):
            return parsed.date()
        if isinstance(parsed, date):
            return parsed
        raise ValueError("Numeric value is not an Excel date.")
    if isinstance(value, str):
        normalized = normalize_whitespace(value)
        for date_format in DATE_FORMATS:
            try:
                return datetime.strptime(normalized, date_format).date()
            except ValueError:
                continue
    raise ValueError(f"Unsupported date value: {value!r}")


def parse_time_value(value: Any, epoch: datetime = WINDOWS_EPOCH) -> time:
    if isinstance(value, datetime):
        return value.time().replace(tzinfo=None)
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    if isinstance(value, bool):
        raise ValueError("Boolean values are not times.")
    if isinstance(value, (int, float)):
        if not 0 <= float(value) < 1:
            raise ValueError("Numeric time must be an Excel day fraction in [0, 1).")
        parsed = from_excel(value, epoch=epoch)
        if isinstance(parsed, datetime):
            return parsed.time().replace(tzinfo=None)
        if isinstance(parsed, time):
            return parsed.replace(tzinfo=None)
        raise ValueError("Numeric value is not an Excel time.")
    if isinstance(value, str):
        normalized = normalize_whitespace(value).upper()
        for time_format in TIME_FORMATS:
            try:
                return datetime.strptime(normalized, time_format).time()
            except ValueError:
                continue
    raise ValueError(f"Unsupported time value: {value!r}")


def to_utc_string(
    local_date: date,
    local_time: time,
    zone: ZoneInfo,
    *,
    ambiguous_policy: str = "fold_zero",
) -> str:
    naive = datetime.combine(local_date, local_time).replace(microsecond=0)

    valid_candidates: list[datetime] = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold)
        round_trip = (
            candidate.astimezone(timezone.utc)
            .astimezone(zone)
            .replace(tzinfo=None)
        )
        if round_trip == naive:
            valid_candidates.append(candidate)

    if not valid_candidates:
        raise NonexistentLocalTimeError(
            f"Local time {naive.isoformat(sep=' ')} does not exist in {zone.key}."
        )

    offsets = {candidate.utcoffset() for candidate in valid_candidates}
    if len(offsets) > 1 and ambiguous_policy == "blocking_error":
        raise AmbiguousLocalTimeError(
            f"Local time {naive.isoformat(sep=' ')} is ambiguous in {zone.key}."
        )

    # fold=0 is the first candidate and is the deterministic choice during fall-back.
    utc_value = valid_candidates[0].astimezone(timezone.utc)
    return utc_value.strftime("%Y-%m-%dT%H:%M:%SZ")
