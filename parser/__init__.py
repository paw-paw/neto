"""Reusable NETO parser interfaces."""

from .engine import parse_workbook
from .export import matches_dataframe, result_to_csv_bytes
from .models import (
    IngestionMetadata,
    OUTPUT_COLUMNS,
    OfficialMatchMetadata,
    ParseResult,
    ParsedMatch,
    ParserKey,
    ParserKeyCatalog,
    ParserKeyLoadError,
    ValidationIssue,
)
from .parser_keys import load_parser_keys, normalize_parser_key
from .registration import validate_parser_key_upload
from .suggestions import fingerprint_workbook, rank_parser_keys

__all__ = [
    "OUTPUT_COLUMNS",
    "IngestionMetadata",
    "OfficialMatchMetadata",
    "ParseResult",
    "ParsedMatch",
    "ParserKey",
    "ParserKeyCatalog",
    "ParserKeyLoadError",
    "ValidationIssue",
    "load_parser_keys",
    "matches_dataframe",
    "normalize_parser_key",
    "parse_workbook",
    "result_to_csv_bytes",
    "fingerprint_workbook",
    "rank_parser_keys",
    "validate_parser_key_upload",
]
