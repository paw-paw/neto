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


def canonical_csv_bytes(canonical: pd.DataFrame) -> bytes:
    """Serialize a canonical dataframe with NETO's fixed public schema."""

    csv_text = canonical.loc[:, list(OUTPUT_COLUMNS)].to_csv(
        index=False, lineterminator="\n"
    )
    return csv_text.encode("utf-8-sig")


def result_to_csv_bytes(result: ParseResult) -> bytes:
    if not result.exportable:
        raise ValueError(f'Parse status "{result.status}" is not exportable.')
    return canonical_csv_bytes(matches_dataframe(result.matches))
