from __future__ import annotations

from pathlib import Path

import pytest

from parser.parser_keys import load_parser_keys
from parser.suggestions import (
    WorkbookFingerprintError,
    fingerprint_workbook,
    rank_parser_keys,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.mark.parametrize(
    ("fixture_name", "expected_id"),
    [
        ("betboom_rush_b_summit_part_four.xlsx", "betboom_rush_b_summit_part_four_v1"),
        ("cct_2026_contenders_eu6.xlsx", "cct_2026_contenders_europe_6_v1"),
        ("cct_2026_sa3_public_schedule.xlsx", "cct_2026_sa3_public_schedule_v1"),
        ("esports_world_cup_2026_dota2.xlsx", "esports_world_cup_2026_dota2_v1"),
        ("european_pro_league_season_39.xlsx", "european_pro_league_season_39_v1"),
        ("exort_series_29.xlsx", "exort_series_29_v1"),
        ("nodwin_clutch_series_10.xlsx", "nodwin_clutch_series_10_v1"),
        ("stake_ranked_episode_3.xlsx", "stake_ranked_episode_3_offline_main_event_v1"),
        ("xse_pro_league_guangzhou_2026.xlsx", "xse_pro_league_guangzhou_2026_v1"),
    ],
)
def test_structural_fingerprint_ranks_corpus_key_first(
    fixture_name: str, expected_id: str
) -> None:
    keys = load_parser_keys(ROOT / "parser_keys").keys
    data = (FIXTURES / fixture_name).read_bytes()

    fingerprint = fingerprint_workbook(data, fixture_name)
    suggestions = rank_parser_keys(fingerprint, keys)

    assert len(suggestions) == 3
    assert suggestions[0].parser_key.parser_key_id == expected_id
    assert suggestions[0].confidence == "High"
    assert suggestions[0].score >= suggestions[1].score
    assert suggestions[0].reasons


def test_invalid_workbook_and_empty_catalog_are_honest() -> None:
    with pytest.raises(WorkbookFingerprintError, match="could not be inspected"):
        fingerprint_workbook(b"not an xlsx", "broken.xlsx")

    valid = (FIXTURES / "cct_2026_sa3_public_schedule.xlsx").read_bytes()
    assert rank_parser_keys(fingerprint_workbook(valid), []) == []
