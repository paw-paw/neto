"""Validation finalization shared by XLSX and official-web ingestion."""

from __future__ import annotations

from collections import defaultdict

from .models import (
    IngestionMetadata,
    ParseResult,
    ParsedMatch,
    ValidationIssue,
)


def add_duplicate_issues(
    matches: list[ParsedMatch], issues: list[ValidationIssue]
) -> None:
    groups: dict[tuple[str, str, str], list[ParsedMatch]] = defaultdict(list)
    for match in matches:
        if match.start_time_utc and match.team_a and match.team_b:
            groups[(match.start_time_utc, match.team_a, match.team_b)].append(match)

    for duplicate_group in groups.values():
        if len(duplicate_group) < 2:
            continue
        source_rows = ", ".join(str(match.source_row) for match in duplicate_group)
        for match in duplicate_group:
            issues.append(
                ValidationIssue(
                    source_row=match.source_row,
                    source_sheet=match.source_sheet,
                    severity="warning",
                    code="possible_duplicate",
                    affected_field="start_time_utc,team_a,team_b",
                    message=f"Possible duplicate across source rows {source_rows}.",
                )
            )


def assign_row_statuses(
    matches: list[ParsedMatch], issues: list[ValidationIssue]
) -> None:
    issues_by_row: dict[int, list[ValidationIssue]] = defaultdict(list)
    for issue in issues:
        if issue.source_row is not None:
            issues_by_row[issue.source_row].append(issue)

    for match in matches:
        row_issues = issues_by_row.get(match.source_row, [])
        if any(issue.severity == "blocking_error" for issue in row_issues):
            match.row_status = "invalid"
        elif any(issue.severity == "warning" for issue in row_issues):
            match.row_status = "warning"
        else:
            match.row_status = "valid"


def status_for_issues(issues: list[ValidationIssue]) -> str:
    if any(issue.severity == "blocking_error" for issue in issues):
        return "blocked"
    if any(issue.severity == "warning" for issue in issues):
        return "parsed_with_warnings"
    return "parsed"


def finalize_parse_result(
    matches: list[ParsedMatch],
    issues: list[ValidationIssue],
    *,
    notice: str | None = None,
    ingestion: IngestionMetadata | None = None,
    check_duplicates: bool = True,
) -> ParseResult:
    if check_duplicates:
        add_duplicate_issues(matches, issues)
    assign_row_statuses(matches, issues)
    return ParseResult(
        status=status_for_issues(issues),
        matches=matches,
        issues=issues,
        notice=notice,
        ingestion=ingestion,
    )
