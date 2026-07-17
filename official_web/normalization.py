"""Normalization and finalization shared by official adapters."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from parser.models import IngestionMetadata, ParseResult, ParsedMatch, ValidationIssue
from parser.validation import finalize_parse_result

from .errors import OfficialRequestError, OfficialSchemaError
from .models import OfficialHttpClientProtocol, OfficialScheduleRequest, OfficialSource


MAX_RANGE_DAYS = 90


def normalize_text(value: object) -> str:
    return " ".join(str(value or "").split())


def compose_stage(*parts: object) -> str:
    """Join distinct competition/stage labels without fabricating missing detail."""

    values: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for value in normalize_text(part).split(" · "):
            marker = value.casefold()
            if value and marker not in seen:
                values.append(value)
                seen.add(marker)
    return " · ".join(values)


def request_bounds(request: OfficialScheduleRequest) -> tuple[datetime, datetime]:
    if request.end_date < request.start_date:
        raise OfficialRequestError("End date must be on or after start date.")
    if (request.end_date - request.start_date).days + 1 > MAX_RANGE_DAYS:
        raise OfficialRequestError(f"Official schedule ranges are limited to {MAX_RANGE_DAYS} days.")
    try:
        zone = ZoneInfo(request.range_timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise OfficialRequestError(
            f'Range timezone "{request.range_timezone}" is not a valid IANA timezone.'
        ) from exc
    start_local = datetime.combine(request.start_date, time.min, tzinfo=zone)
    end_local = datetime.combine(request.end_date + timedelta(days=1), time.min, tzinfo=zone)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def parse_utc(value: object, path: str) -> datetime:
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            parsed = datetime.fromtimestamp(float(value), tz=timezone.utc)
        else:
            text = normalize_text(value)
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                raise ValueError("timezone missing")
            parsed = parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OSError, OverflowError) as exc:
        raise OfficialSchemaError(f"Expected a UTC datetime at {path}.") from exc
    return parsed.replace(microsecond=0)


def utc_fields(value: datetime) -> tuple[str, str, str]:
    utc_value = value.astimezone(timezone.utc).replace(microsecond=0)
    return (
        utc_value.strftime("%Y-%m-%d"),
        utc_value.strftime("%H:%M:%S"),
        utc_value.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def mapping(value: object, path: str) -> dict:
    if not isinstance(value, dict):
        raise OfficialSchemaError(f"Expected an object at {path}.")
    return value


def sequence(value: object, path: str) -> list:
    if not isinstance(value, list):
        raise OfficialSchemaError(f"Expected an array at {path}.")
    return value


def issue(
    match: ParsedMatch,
    code: str,
    message: str,
    field: str | None = None,
    severity: str = "warning",
) -> ValidationIssue:
    return ValidationIssue(
        source_row=match.source_row,
        source_sheet=match.source_sheet,
        severity=severity,
        code=code,
        affected_field=field,
        message=message,
    )


def finish_official_result(
    *,
    source: OfficialSource,
    request: OfficialScheduleRequest,
    client: OfficialHttpClientProtocol,
    matches: list[ParsedMatch],
    warning_specs: dict[str, list[tuple[str, str, str | None]]],
    conflict_ids: set[str] | None = None,
) -> ParseResult:
    for match in matches:
        if match.official:
            match.stage = compose_stage(
                match.official.competition_name,
                match.stage,
            )
    matches.sort(key=lambda match: (match.start_time_utc, match.official.match_id if match.official else ""))
    issues: list[ValidationIssue] = []
    for row_number, match in enumerate(matches, start=1):
        match.source_row = row_number
        match.source_sheet = source.source_id
        match_id = match.official.match_id if match.official else ""
        for code, message, field in warning_specs.get(match_id, []):
            issues.append(issue(match, code, message, field))
        if not match.stage:
            issues.append(issue(match, "stage_missing", "Stage is missing.", "stage"))
        if not match.bo:
            issues.append(issue(match, "bo_missing", "Best-of is missing.", "bo"))
        if not match.match_label:
            issues.append(
                issue(match, "match_label_missing", "Match label is missing.", "match_label")
            )
        if conflict_ids and match_id in conflict_ids:
            issues.append(
                issue(
                    match,
                    "conflicting_official_match",
                    "The official source returned conflicting copies of this match; the richest latest-state copy was retained.",
                )
            )

    fetched = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ingestion = IngestionMetadata(
        method="official_web",
        source_id=source.source_id,
        source_label=source.label,
        source_url=source.source_url,
        strategy=source.strategy,
        fetched_at_utc=fetched,
        request_count=client.request_count,
        legitimate_empty=not matches,
        range_start=request.start_date.isoformat(),
        range_end=request.end_date.isoformat(),
        range_timezone=request.range_timezone,
    )
    notice = (
        f"retrieval_strategy: {source.strategy}. No official matches were published "
        "for the selected range."
        if not matches
        else f"retrieval_strategy: {source.strategy}."
    )
    return finalize_parse_result(
        matches,
        issues,
        notice=notice,
        ingestion=ingestion,
    )
