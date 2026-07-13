from __future__ import annotations

from datetime import date, time
from io import BytesIO
from typing import Any

from openpyxl import Workbook

from parser.models import ParserKey


DEFAULT_MAPPINGS: dict[str, str | None] = {
    "date": "A",
    "time": "B",
    "team_a": "C",
    "team_b": "D",
    "stage": "E",
    "bo": "F",
    "match_label": "G",
}


def make_parser_key(
    *,
    timezone: str = "America/Lima",
    target_sheet: str = "Schedule",
    forward_fill: dict[str, bool] | None = None,
    mappings: dict[str, str | None] | None = None,
) -> ParserKey:
    rules = {field: False for field in DEFAULT_MAPPINGS}
    rules["date"] = True
    if forward_fill:
        rules.update(forward_fill)
    return ParserKey(
        parser_key_id="test_key",
        key_name="Test Key",
        tournament_name="Test Tournament",
        base_timezone=timezone,
        target_sheet=target_sheet,
        layout_type="linear_table",
        header_row=1,
        data_start_row=2,
        field_mappings=(mappings or DEFAULT_MAPPINGS).copy(),
        forward_fill_rules=rules,
    )


def valid_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "date": date(2026, 7, 1),
        "time": time(18, 0),
        "team_a": "Team A",
        "team_b": "Team B",
        "stage": "Group Stage",
        "bo": "Bo3",
        "match_label": "Match 1",
    }
    row.update(overrides)
    return row


def workbook_bytes(
    rows: list[dict[str, Any]],
    *,
    sheet_name: str = "Schedule",
    mappings: dict[str, str | None] | None = None,
) -> bytes:
    active_mappings = mappings or DEFAULT_MAPPINGS
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name

    for field, column in active_mappings.items():
        if column:
            sheet[f"{column}1"] = field

    for row_number, values in enumerate(rows, start=2):
        for field, column in active_mappings.items():
            if column and field in values:
                sheet[f"{column}{row_number}"] = values[field]

    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()
