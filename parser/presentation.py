"""UI-facing filtering, sorting, and local-time presentation helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from .export import matches_dataframe
from .models import ParseResult


PRESENTATION_COLUMNS: tuple[str, ...] = (
    "date",
    "time",
    "team_a",
    "team_b",
    "bo",
    "stage",
    "match_label",
    "timezone",
    "start_time_utc",
    "row_status",
)


def canonical_view_dataframe(
    result: ParseResult,
    *,
    descending: bool = True,
    search: str = "",
    stages: Iterable[str] | None = None,
    bos: Iterable[str] | None = None,
    statuses: Iterable[str] | None = None,
    competitions: Iterable[str] | None = None,
    match_states: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Return the canonical rows after stable UTC sorting and UI filters."""

    dataframe = matches_dataframe(result.matches).copy()
    dataframe["_official_match_id"] = [
        match.official.match_id if match.official else "" for match in result.matches
    ]
    dataframe["_competition"] = [
        match.official.competition_name if match.official else ""
        for match in result.matches
    ]
    dataframe["_region"] = [
        match.official.region if match.official else "" for match in result.matches
    ]
    dataframe["_match_state"] = [
        match.official.match_state if match.official else "" for match in result.matches
    ]
    dataframe["_source_url"] = [
        match.official.source_url if match.official else "" for match in result.matches
    ]
    dataframe["_start_sort"] = pd.to_datetime(
        dataframe["start_time_utc"], errors="coerce", utc=True
    )

    query = search.strip()
    if query:
        searchable = dataframe[
            ["team_a", "team_b", "stage", "match_label", "_competition"]
        ].fillna("")
        mask = searchable.apply(
            lambda column: column.astype(str).str.contains(
                query, case=False, regex=False, na=False
            )
        ).any(axis=1)
        dataframe = dataframe.loc[mask]

    for column, selected in (
        ("stage", stages),
        ("bo", bos),
        ("row_status", statuses),
        ("_competition", competitions),
        ("_match_state", match_states),
    ):
        values = list(selected or [])
        if values:
            dataframe = dataframe.loc[dataframe[column].isin(values)]

    return dataframe.sort_values(
        by="_start_sort",
        ascending=not descending,
        na_position="last",
        kind="stable",
    ).reset_index(drop=True)


def _natural_date(value: object, date_format: str) -> str:
    text = "" if value is None else str(value).strip()
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return text
    year, month, day = match.groups()
    if date_format == "MM-DD-YYYY":
        return f"{month}-{day}-{year}"
    if date_format == "YYYY-MM-DD":
        return text
    return f"{day}-{month}-{year}"


def _natural_time(value: object) -> str:
    text = "" if value is None else str(value).strip()
    match = re.match(r"^(\d{1,2}):(\d{2})", text)
    return f"{int(match.group(1)):02d}:{match.group(2)}" if match else text


def presentation_dataframe(
    canonical: pd.DataFrame,
    *,
    date_format: str = "DD-MM-YYYY",
    display_timezone: str | None = None,
) -> pd.DataFrame:
    """Format a canonical view for traders without changing its source fields."""

    date_values = canonical["date_original"].map(
        lambda value: _natural_date(value, date_format)
    )
    time_values = canonical["time_original"].map(_natural_time)

    if display_timezone and not canonical.empty:
        localized = pd.to_datetime(
            canonical["start_time_utc"], errors="coerce", utc=True
        ).dt.tz_convert(ZoneInfo(display_timezone))
        valid = localized.notna()
        if date_format == "MM-DD-YYYY":
            localized_dates = localized.dt.strftime("%m-%d-%Y")
        elif date_format == "YYYY-MM-DD":
            localized_dates = localized.dt.strftime("%Y-%m-%d")
        else:
            localized_dates = localized.dt.strftime("%d-%m-%Y")
        date_values = date_values.where(~valid, localized_dates)
        time_values = time_values.where(~valid, localized.dt.strftime("%H:%M"))

    return pd.DataFrame(
        {
            "date": date_values,
            "time": time_values,
            "team_a": canonical["team_a"],
            "team_b": canonical["team_b"],
            "bo": canonical["bo"],
            "stage": canonical["stage"],
            "match_label": canonical["match_label"],
            "timezone": canonical["timezone"],
            "start_time_utc": canonical["start_time_utc"],
            "row_status": canonical["row_status"],
        },
        columns=list(PRESENTATION_COLUMNS),
    ).reset_index(drop=True)


def timezone_difference_label(
    canonical: pd.DataFrame, schedule_timezone: str, display_timezone: str
) -> str:
    """Describe view-zone offset minus schedule-zone offset for the first match."""

    if canonical.empty:
        return "—"
    timestamp = pd.to_datetime(canonical.iloc[0]["start_time_utc"], errors="coerce", utc=True)
    if pd.isna(timestamp):
        return "—"
    schedule_offset = timestamp.tz_convert(ZoneInfo(schedule_timezone)).utcoffset()
    display_offset = timestamp.tz_convert(ZoneInfo(display_timezone)).utcoffset()
    if schedule_offset is None or display_offset is None:
        return "—"
    hours = (display_offset - schedule_offset).total_seconds() / 3600
    if hours == 0:
        return "0 h"
    formatted = f"{abs(hours):g}"
    return f"{'+' if hours > 0 else '-'}{formatted} h"
