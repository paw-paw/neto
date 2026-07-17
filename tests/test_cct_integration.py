from __future__ import annotations

from pathlib import Path

from parser import load_parser_keys, parse_workbook


ROOT = Path(__file__).resolve().parents[1]


def test_supplied_cct_workbook_end_to_end() -> None:
    catalog = load_parser_keys(ROOT / "parser_keys")
    parser_key = next(
        key
        for key in catalog.keys
        if key.parser_key_id == "cct_2026_sa3_public_schedule_v1"
    )
    workbook = (
        ROOT / "tests" / "fixtures" / "cct_2026_sa3_public_schedule.xlsx"
    ).read_bytes()

    result = parse_workbook(workbook, parser_key)

    assert result.status == "parsed"
    assert result.total_matches == 48
    assert result.valid_matches == 48
    assert result.warning_matches == 0
    assert result.invalid_matches == 0
    assert result.warnings_count == 0
    assert result.errors_count == 0
    assert result.matches[0].start_time_utc == "2026-06-27T13:00:00Z"
    assert result.matches[-1].start_time_utc == "2026-07-09T21:00:00Z"
