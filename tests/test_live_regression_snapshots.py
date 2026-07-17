from __future__ import annotations

import hashlib
import json
from pathlib import Path

from parser import load_parser_keys, parse_workbook
from parser.suggestions import fingerprint_workbook, rank_parser_keys


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "tests" / "fixtures" / "live_regressions"
MANIFEST = json.loads((SNAPSHOTS / "manifest.json").read_text(encoding="utf-8"))
PARSER_KEYS = load_parser_keys(ROOT / "parser_keys").keys
KEYS_BY_ID = {key.parser_key_id: key for key in PARSER_KEYS}


def test_directed_live_snapshots_remain_exportable_and_clean() -> None:
    for entry in MANIFEST["entries"]:
        path = SNAPSHOTS / entry["filename"]
        content = path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]

        suggestions = rank_parser_keys(
            fingerprint_workbook(content, entry["filename"]), PARSER_KEYS
        )
        assert suggestions[0].parser_key.parser_key_id == entry["parser_key_id"]

        result = parse_workbook(content, KEYS_BY_ID[entry["parser_key_id"]])
        assert result.exportable
        assert result.status == entry["status"]
        assert result.total_matches == entry["matches"]
        assert result.errors_count == entry["blocking_errors"] == 0
        assert result.warnings_count == entry["warnings"]
        assert sorted({issue.code for issue in result.issues}) == sorted(
            entry["issue_codes"]
        )

        for match in result.matches:
            for value in match.as_output_dict().values():
                assert not str(value).lstrip().startswith("=")
                assert "openpyxl" not in str(value).casefold()
