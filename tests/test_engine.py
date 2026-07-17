from __future__ import annotations

from dataclasses import replace
from datetime import date, time

import pytest

from parser import parse_workbook
from tests.helpers import make_parser_key, valid_row, workbook_bytes


def issue_codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


def test_parses_and_normalizes_whitespace() -> None:
    data = workbook_bytes(
        [
            valid_row(
                team_a="  Team\n  Alpha  ",
                team_b="Team    Beta",
                stage=" Group\tStage ",
            )
        ]
    )

    result = parse_workbook(data, make_parser_key())

    assert result.status == "parsed"
    assert result.matches[0].team_a == "Team Alpha"
    assert result.matches[0].team_b == "Team Beta"
    assert result.matches[0].stage == "Group Stage"
    assert result.matches[0].start_time_utc == "2026-07-01T23:00:00Z"
    assert result.matches[0].row_status == "valid"
    assert "timezone_from_key" not in issue_codes(result)


def test_empty_rows_reset_and_stop_after_five_consecutive_rows() -> None:
    whitespace_row = {field: " \n " for field in make_parser_key().field_mappings}
    rows = [
        valid_row(match_label="First"),
        whitespace_row,
        valid_row(match_label="Second", team_a="C", team_b="D"),
        whitespace_row,
        whitespace_row,
        whitespace_row,
        whitespace_row,
        whitespace_row,
        valid_row(match_label="Ignored", team_a="E", team_b="F"),
    ]

    result = parse_workbook(workbook_bytes(rows), make_parser_key())

    assert result.status == "parsed"
    assert [match.match_label for match in result.matches] == ["First", "Second"]


def test_forward_fill_applies_only_to_enabled_non_team_fields() -> None:
    key = make_parser_key(
        forward_fill={"date": True, "stage": True, "team_a": True}
    )
    rows = [
        valid_row(date=date(2026, 7, 2), stage="Playoffs", team_a="Original"),
        valid_row(
            date=None,
            stage=None,
            team_a=None,
            team_b="Opponent",
            match_label="Match 2",
        ),
    ]

    result = parse_workbook(workbook_bytes(rows), key)

    assert result.matches[1].date_original == "2026-07-02"
    assert result.matches[1].stage == "Playoffs"
    assert result.matches[1].team_a == ""
    assert "missing_team_a" in issue_codes(result)
    assert result.status == "blocked"


def test_formula_without_cached_value_is_not_forward_filled() -> None:
    rows = [
        valid_row(date=date(2026, 7, 1)),
        valid_row(date="=A2+1", team_a="Other A", team_b="Other B"),
    ]

    result = parse_workbook(workbook_bytes(rows), make_parser_key())

    assert result.status == "blocked"
    assert result.matches[1].date_original == ""
    assert any(
        issue.code == "unparseable_date" and issue.source_row == 3
        for issue in result.issues
    )


def test_v0_empty_participant_policy_uses_tbd_for_plain_blanks() -> None:
    key = replace(
        make_parser_key(),
        raw_data={
            "validation_rules": {"empty_participant_policy": "use_tbd"}
        },
    )

    result = parse_workbook(
        workbook_bytes([valid_row(team_a=None, team_b=None)]), key
    )

    assert result.status == "parsed"
    assert result.matches[0].team_a == result.matches[0].team_b == "TBD"
    assert "formula_cached_value_missing" not in issue_codes(result)


def test_v0_formula_participant_uses_tbd_and_keeps_cache_warning() -> None:
    key = replace(
        make_parser_key(),
        raw_data={
            "validation_rules": {"empty_participant_policy": "use_tbd"}
        },
    )

    result = parse_workbook(
        workbook_bytes([valid_row(team_a="=C3", team_b="Opponent")]), key
    )

    assert result.status == "parsed_with_warnings"
    assert result.matches[0].team_a == "TBD"
    assert "formula_cached_value_missing" in issue_codes(result)
    assert not any(
        str(value).lstrip().startswith("=")
        for value in result.matches[0].as_output_dict().values()
    )


def test_missing_critical_fields_and_optional_warnings() -> None:
    row = {
        "date": None,
        "time": None,
        "team_a": None,
        "team_b": None,
        "stage": None,
        "bo": None,
        "match_label": "keeps row non-empty",
    }

    result = parse_workbook(workbook_bytes([row]), make_parser_key())

    assert result.status == "blocked"
    assert result.matches[0].row_status == "invalid"
    assert {"missing_date", "missing_time", "missing_team_a", "missing_team_b"} <= issue_codes(result)
    assert {"stage_missing", "bo_missing"} <= issue_codes(result)


def test_unparseable_fields_are_blocking() -> None:
    result = parse_workbook(
        workbook_bytes([valid_row(date="not a date", time="not a time")]),
        make_parser_key(),
    )

    assert result.status == "blocked"
    assert {"unparseable_date", "unparseable_time"} <= issue_codes(result)


@pytest.mark.parametrize(
    ("timezone", "expected_code"),
    [("", "missing_timezone"), ("Mars/Olympus_Mons", "invalid_timezone")],
)
def test_timezone_errors_are_row_level_blockers(timezone: str, expected_code: str) -> None:
    result = parse_workbook(
        workbook_bytes([valid_row()]), make_parser_key(timezone=timezone)
    )

    assert result.status == "blocked"
    assert expected_code in issue_codes(result)
    assert result.matches[0].start_time_utc == ""


def test_nonexistent_datetime_uses_unparseable_datetime_code() -> None:
    result = parse_workbook(
        workbook_bytes(
            [valid_row(date=date(2026, 3, 8), time=time(2, 30))]
        ),
        make_parser_key(timezone="America/New_York"),
    )

    assert result.status == "blocked"
    assert "unparseable_datetime" in issue_codes(result)


def test_optional_field_warnings_allow_export() -> None:
    result = parse_workbook(
        workbook_bytes([valid_row(stage=None, bo=None, match_label=None)]),
        make_parser_key(),
    )

    assert result.status == "parsed_with_warnings"
    assert result.exportable
    assert result.matches[0].row_status == "warning"
    assert {"stage_missing", "bo_missing", "match_label_missing"} <= issue_codes(result)


def test_duplicate_warning_marks_every_row_in_group() -> None:
    rows = [valid_row(), valid_row()]
    result = parse_workbook(workbook_bytes(rows), make_parser_key())

    duplicate_issues = [
        issue for issue in result.issues if issue.code == "possible_duplicate"
    ]
    assert result.status == "parsed_with_warnings"
    assert len(duplicate_issues) == 2
    assert [match.row_status for match in result.matches] == ["warning", "warning"]


def test_failed_results_for_bad_file_missing_sheet_and_no_matches() -> None:
    bad_file = parse_workbook(b"not an xlsx", make_parser_key())
    missing_sheet = parse_workbook(
        workbook_bytes([valid_row()], sheet_name="Other"), make_parser_key()
    )
    no_matches = parse_workbook(workbook_bytes([]), make_parser_key())

    assert bad_file.status == "failed"
    assert missing_sheet.status == "failed"
    assert "expects sheet" in (missing_sheet.technical_error or "")
    assert no_matches.status == "failed"
