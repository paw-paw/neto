from __future__ import annotations

import hashlib
import json
from pathlib import Path

from parser import load_parser_keys, parse_workbook


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
MANIFEST = FIXTURES / "neto_parserkey_v2_corpus_manifest.json"

FIXTURE_BY_KEY = {
    "betboom_rush_b_summit_part_four_v1": "betboom_rush_b_summit_part_four.xlsx",
    "exort_series_29_v1": "exort_series_29.xlsx",
    "cct_2026_contenders_europe_6_v1": "cct_2026_contenders_eu6.xlsx",
    "xse_pro_league_guangzhou_2026_v1": "xse_pro_league_guangzhou_2026.xlsx",
    "stake_ranked_episode_3_offline_main_event_v1": "stake_ranked_episode_3.xlsx",
    "esports_world_cup_2026_dota2_v1": "esports_world_cup_2026_dota2.xlsx",
    "european_pro_league_season_39_v1": "european_pro_league_season_39.xlsx",
    "nodwin_clutch_series_10_v1": "nodwin_clutch_series_10.xlsx",
}


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _catalog_by_id() -> dict:
    catalog = load_parser_keys(ROOT / "parser_keys")
    assert catalog.errors == []
    return {key.parser_key_id: key for key in catalog.keys}


def _matching_record(result, smoke_check: dict):
    candidates = [
        match for match in result.matches if match.source_row == smoke_check["source_row"]
    ]
    if "sheet" in smoke_check:
        candidates = [
            match for match in candidates if match.source_sheet == smoke_check["sheet"]
        ]
    if "tile" in smoke_check:
        candidates = [
            match for match in candidates if match.tile_origin == smoke_check["tile"]
        ]
    assert len(candidates) == 1, smoke_check
    return candidates[0]


def test_v2_keys_validate_and_cover_declared_source_hashes() -> None:
    keys = _catalog_by_id()
    assert set(FIXTURE_BY_KEY) <= set(keys)

    for key_id, fixture_name in FIXTURE_BY_KEY.items():
        key = keys[key_id]
        assert key.schema_version == "neto.parser_key.v2"
        expected_hash = key.raw_data["metadata"]["source_files"][0]["sha256"]
        actual_hash = hashlib.sha256((FIXTURES / fixture_name).read_bytes()).hexdigest()
        assert actual_hash == expected_hash


def test_entire_v2_corpus_matches_counts_and_smoke_checks() -> None:
    keys = _catalog_by_id()
    manifest = _manifest()
    total_records = 0

    for entry in manifest["entries"]:
        key_id = entry["parser_key_id"]
        result = parse_workbook(
            (FIXTURES / FIXTURE_BY_KEY[key_id]).read_bytes(), keys[key_id]
        )

        assert result.exportable, (
            key_id,
            result.status,
            [(issue.code, issue.source_sheet, issue.source_row) for issue in result.issues],
        )
        assert result.total_matches == entry["expected_record_count"]
        assert not any(
            issue.severity == "blocking_error" for issue in result.issues
        )
        total_records += result.total_matches

        for smoke_check in entry["smoke_checks"]:
            match = _matching_record(result, smoke_check)
            for field_name, expected in smoke_check.items():
                if field_name in {"source_row", "sheet", "tile"}:
                    continue
                output_name = {
                    "date": "date_original",
                    "time": "time_original",
                }.get(field_name, field_name)
                assert getattr(match, output_name) == expected
            assert match.start_time_utc.endswith("Z")
            assert match.field_provenance["date"]["record_set"]

    assert total_records == manifest["total_expected_records"] == 363
