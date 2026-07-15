"""Cheap structural ParserKey ranking for uploaded XLSX workbooks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.cell import column_index_from_string
from openpyxl.utils.exceptions import InvalidFileException

from .models import ParserKey
from .workbook_security import WorkbookSafetyError, validate_xlsx_archive


SAMPLE_ROWS = 32
SAMPLE_COLUMNS = 40
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "best",
    "event",
    "for",
    "main",
    "of",
    "offline",
    "online",
    "public",
    "schedule",
    "season",
    "series",
    "stage",
    "the",
    "tournament",
    "v1",
    "v2",
    "xlsx",
}
HEADER_HINTS = {
    "date": {"date", "day"},
    "time": {"time", "start", "utc", "local"},
    "team_a": {"team", "team1", "teama", "home", "opponent"},
    "team_b": {"team", "team2", "teamb", "away", "opponent"},
    "stage": {"stage", "phase", "round", "group"},
    "bo": {"bo", "bestof", "format", "maps"},
    "match_label": {"match", "label", "game", "fixture"},
}


class WorkbookFingerprintError(ValueError):
    """Raised when a workbook cannot be fingerprinted safely."""


@dataclass(frozen=True)
class SheetFingerprint:
    name: str
    max_row: int
    max_column: int
    sampled_tokens: frozenset[str]
    row_tokens: dict[int, frozenset[str]]


@dataclass(frozen=True)
class WorkbookFingerprint:
    file_name: str
    sheets: tuple[SheetFingerprint, ...]

    @property
    def sheet_names(self) -> tuple[str, ...]:
        return tuple(sheet.name for sheet in self.sheets)

    @property
    def sampled_tokens(self) -> frozenset[str]:
        return frozenset(
            token for sheet in self.sheets for token in sheet.sampled_tokens
        )


@dataclass(frozen=True)
class ParserKeySuggestion:
    parser_key: ParserKey
    score: int
    confidence: str
    reasons: tuple[str, ...]

    @property
    def recommended(self) -> bool:
        return self.confidence in {"High", "Medium"}


def _tokens(value: object) -> set[str]:
    if value is None:
        return set()
    return set(TOKEN_RE.findall(str(value).casefold()))


def _identity_tokens(value: object) -> set[str]:
    return {
        token
        for token in _tokens(value)
        if token not in STOPWORDS and not token.isdigit() and len(token) > 1
    }


def fingerprint_workbook(file_bytes: bytes, file_name: str = "workbook.xlsx") -> WorkbookFingerprint:
    """Read only a bounded cell sample plus workbook dimensions and sheet names."""

    try:
        validate_xlsx_archive(file_bytes)
    except WorkbookSafetyError as exc:
        raise WorkbookFingerprintError(
            f"The uploaded XLSX could not be inspected: {exc}"
        ) from exc

    try:
        workbook = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    except (OSError, ValueError, BadZipFile, InvalidFileException) as exc:
        raise WorkbookFingerprintError(f"The uploaded XLSX could not be inspected: {exc}") from exc

    sheets: list[SheetFingerprint] = []
    try:
        for worksheet in workbook.worksheets:
            row_tokens: dict[int, frozenset[str]] = {}
            sampled: set[str] = set()
            max_row = int(worksheet.max_row or 0)
            max_column = int(worksheet.max_column or 0)
            for row_number, row in enumerate(
                worksheet.iter_rows(
                    min_row=1,
                    max_row=min(max_row, SAMPLE_ROWS),
                    max_col=min(max_column, SAMPLE_COLUMNS),
                    values_only=True,
                ),
                start=1,
            ):
                current = set().union(*(_tokens(value) for value in row)) if row else set()
                row_tokens[row_number] = frozenset(current)
                sampled.update(current)
            sheets.append(
                SheetFingerprint(
                    name=worksheet.title,
                    max_row=max_row,
                    max_column=max_column,
                    sampled_tokens=frozenset(sampled),
                    row_tokens=row_tokens,
                )
            )
    except Exception as exc:
        raise WorkbookFingerprintError(
            f"The uploaded XLSX could not be inspected: {exc}"
        ) from exc
    finally:
        workbook.close()
    return WorkbookFingerprint(file_name=file_name, sheets=tuple(sheets))


def _expected_sheets(parser_key: ParserKey) -> list[str]:
    if parser_key.schema_version != "neto.parser_key.v2":
        return [parser_key.target_sheet]
    sheets: list[str] = []
    for source in parser_key.raw_data.get("sources", []):
        if not isinstance(source, dict):
            continue
        locator = source.get("sheet_locator", {})
        args = locator.get("args", {}) if isinstance(locator, dict) else {}
        name = args.get("sheet_name") if isinstance(args, dict) else None
        if isinstance(name, str) and name.strip():
            sheets.append(name.strip())
    return list(dict.fromkeys(sheets))


def _source_file_names(parser_key: ParserKey) -> list[str]:
    metadata = parser_key.raw_data.get("metadata", {})
    names: list[str] = []
    if isinstance(metadata, dict):
        legacy = metadata.get("source_schedule_file")
        if isinstance(legacy, str):
            names.append(legacy)
        for item in metadata.get("source_files", []):
            if isinstance(item, dict) and isinstance(item.get("filename"), str):
                names.append(item["filename"])
    return names


def _similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, min(len(left), len(right)))


def _sheet_lookup(fingerprint: WorkbookFingerprint, expected: str) -> SheetFingerprint | None:
    exact = next((sheet for sheet in fingerprint.sheets if sheet.name == expected), None)
    if exact:
        return exact
    return next(
        (sheet for sheet in fingerprint.sheets if sheet.name.casefold() == expected.casefold()),
        None,
    )


def _max_coordinate_bounds(value: Any) -> tuple[int, int]:
    max_row = 0
    max_column = 0
    if isinstance(value, dict):
        for name, child in value.items():
            if isinstance(child, int) and not isinstance(child, bool):
                if name in {"row", "start_row", "end_row"}:
                    max_row = max(max_row, child)
            child_row, child_column = _max_coordinate_bounds(child)
            max_row = max(max_row, child_row)
            max_column = max(max_column, child_column)
    elif isinstance(value, list):
        for child in value:
            child_row, child_column = _max_coordinate_bounds(child)
            max_row = max(max_row, child_row)
            max_column = max(max_column, child_column)
    elif isinstance(value, str):
        for coordinate in re.findall(r"(?<![A-Z0-9_])\$?([A-Z]{1,3})\$?(\d+)", value):
            max_column = max(max_column, column_index_from_string(coordinate[0]))
            max_row = max(max_row, int(coordinate[1]))
        if re.fullmatch(r"[A-Z]{1,3}", value):
            max_column = max(max_column, column_index_from_string(value))
    return max_row, max_column


def _expected_dimensions(parser_key: ParserKey) -> tuple[int, int]:
    if parser_key.schema_version != "neto.parser_key.v2":
        columns = [
            column_index_from_string(column)
            for column in parser_key.field_mappings.values()
            if column
        ]
        return parser_key.data_start_row, max(columns, default=1)
    return _max_coordinate_bounds(parser_key.raw_data.get("record_sets", []))


def _header_compatibility(parser_key: ParserKey, fingerprint: WorkbookFingerprint) -> tuple[float, int]:
    if parser_key.schema_version == "neto.parser_key.v2":
        expected = _expected_sheets(parser_key)
        tokens = set().union(
            *(
                set(sheet.sampled_tokens)
                for name in expected
                if (sheet := _sheet_lookup(fingerprint, name)) is not None
            )
        ) if expected else set()
        identity = _identity_tokens(parser_key.key_name) | _identity_tokens(parser_key.tournament_name)
        overlap = identity & tokens
        return _similarity(identity, tokens), len(overlap)

    sheet = _sheet_lookup(fingerprint, parser_key.target_sheet)
    if sheet is None:
        return 0.0, 0
    header = set(sheet.row_tokens.get(parser_key.header_row, frozenset()))
    mapped = [field for field, column in parser_key.field_mappings.items() if column]
    hits = sum(bool(header & HEADER_HINTS[field]) for field in mapped)
    return hits / max(1, len(mapped)), hits


def _confidence(score: int, all_expected_sheets_present: bool) -> str:
    if score >= 78 and all_expected_sheets_present:
        return "High"
    if score >= 55 and all_expected_sheets_present:
        return "Medium"
    return "Low"


def rank_parser_keys(
    fingerprint: WorkbookFingerprint,
    parser_keys: Iterable[ParserKey],
    *,
    limit: int = 3,
) -> list[ParserKeySuggestion]:
    """Rank keys without executing their complete parsing pipelines."""

    ranked: list[ParserKeySuggestion] = []
    actual_names = set(fingerprint.sheet_names)
    actual_folded = {name.casefold() for name in actual_names}
    upload_tokens = _identity_tokens(Path(fingerprint.file_name).stem)

    for parser_key in parser_keys:
        expected = _expected_sheets(parser_key)
        exact_count = sum(name in actual_names for name in expected)
        compatible_count = sum(name.casefold() in actual_folded for name in expected)
        all_present = bool(expected) and compatible_count == len(expected)
        sheet_ratio = compatible_count / max(1, len(expected))
        sheet_score = round(52 * sheet_ratio)
        if exact_count == compatible_count and compatible_count:
            sheet_score += 3

        source_names = _source_file_names(parser_key)
        source_tokens = set().union(*(_identity_tokens(name) for name in source_names)) if source_names else set()
        key_tokens = _identity_tokens(parser_key.key_name) | _identity_tokens(parser_key.tournament_name)
        filename_similarity = max(
            _similarity(upload_tokens, source_tokens),
            _similarity(upload_tokens, key_tokens),
        )
        filename_score = round(22 * filename_similarity)

        header_similarity, header_hits = _header_compatibility(parser_key, fingerprint)
        header_score = round(16 * header_similarity)

        required_row, required_column = _expected_dimensions(parser_key)
        matched_sheets = [
            sheet for name in expected if (sheet := _sheet_lookup(fingerprint, name)) is not None
        ]
        dimension_ok = bool(matched_sheets) and all(
            sheet.max_row >= required_row and sheet.max_column >= required_column
            for sheet in matched_sheets
        )
        dimension_score = 7 if dimension_ok else (2 if matched_sheets else 0)

        score = min(100, sheet_score + filename_score + header_score + dimension_score)
        reasons: list[str] = []
        if all_present:
            reasons.append(
                "All expected sheets are present"
                if len(expected) > 1
                else f'Expected sheet "{expected[0]}" is present'
            )
        elif compatible_count:
            reasons.append(f"{compatible_count}/{len(expected)} expected sheets are present")
        else:
            reasons.append("Expected sheets are missing")
        if filename_similarity >= 0.55:
            reasons.append("Workbook name closely matches key metadata")
        elif filename_similarity >= 0.25:
            reasons.append("Workbook name partially matches key metadata")
        if header_hits:
            reasons.append("Sampled headers/content match the key structure")
        if dimension_ok:
            reasons.append("Sheet dimensions cover the key's required range")

        ranked.append(
            ParserKeySuggestion(
                parser_key=parser_key,
                score=score,
                confidence=_confidence(score, all_present),
                reasons=tuple(reasons[:3]),
            )
        )

    ranked.sort(
        key=lambda suggestion: (
            -suggestion.score,
            suggestion.parser_key.key_name.casefold(),
            suggestion.parser_key.parser_key_id.casefold(),
        )
    )
    return ranked[: max(0, limit)]
