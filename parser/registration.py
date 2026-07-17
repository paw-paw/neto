"""Validation and normalization for uploaded ParserKey JSON documents."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable

from .models import ParserKey
from .parser_keys import ParserKeyValidationError, normalize_parser_key


MAX_PARSER_KEY_BYTES = 1_000_000
MAX_RECORD_SETS = 64
MAX_OPERATOR_NODES = 5_000
MAX_LOCATOR_ANCHORS = 50_000
MAX_TOTAL_LOCATOR_ANCHORS = 100_000
MAX_REGEX_PATTERNS = 256
MAX_REGEX_PATTERN_CHARS = 512


class ParserKeyRegistrationError(ValueError):
    """Raised when an uploaded ParserKey cannot be registered."""


@dataclass(frozen=True)
class ValidatedParserKeyUpload:
    parser_key: ParserKey
    content: bytes


def _integer(value: object, label: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ParserKeyRegistrationError(
            f"ParserKey operator argument {label} must be an integer >= {minimum}."
        )
    return value


def _locator_anchor_count(locator: object) -> int:
    if not isinstance(locator, dict):
        raise ParserKeyRegistrationError("ParserKey record locator must be an object.")
    op = locator.get("op")
    args = locator.get("args")
    if not isinstance(args, dict):
        raise ParserKeyRegistrationError(
            f'ParserKey locator "{op}" requires object args.'
        )

    if op == "records.row_ranges":
        ranges = args.get("ranges")
        if not isinstance(ranges, list) or not ranges:
            raise ParserKeyRegistrationError(
                "records.row_ranges requires at least one range."
            )
        count = 0
        for index, row_range in enumerate(ranges):
            if not isinstance(row_range, dict):
                raise ParserKeyRegistrationError(
                    f"records.row_ranges range[{index}] must be an object."
                )
            start = _integer(row_range.get("start_row"), f"ranges[{index}].start_row")
            end = _integer(row_range.get("end_row"), f"ranges[{index}].end_row")
            if end < start:
                raise ParserKeyRegistrationError(
                    f"records.row_ranges range[{index}] ends before it starts."
                )
            count += end - start + 1
        return count

    if op == "records.row_scan":
        start = _integer(args.get("start_row"), "start_row")
        end = _integer(args.get("end_row"), "end_row")
        step = _integer(args.get("step", 1), "step")
        if end < start:
            raise ParserKeyRegistrationError(
                "records.row_scan end_row precedes start_row."
            )
        return ((end - start) // step) + 1

    if op == "records.tile_grid":
        tiles = args.get("tiles")
        if not isinstance(tiles, list) or not tiles:
            raise ParserKeyRegistrationError(
                "records.tile_grid requires at least one tile."
            )
        count = 0
        for index, tile in enumerate(tiles):
            offsets = tile.get("record_row_offsets") if isinstance(tile, dict) else None
            if not isinstance(offsets, list) or not offsets:
                raise ParserKeyRegistrationError(
                    f"records.tile_grid tile[{index}] requires record_row_offsets."
                )
            for offset in offsets:
                _integer(offset, f"tiles[{index}].record_row_offsets", minimum=0)
            count += len(offsets)
        return count

    raise ParserKeyRegistrationError(f'Unsupported ParserKey record locator "{op}".')


def _validate_upload_complexity(data: object) -> None:
    if not isinstance(data, dict) or data.get("schema_version") != "neto.parser_key.v2":
        return

    record_sets = data.get("record_sets")
    if not isinstance(record_sets, list):
        return
    if len(record_sets) > MAX_RECORD_SETS:
        raise ParserKeyRegistrationError(
            f"Uploaded ParserKeys are limited to {MAX_RECORD_SETS} record sets."
        )

    operator_count = 0
    pattern_count = 0
    stack: list[object] = [data]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            op = value.get("op")
            if isinstance(op, str):
                operator_count += 1
                args = value.get("args")
                if isinstance(args, dict) and op in {
                    "extract.regex",
                    "predicate.matches_regex",
                    "text.regex_extract",
                    "text.regex_replace",
                }:
                    patterns: list[object] = []
                    if "pattern" in args:
                        patterns.append(args["pattern"])
                    raw_patterns = args.get("patterns")
                    if isinstance(raw_patterns, list):
                        patterns.extend(
                            item.get("pattern") if isinstance(item, dict) else item
                            for item in raw_patterns
                        )
                    for pattern in patterns:
                        if not isinstance(pattern, str):
                            continue
                        pattern_count += 1
                        if len(pattern) > MAX_REGEX_PATTERN_CHARS:
                            raise ParserKeyRegistrationError(
                                "ParserKey regex patterns are limited to "
                                f"{MAX_REGEX_PATTERN_CHARS} characters."
                            )
                        try:
                            re.compile(pattern)
                        except re.error as exc:
                            raise ParserKeyRegistrationError(
                                f"ParserKey contains an invalid regex pattern: {exc}."
                            ) from exc
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)

    if operator_count > MAX_OPERATOR_NODES:
        raise ParserKeyRegistrationError(
            f"Uploaded ParserKeys are limited to {MAX_OPERATOR_NODES} operator nodes."
        )
    if pattern_count > MAX_REGEX_PATTERNS:
        raise ParserKeyRegistrationError(
            f"Uploaded ParserKeys are limited to {MAX_REGEX_PATTERNS} regex patterns."
        )

    total_anchors = 0
    for record_set in record_sets:
        if not isinstance(record_set, dict) or not record_set.get("enabled", True):
            continue
        anchors = _locator_anchor_count(record_set.get("locator"))
        if anchors > MAX_LOCATOR_ANCHORS:
            raise ParserKeyRegistrationError(
                "A ParserKey record locator may emit at most "
                f"{MAX_LOCATOR_ANCHORS} anchors."
            )
        total_anchors += anchors
    if total_anchors > MAX_TOTAL_LOCATOR_ANCHORS:
        raise ParserKeyRegistrationError(
            "An uploaded ParserKey may emit at most "
            f"{MAX_TOTAL_LOCATOR_ANCHORS} total anchors."
        )


def validate_parser_key_upload(
    content: bytes,
    *,
    source_file: str,
    existing_keys: Iterable[ParserKey] = (),
) -> ValidatedParserKeyUpload:
    if not content:
        raise ParserKeyRegistrationError("The uploaded ParserKey is empty.")
    if len(content) > MAX_PARSER_KEY_BYTES:
        raise ParserKeyRegistrationError("ParserKey JSON files are limited to 1 MB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ParserKeyRegistrationError("ParserKey JSON must be UTF-8 encoded.") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParserKeyRegistrationError(
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}."
        ) from exc
    except RecursionError as exc:
        raise ParserKeyRegistrationError("ParserKey JSON is nested too deeply.") from exc
    try:
        parser_key = normalize_parser_key(data, source_file=source_file)
    except (ParserKeyValidationError, KeyError, TypeError, RecursionError) as exc:
        raise ParserKeyRegistrationError(str(exc)) from exc
    _validate_upload_complexity(data)

    existing_ids = {key.parser_key_id for key in existing_keys}
    if parser_key.parser_key_id in existing_ids:
        raise ParserKeyRegistrationError(
            f'ParserKey id "{parser_key.parser_key_id}" is already registered; existing keys are never overwritten.'
        )
    canonical = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return ValidatedParserKeyUpload(parser_key=parser_key, content=canonical)
