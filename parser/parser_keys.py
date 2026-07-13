"""Load and validate ParserKey JSON files."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from openpyxl.utils.cell import column_index_from_string

from .models import ParserKey, ParserKeyCatalog, ParserKeyLoadError


SUPPORTED_SCHEMA_VERSION = "neto.parser_key.v0"
SUPPORTED_V2_SCHEMA_VERSION = "neto.parser_key.v2"
SUPPORTED_LAYOUT = "linear_table"
CONTRACT_ROOT = Path(__file__).resolve().parents[1]
V2_SCHEMA_PATH = CONTRACT_ROOT / "neto_parserkey_v2.schema.json"
OPERATOR_CATALOG_PATH = CONTRACT_ROOT / "neto_operator_catalog_v1.json"

SUPPORTED_V2_OPERATORS = {
    "cell.absolute",
    "cell.column",
    "cell.merged_origin",
    "cell.relative",
    "context.get",
    "datetime.excel_fraction_to_time",
    "datetime.excel_serial_to_date",
    "datetime.format_date",
    "datetime.format_time",
    "datetime.inject_year",
    "datetime.parse_date",
    "datetime.parse_time",
    "extract.regex",
    "extractor.output",
    "literal.value",
    "predicate.all",
    "predicate.any",
    "predicate.equals",
    "predicate.matches_regex",
    "predicate.not_empty",
    "record.row_index",
    "records.row_ranges",
    "records.row_scan",
    "records.tile_grid",
    "sheet.exact",
    "text.regex_extract",
    "text.regex_replace",
    "text.to_string",
    "text.trim",
}
FIELDS: tuple[str, ...] = (
    "date",
    "time",
    "team_a",
    "team_b",
    "stage",
    "bo",
    "match_label",
)
CRITICAL_FIELDS = {"date", "time", "team_a", "team_b"}
TEAM_FIELDS = {"team_a", "team_b"}


class ParserKeyValidationError(ValueError):
    """Raised when a ParserKey cannot be normalized safely."""


def _read_contract_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as file_handle:
            value = json.load(file_handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ParserKeyValidationError(
            f'Required ParserKey v2 contract file "{path.name}" could not be loaded: {exc}'
        ) from exc
    if not isinstance(value, dict):
        raise ParserKeyValidationError(
            f'Required ParserKey v2 contract file "{path.name}" must contain an object.'
        )
    return value


def _operator_nodes(value: Any) -> set[str]:
    operators: set[str] = set()
    if isinstance(value, dict):
        if isinstance(value.get("op"), str):
            operators.add(value["op"])
        for child in value.values():
            operators.update(_operator_nodes(child))
    elif isinstance(value, list):
        for child in value:
            operators.update(_operator_nodes(child))
    return operators


def _normalize_v2_parser_key(
    data: dict[str, Any], source_file: str | None
) -> ParserKey:
    schema = _read_contract_json(V2_SCHEMA_PATH)
    validation_errors = sorted(
        Draft202012Validator(schema).iter_errors(data),
        key=lambda error: list(error.absolute_path),
    )
    if validation_errors:
        error = validation_errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise ParserKeyValidationError(
            f"ParserKey v2 schema validation failed at {location}: {error.message}"
        )

    catalog = _read_contract_json(OPERATOR_CATALOG_PATH)
    catalog_operators = {
        operator
        for category in catalog.get("operators", {}).values()
        if isinstance(category, list)
        for operator in category
        if isinstance(operator, str)
    }
    declared_operators = set(data["runtime"]["required_operators"])
    actual_operators = _operator_nodes(data)

    missing_declarations = actual_operators - declared_operators
    if missing_declarations:
        raise ParserKeyValidationError(
            "ParserKey uses operator(s) absent from runtime.required_operators: "
            + ", ".join(sorted(missing_declarations))
            + "."
        )
    absent_from_catalog = declared_operators - catalog_operators
    if absent_from_catalog:
        raise ParserKeyValidationError(
            "ParserKey requires operator(s) absent from the operator catalog: "
            + ", ".join(sorted(absent_from_catalog))
            + "."
        )
    unsupported = declared_operators - SUPPORTED_V2_OPERATORS
    if unsupported:
        raise ParserKeyValidationError(
            "NETO runtime does not implement required operator(s): "
            + ", ".join(sorted(unsupported))
            + "."
        )
    if data["runtime"].get("required_plugins"):
        raise ParserKeyValidationError("NETO v0 does not load ParserKey plugins.")

    sources = data["sources"]
    sheet_names: list[str] = []
    for source in sources:
        locator = source["sheet_locator"]
        if locator["op"] != "sheet.exact":
            raise ParserKeyValidationError(
                f'Unsupported sheet locator "{locator["op"]}" in the initial v2 runtime.'
            )
        sheet_names.append(locator["args"]["sheet_name"])

    locator_types = sorted(
        {record_set["locator"]["op"] for record_set in data["record_sets"]}
    )
    return ParserKey(
        parser_key_id=data["parser_key_id"],
        key_name=data["key_name"],
        tournament_name=data["tournament"]["name"],
        base_timezone=data["tournament"]["base_timezone"],
        target_sheet=", ".join(sheet_names),
        layout_type="v2: " + ", ".join(locator_types),
        header_row=1,
        data_start_row=2,
        field_mappings={},
        forward_fill_rules={},
        schema_version=SUPPORTED_V2_SCHEMA_VERSION,
        source_file=source_file,
        raw_data=data,
    )


def _nested_value(data: dict[str, Any], path: tuple[str, ...]) -> tuple[bool, Any]:
    current: Any = data
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _semantic_value(
    data: dict[str, Any], name: str, nested_path: tuple[str, ...] | None = None
) -> Any:
    candidates: list[tuple[str, Any]] = []
    if name in data:
        candidates.append((name, data[name]))
    if nested_path:
        present, value = _nested_value(data, nested_path)
        if present:
            candidates.append((".".join(nested_path), value))

    if not candidates:
        raise ParserKeyValidationError(f'Missing required field "{name}".')
    if len(candidates) == 2 and candidates[0][1] != candidates[1][1]:
        raise ParserKeyValidationError(
            f'Conflicting values for "{name}" in {candidates[0][0]} and {candidates[1][0]}.'
        )
    return candidates[0][1]


def _required_string(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ParserKeyValidationError(f'Field "{name}" must be a string.')
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise ParserKeyValidationError(f'Field "{name}" cannot be empty.')
    return normalized


def _positive_row(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ParserKeyValidationError(f'Field "{name}" must be a positive integer.')
    return value


def _column_letter(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ParserKeyValidationError(
            f'Field mapping "{field_name}" must be a valid Excel column letter.'
        )
    column = value.strip().upper()
    try:
        index = column_index_from_string(column)
    except ValueError as exc:
        raise ParserKeyValidationError(
            f'Field mapping "{field_name}" has invalid Excel column "{value}".'
        ) from exc
    if index > 16384:
        raise ParserKeyValidationError(
            f'Field mapping "{field_name}" exceeds Excel column XFD.'
        )
    return column


def normalize_parser_key(data: dict[str, Any], source_file: str | None = None) -> ParserKey:
    if not isinstance(data, dict):
        raise ParserKeyValidationError("ParserKey root must be a JSON object.")

    schema_version = data.get("schema_version")
    if schema_version == SUPPORTED_V2_SCHEMA_VERSION:
        return _normalize_v2_parser_key(data, source_file)
    if schema_version is not None and schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ParserKeyValidationError(
            f'Unsupported schema_version "{schema_version}"; expected "{SUPPORTED_SCHEMA_VERSION}".'
        )

    parser_key_id = _required_string(
        _semantic_value(data, "parser_key_id"), "parser_key_id"
    )
    key_name = _required_string(_semantic_value(data, "key_name"), "key_name")
    tournament_name = _required_string(
        _semantic_value(data, "tournament_name", ("tournament", "name")),
        "tournament_name",
    )
    base_timezone = _required_string(
        _semantic_value(data, "base_timezone", ("tournament", "base_timezone")),
        "base_timezone",
        allow_empty=True,
    )
    target_sheet = _required_string(
        _semantic_value(
            data, "target_sheet", ("source_expectations", "target_sheet")
        ),
        "target_sheet",
    )
    layout_type = _required_string(
        _semantic_value(
            data, "layout_type", ("source_expectations", "layout_type")
        ),
        "layout_type",
    )
    if layout_type != SUPPORTED_LAYOUT:
        raise ParserKeyValidationError(
            f'Unsupported layout_type "{layout_type}"; NETO v0 supports only "{SUPPORTED_LAYOUT}".'
        )

    header_row = _positive_row(
        _semantic_value(data, "header_row", ("table", "header_row")), "header_row"
    )
    data_start_row = _positive_row(
        _semantic_value(data, "data_start_row", ("table", "data_start_row")),
        "data_start_row",
    )
    if data_start_row <= header_row:
        raise ParserKeyValidationError("data_start_row must be greater than header_row.")

    raw_mappings = _semantic_value(data, "field_mappings")
    if not isinstance(raw_mappings, dict):
        raise ParserKeyValidationError('Field "field_mappings" must be an object.')

    field_mappings: dict[str, str | None] = {}
    for field_name in FIELDS:
        value = raw_mappings.get(field_name)
        if field_name in CRITICAL_FIELDS and value is None:
            raise ParserKeyValidationError(
                f'Missing required field mapping "{field_name}".'
            )
        if value is None:
            field_mappings[field_name] = None
        else:
            field_mappings[field_name] = _column_letter(value, field_name)

    populated_columns = [column for column in field_mappings.values() if column]
    duplicates = sorted(
        column for column, count in Counter(populated_columns).items() if count > 1
    )
    if duplicates:
        raise ParserKeyValidationError(
            "Field mappings must use unique columns; duplicate column(s): "
            + ", ".join(duplicates)
            + "."
        )

    raw_forward_fill = _semantic_value(data, "forward_fill_rules")
    if not isinstance(raw_forward_fill, dict):
        raise ParserKeyValidationError('Field "forward_fill_rules" must be an object.')

    forward_fill_rules: dict[str, bool] = {}
    for field_name in FIELDS:
        value = raw_forward_fill.get(field_name, False)
        if not isinstance(value, bool):
            raise ParserKeyValidationError(
                f'Forward-fill rule "{field_name}" must be true or false.'
            )
        if field_name in TEAM_FIELDS and value:
            raise ParserKeyValidationError(
                f'Forward-fill is forbidden for "{field_name}".'
            )
        forward_fill_rules[field_name] = value

    return ParserKey(
        parser_key_id=parser_key_id,
        key_name=key_name,
        tournament_name=tournament_name,
        base_timezone=base_timezone,
        target_sheet=target_sheet,
        layout_type=layout_type,
        header_row=header_row,
        data_start_row=data_start_row,
        field_mappings=field_mappings,
        forward_fill_rules=forward_fill_rules,
        source_file=source_file,
        raw_data=data,
    )


def load_parser_keys(directory: str | Path) -> ParserKeyCatalog:
    key_directory = Path(directory)
    keys: list[ParserKey] = []
    errors: list[ParserKeyLoadError] = []

    if not key_directory.exists():
        return ParserKeyCatalog(
            keys=[],
            errors=[
                ParserKeyLoadError(
                    file_name=str(key_directory),
                    message="ParserKey directory does not exist.",
                )
            ],
        )

    for path in sorted(key_directory.glob("*.json"), key=lambda item: item.name.lower()):
        try:
            with path.open("r", encoding="utf-8-sig") as file_handle:
                data = json.load(file_handle)
            keys.append(normalize_parser_key(data, source_file=path.name))
        except (OSError, json.JSONDecodeError, ParserKeyValidationError) as exc:
            errors.append(ParserKeyLoadError(file_name=path.name, message=str(exc)))

    id_counts = Counter(key.parser_key_id for key in keys)
    duplicate_ids = {key_id for key_id, count in id_counts.items() if count > 1}
    if duplicate_ids:
        retained: list[ParserKey] = []
        for key in keys:
            if key.parser_key_id in duplicate_ids:
                errors.append(
                    ParserKeyLoadError(
                        file_name=key.source_file or key.parser_key_id,
                        message=f'Duplicate parser_key_id "{key.parser_key_id}".',
                    )
                )
            else:
                retained.append(key)
        keys = retained

    keys.sort(key=lambda key: (key.key_name.casefold(), key.parser_key_id.casefold()))
    errors.sort(key=lambda error: error.file_name.casefold())
    return ParserKeyCatalog(keys=keys, errors=errors)
