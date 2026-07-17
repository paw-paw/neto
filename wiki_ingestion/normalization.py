"""Shared normalization and result classification for tournament wikis."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from parser.models import IngestionMetadata, ParseResult, ParsedMatch, ValidationIssue
from parser.validation import finalize_parse_result

from .errors import WikiStructureError
from .models import WikiHttpClientProtocol
from .urls import TournamentPage


def normalize_text(value: object) -> str:
    return " ".join(str(value or "").split())


def parse_api_utc(value: object, path: str) -> datetime:
    text = normalize_text(value)
    if not text:
        raise ValueError(f"Missing UTC datetime at {path}.")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Invalid UTC datetime at {path}.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def utc_fields(value: datetime) -> tuple[str, str, str]:
    utc_value = value.astimezone(timezone.utc).replace(microsecond=0)
    return (
        utc_value.strftime("%Y-%m-%d"),
        utc_value.strftime("%H:%M:%S"),
        utc_value.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def warning(
    *,
    source_row: int | None,
    page: TournamentPage,
    code: str,
    message: str,
    field: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        source_row=source_row,
        source_sheet=page.title,
        severity="warning",
        code=code,
        message=message,
        affected_field=field,
    )


def failure_metadata(
    page: TournamentPage,
    strategy: str,
    client: WikiHttpClientProtocol | None,
) -> IngestionMetadata:
    return IngestionMetadata(
        method="wiki_tournament",
        source_id=page.source_id,
        source_label=f"Leaguepedia — {page.game_label}",
        source_url=page.url,
        strategy=strategy,
        fetched_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        request_count=getattr(client, "request_count", 0),
    )


def finish_wiki_result(
    *,
    page: TournamentPage,
    strategy: str,
    client: WikiHttpClientProtocol,
    candidate_count: int,
    matches: list[ParsedMatch],
    issues: list[ValidationIssue],
    skipped_count: int,
) -> ParseResult:
    if candidate_count and not matches:
        raise WikiStructureError(
            "Schedule records were found, but none had an unambiguous date, time, Team A, and Team B."
        )

    for match in matches:
        if not match.stage:
            issues.append(
                warning(
                    source_row=match.source_row,
                    page=page,
                    code="stage_missing",
                    message="Stage is missing from the wiki record.",
                    field="stage",
                )
            )
        if not match.bo:
            issues.append(
                warning(
                    source_row=match.source_row,
                    page=page,
                    code="bo_missing",
                    message="Best-of is missing from the wiki record.",
                    field="bo",
                )
            )
        if not match.match_label:
            issues.append(
                warning(
                    source_row=match.source_row,
                    page=page,
                    code="match_label_missing",
                    message="Match label is missing from the wiki record.",
                    field="match_label",
                )
            )

    matches.sort(key=lambda match: (match.start_time_utc, match.source_row))
    ingestion = replace(
        failure_metadata(page, strategy, client),
        legitimate_empty=candidate_count == 0,
    )
    attribution = "Leaguepedia source data: CC BY-SA 3.0."
    if candidate_count == 0:
        notice = f"No schedule found for this tournament page. {attribution}"
    elif skipped_count:
        notice = (
            f"Partial extraction: {len(matches)} reliable match(es) returned and "
            f"{skipped_count} ambiguous record(s) skipped with warnings. {attribution}"
        )
    elif issues:
        notice = f"Extraction succeeded with warnings. {attribution}"
    else:
        notice = f"Complete extraction: {len(matches)} match(es). {attribution}"
    return finalize_parse_result(
        matches,
        issues,
        notice=notice,
        ingestion=ingestion,
    )
