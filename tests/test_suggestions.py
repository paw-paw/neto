from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from parser.parser_keys import load_parser_keys
from parser.suggestions import (
    MAX_STRUCTURAL_PROBES,
    WorkbookFingerprintError,
    _identity_profile,
    _v2_probes,
    fingerprint_workbook,
    rank_parser_keys,
)
from tests.helpers import valid_row, workbook_bytes


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

    assert 1 <= len(suggestions) <= 3
    assert suggestions[0].parser_key.parser_key_id == expected_id
    assert suggestions[0].confidence in {"High", "Medium"}
    assert all(suggestion.score > 0 for suggestion in suggestions)
    assert [item.score for item in suggestions] == sorted(
        (item.score for item in suggestions), reverse=True
    )
    runner_up = suggestions[1].score if len(suggestions) > 1 else 0
    assert suggestions[0].margin == suggestions[0].score - runner_up
    assert suggestions[0].reasons


def test_invalid_workbook_and_empty_catalog_are_honest() -> None:
    with pytest.raises(WorkbookFingerprintError, match="could not be inspected"):
        fingerprint_workbook(b"not an xlsx", "broken.xlsx")

    valid = (FIXTURES / "cct_2026_sa3_public_schedule.xlsx").read_bytes()
    assert rank_parser_keys(fingerprint_workbook(valid), []) == []


@pytest.mark.parametrize(
    ("fixture_name", "new_name", "expected_id"),
    [
        ("exort_series_29.xlsx", "Exort Series 30.xlsx", "exort_series_29_v1"),
        (
            "cct_2026_sa3_public_schedule.xlsx",
            "[CCT 2026 SA4] Bracket, Schedule, Results.xlsx",
            "cct_2026_sa3_public_schedule_v1",
        ),
    ],
)
def test_cross_edition_reuse_is_ranked_and_explained(
    fixture_name: str, new_name: str, expected_id: str
) -> None:
    keys = load_parser_keys(ROOT / "parser_keys").keys
    fingerprint = fingerprint_workbook((FIXTURES / fixture_name).read_bytes(), new_name)

    suggestions = rank_parser_keys(fingerprint, keys)

    assert suggestions[0].parser_key.parser_key_id == expected_id
    assert suggestions[0].recommended
    assert any("different edition" in reason for reason in suggestions[0].reasons)


def test_no_match_and_zero_score_candidates_are_not_returned() -> None:
    keys = load_parser_keys(ROOT / "parser_keys").keys
    unknown = fingerprint_workbook(
        workbook_bytes([valid_row()], sheet_name="Unknown"),
        "Mystery workbook.xlsx",
    )

    assert rank_parser_keys(unknown, keys) == []

    stake = fingerprint_workbook(
        (FIXTURES / "stake_ranked_episode_3.xlsx").read_bytes(),
        "stake_ranked_episode_3.xlsx",
    )
    suggestions = rank_parser_keys(stake, keys)
    assert suggestions
    assert all(suggestion.score > 0 for suggestion in suggestions)
    assert len(suggestions) < 3


def _remove_worksheet_dimensions(payload: bytes) -> bytes:
    source = ZipFile(BytesIO(payload), "r")
    output = BytesIO()
    with source, ZipFile(output, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename.startswith("xl/worksheets/sheet"):
                content = re.sub(br"<dimension[^>]*/>", b"", content)
            target.writestr(item, content)
    return output.getvalue()


def test_missing_dimensions_do_not_bypass_the_sample_cap() -> None:
    payload = workbook_bytes([valid_row() for _ in range(80)])
    fingerprint = fingerprint_workbook(_remove_worksheet_dimensions(payload))
    sheet = fingerprint.sheets[0]

    assert sheet.max_row is None
    assert sheet.max_column is None
    assert max(sheet.row_tokens) == 32
    assert max(row for row, _ in sheet.sampled_cells) <= 32
    assert max(column for _, column in sheet.sampled_cells) <= 40


def test_profiles_are_unicode_aware_and_keep_brand_numbers() -> None:
    bitva = _identity_profile("BetBoom Битва Чемпионов: Сплит 4")
    united = _identity_profile("United21 Season 52")

    assert {"betboom", "битва", "чемпионов"} <= bitva.family
    assert bitva.editions == {"4"}
    assert "united21" in united.family
    assert united.editions == {"52"}


def test_v2_structural_profiles_respect_the_probe_cap() -> None:
    keys = load_parser_keys(ROOT / "parser_keys").keys

    for parser_key in keys:
        if parser_key.schema_version == "neto.parser_key.v2":
            assert len(_v2_probes(parser_key)) <= MAX_STRUCTURAL_PROBES
