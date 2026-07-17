from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from google_sheets import fetch_google_sheet, parse_fetched_google_sheet
from parser.parser_keys import load_parser_keys
from parser.suggestions import fingerprint_workbook, rank_parser_keys


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("NETO_RUN_LIVE_TESTS") != "1",
        reason="Set NETO_RUN_LIVE_TESTS=1 to call the public Google Sheets exporter.",
    ),
]


CASES_PATH = Path(__file__).parent / "fixtures" / "public_google_sheets_cases.json"
PUBLIC_SHEETS = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
PARSER_KEYS = load_parser_keys(Path(__file__).parents[1] / "parser_keys").keys


@pytest.mark.parametrize(
    "case",
    PUBLIC_SHEETS,
    ids=[case["case_id"] for case in PUBLIC_SHEETS],
)
def test_public_google_sheet_exports_and_ranks_as_expected(
    case: dict[str, object],
) -> None:
    fetched = fetch_google_sheet(str(case["url"]))

    assert fetched.content.startswith(b"PK")
    assert fetched.file_name.lower().endswith(".xlsx")
    assert fetched.ingestion_metadata().method == "google_sheets"

    suggestions = rank_parser_keys(
        fingerprint_workbook(fetched.content, fetched.file_name),
        PARSER_KEYS,
    )
    acceptable_ids = set(case["acceptable_parser_key_ids"])
    if acceptable_ids:
        assert suggestions
        assert suggestions[0].parser_key.parser_key_id in acceptable_ids
    else:
        assert suggestions == []

    parse_expectation = case.get("live_parse_expectation")
    if isinstance(parse_expectation, dict):
        key_by_id = {key.parser_key_id: key for key in PARSER_KEYS}
        parser_key = key_by_id[parse_expectation["parser_key_id"]]
        result = parse_fetched_google_sheet(fetched, parser_key)
        assert result.status == parse_expectation["status"]
        assert result.exportable
        assert result.total_matches == parse_expectation["matches"]
        assert result.errors_count == parse_expectation["blocking_errors"]
        assert result.warnings_count == parse_expectation["warnings"]
        assert sorted({issue.code for issue in result.issues}) == sorted(
            parse_expectation["issue_codes"]
        )
        for match in result.matches:
            for value in match.as_output_dict().values():
                assert not str(value).lstrip().startswith("=")
                assert "openpyxl" not in str(value).casefold()
