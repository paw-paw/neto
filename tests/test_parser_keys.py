from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from parser.parser_keys import load_parser_keys, normalize_parser_key


ROOT = Path(__file__).resolve().parents[1]


def nested_key_data() -> dict:
    return {
        "schema_version": "neto.parser_key.v0",
        "parser_key_id": "nested_key",
        "key_name": "Nested Key",
        "tournament": {
            "name": "Nested Tournament",
            "base_timezone": "America/Lima",
        },
        "source_expectations": {
            "target_sheet": "Schedule",
            "layout_type": "linear_table",
        },
        "table": {"header_row": 1, "data_start_row": 2},
        "field_mappings": {
            "date": "A",
            "time": "B",
            "team_a": "C",
            "team_b": "D",
            "stage": "E",
            "bo": "F",
            "match_label": "G",
        },
        "forward_fill_rules": {"date": True},
    }


def flat_key_data() -> dict:
    data = nested_key_data()
    return {
        "parser_key_id": "flat_key",
        "key_name": "Flat Key",
        "tournament_name": "Flat Tournament",
        "base_timezone": "UTC",
        "target_sheet": "Matches",
        "layout_type": "linear_table",
        "header_row": 3,
        "data_start_row": 4,
        "field_mappings": data["field_mappings"],
        "forward_fill_rules": {"stage": True},
    }


def test_normalizes_nested_and_flat_shapes() -> None:
    nested = normalize_parser_key(nested_key_data())
    flat = normalize_parser_key(flat_key_data())

    assert nested.tournament_name == "Nested Tournament"
    assert nested.field_mappings["date"] == "A"
    assert nested.forward_fill_rules["time"] is False
    assert flat.tournament_name == "Flat Tournament"
    assert flat.target_sheet == "Matches"
    assert flat.header_row == 3


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda data: data.pop("parser_key_id"), "parser_key_id"),
        (
            lambda data: data["source_expectations"].update(
                {"layout_type": "horizontal_blocks"}
            ),
            "linear_table",
        ),
        (lambda data: data["field_mappings"].update({"date": "A1"}), "invalid Excel"),
        (lambda data: data["field_mappings"].update({"team_b": "C"}), "unique"),
        (
            lambda data: data["forward_fill_rules"].update({"team_a": True}),
            "forbidden",
        ),
    ],
)
def test_rejects_invalid_keys(mutator, expected: str) -> None:
    data = copy.deepcopy(nested_key_data())
    mutator(data)
    with pytest.raises(ValueError, match=expected):
        normalize_parser_key(data)


def test_loader_isolates_bad_files_and_duplicate_ids(tmp_path) -> None:
    valid = nested_key_data()
    (tmp_path / "valid.json").write_text(json.dumps(valid), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{broken", encoding="utf-8")
    duplicate = copy.deepcopy(valid)
    duplicate["key_name"] = "Duplicate"
    (tmp_path / "duplicate.json").write_text(
        json.dumps(duplicate), encoding="utf-8"
    )

    catalog = load_parser_keys(tmp_path)

    assert catalog.keys == []
    assert len(catalog.errors) == 3
    assert any("Duplicate parser_key_id" in error.message for error in catalog.errors)
    assert any(error.file_name == "broken.json" for error in catalog.errors)


def test_missing_optional_mappings_become_null() -> None:
    data = flat_key_data()
    data["field_mappings"] = {
        "date": "A",
        "time": "B",
        "team_a": "C",
        "team_b": "D",
    }

    key = normalize_parser_key(data)

    assert key.field_mappings["stage"] is None
    assert key.field_mappings["bo"] is None
    assert key.field_mappings["match_label"] is None


def test_v2_schema_validation_rejects_missing_contract_sections() -> None:
    data = json.loads(
        (ROOT / "parser_keys" / "betboom_rush_b_summit_part_four_v1.json").read_text(
            encoding="utf-8"
        )
    )
    data.pop("runtime")

    with pytest.raises(ValueError, match="schema validation failed"):
        normalize_parser_key(data)


def test_v2_runtime_rejects_catalogued_but_unimplemented_operator() -> None:
    data = json.loads(
        (ROOT / "parser_keys" / "betboom_rush_b_summit_part_four_v1.json").read_text(
            encoding="utf-8"
        )
    )
    data["runtime"]["required_operators"].append("text.collapse_whitespace")

    with pytest.raises(ValueError, match="does not implement"):
        normalize_parser_key(data)
