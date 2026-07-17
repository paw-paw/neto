from __future__ import annotations

import json
from pathlib import Path

import pytest

from parser.registration import (
    ParserKeyRegistrationError,
    validate_parser_key_upload,
)
from tests.test_parser_keys import nested_key_data


ROOT = Path(__file__).resolve().parents[1]


def _validated(key_id: str = "uploaded_key"):
    data = nested_key_data()
    data["parser_key_id"] = key_id
    return validate_parser_key_upload(
        json.dumps(data).encode(), source_file="uploaded.json"
    )


def _v2_data() -> dict:
    return json.loads(
        (
            ROOT
            / "parser_keys"
            / "betboom_rush_b_summit_part_four_v1.json"
        ).read_text(encoding="utf-8")
    )


def test_uploaded_key_uses_real_validator_and_rejects_bad_json_and_duplicates() -> None:
    validated = _validated()
    assert validated.parser_key.parser_key_id == "uploaded_key"
    assert validated.content.endswith(b"\n")

    with pytest.raises(ParserKeyRegistrationError, match="Invalid JSON"):
        validate_parser_key_upload(b"{broken", source_file="broken.json")
    with pytest.raises(ParserKeyRegistrationError, match="already registered"):
        validate_parser_key_upload(
            validated.content,
            source_file="duplicate.json",
            existing_keys=[validated.parser_key],
        )


def test_current_v2_corpus_key_is_within_temporary_upload_policy() -> None:
    data = _v2_data()
    data["parser_key_id"] = "temporary_v2_upload_v1"

    validated = validate_parser_key_upload(
        json.dumps(data).encode(), source_file="temporary_v2_upload.json"
    )

    assert validated.parser_key.parser_key_id == "temporary_v2_upload_v1"


def test_uploaded_key_rejects_excessive_locator_work() -> None:
    data = _v2_data()
    data["parser_key_id"] = "oversized_key_v1"
    data["record_sets"][0]["locator"]["args"]["ranges"][0][
        "end_row"
    ] = 2_000_000_000

    with pytest.raises(ParserKeyRegistrationError, match="at most 50000 anchors"):
        validate_parser_key_upload(
            json.dumps(data).encode(), source_file="oversized.json"
        )


def test_uploaded_key_rejects_excessive_regex_patterns() -> None:
    data = _v2_data()
    data["parser_key_id"] = "oversized_regex_key_v1"
    transform = data["record_sets"][0]["fields"]["team_a"]["value"]["transforms"]
    transform.append(
        {
            "op": "text.regex_replace",
            "args": {"pattern": "a" * 513, "replacement": ""},
        }
    )
    data["runtime"]["required_operators"].append("text.regex_replace")

    with pytest.raises(ParserKeyRegistrationError, match="limited to 512 characters"):
        validate_parser_key_upload(
            json.dumps(data).encode(), source_file="oversized_regex.json"
        )
