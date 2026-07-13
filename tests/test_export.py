from __future__ import annotations

import pandas as pd
import pytest

from parser import OUTPUT_COLUMNS, parse_workbook, result_to_csv_bytes
from tests.helpers import make_parser_key, valid_row, workbook_bytes


def test_csv_is_utf8_bom_and_uses_fixed_columns() -> None:
    result = parse_workbook(workbook_bytes([valid_row()]), make_parser_key())

    csv_bytes = result_to_csv_bytes(result)
    dataframe = pd.read_csv(
        __import__("io").BytesIO(csv_bytes), encoding="utf-8-sig"
    )

    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    assert list(dataframe.columns) == list(OUTPUT_COLUMNS)
    assert dataframe.loc[0, "row_status"] == "valid"
    assert "source_row" not in dataframe.columns


def test_csv_export_is_blocked_for_invalid_parse() -> None:
    result = parse_workbook(
        workbook_bytes([valid_row(team_a=None)]), make_parser_key()
    )

    assert result.status == "blocked"
    with pytest.raises(ValueError, match="not exportable"):
        result_to_csv_bytes(result)
