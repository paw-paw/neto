"""Preview and CSV serialization helpers."""

from __future__ import annotations

import pandas as pd

from .models import OUTPUT_COLUMNS, ParseResult, ParsedMatch


def matches_dataframe(matches: list[ParsedMatch]) -> pd.DataFrame:
    return pd.DataFrame(
        [match.as_output_dict() for match in matches], columns=list(OUTPUT_COLUMNS)
    )


def issues_dataframe(result: ParseResult) -> pd.DataFrame:
    columns = [
        "source_sheet",
        "source_row",
        "record_set_id",
        "severity",
        "code",
        "affected_field",
        "message",
    ]
    records = [issue.as_dict() for issue in result.issues]
    if not records:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(records, columns=columns).sort_values(
        by=["source_row", "severity", "code"], kind="stable"
    )


def result_to_csv_bytes(result: ParseResult) -> bytes:
    if not result.exportable:
        raise ValueError(f'Parse status "{result.status}" is not exportable.')
    csv_text = matches_dataframe(result.matches).to_csv(
        index=False, lineterminator="\n"
    )
    return csv_text.encode("utf-8-sig")
