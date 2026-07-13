from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

import app as app_module
from app import _presentation_dataframe
from parser.models import (
    IngestionMetadata,
    OfficialMatchMetadata,
    ParseResult,
    ParsedMatch,
)
from parser.presentation import canonical_view_dataframe, presentation_dataframe
from parser.ui_exports import canonical_csv_bytes, markdown_bytes, pdf_bytes, xlsx_bytes
from tests.helpers import valid_row, workbook_bytes


ROOT = Path(__file__).resolve().parents[1]
PARSER_KEY_ID = "cct_2026_sa3_public_schedule_v1"


def _download_states(app_test: AppTest) -> list[bool]:
    elements = app_test.get("download_button")
    assert len(elements) == 4
    return [bool(element.proto.disabled) for element in elements]


def test_preview_uses_natural_columns_and_sorts_by_utc() -> None:
    later = ParsedMatch(
        source_row=2,
        date_original="2026-07-10",
        time_original="18:30:00",
        timezone="UTC",
        start_time_utc="2026-07-10T18:30:00Z",
        team_a="Later A",
        team_b="Later B",
        stage="Playoffs",
        bo="BO3",
        match_label="M2",
    )
    earlier = ParsedMatch(
        source_row=3,
        date_original="2026-07-09",
        time_original="9:05",
        timezone="UTC",
        start_time_utc="2026-07-09T09:05:00Z",
        team_a="Earlier A",
        team_b="Earlier B",
        stage="Groups",
        bo="BO1",
        match_label="M1",
    )
    result = ParseResult(status="parsed", matches=[later, earlier])

    ascending = _presentation_dataframe(result)
    descending = _presentation_dataframe(result, descending=True)

    assert list(ascending.columns) == [
        "date",
        "time",
        "team_a",
        "team_b",
        "bo",
        "stage",
        "match_label",
        "timezone",
        "start_time_utc",
        "row_status",
    ]
    assert ascending.loc[0, "date"] == "09-07-2026"
    assert ascending.loc[0, "time"] == "09:05"
    assert ascending.loc[0, "team_a"] == "Earlier A"
    assert descending.loc[0, "team_a"] == "Later A"

    filtered = _presentation_dataframe(
        result,
        search="earlier",
        stages=["Groups"],
        bos=["BO1"],
        statuses=["valid"],
        date_format="MM-DD-YYYY",
        display_timezone="America/Lima",
    )
    assert len(filtered) == 1
    assert filtered.loc[0, "date"] == "07-09-2026"
    assert filtered.loc[0, "time"] == "04:05"


def test_filtered_view_exports_all_supported_formats(tmp_path: Path) -> None:
    match = ParsedMatch(
        source_row=2,
        date_original="2026-07-10",
        time_original="18:30:00",
        timezone="UTC",
        start_time_utc="2026-07-10T18:30:00Z",
        team_a="Alpha",
        team_b="Beta",
        stage="Final",
        bo="BO3",
        match_label="Grand Final",
    )
    result = ParseResult(status="parsed", matches=[match])
    canonical = canonical_view_dataframe(result)
    presentation = presentation_dataframe(canonical)

    csv_data = canonical_csv_bytes(canonical)
    markdown_data = markdown_bytes(presentation)
    xlsx_data = xlsx_bytes(presentation)
    pdf_data = pdf_bytes(presentation)

    assert csv_data.startswith(b"\xef\xbb\xbfdate_original,time_original,timezone")
    assert markdown_data.startswith(b"| Date | Time | Team A | Team B |")
    assert xlsx_data.startswith(b"PK")
    assert pdf_data.startswith(b"%PDF")

    workbook_path = tmp_path / "matches.xlsx"
    workbook_path.write_bytes(xlsx_data)
    workbook = load_workbook(workbook_path, read_only=True)
    assert workbook["NETO Matches"]["A2"].value == "10-07-2026"


def test_streamlit_upload_parse_preview_and_export_gating() -> None:
    app_test = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    app_test.run()

    assert not app_test.exception
    assert app_test.button(key="run_parse").disabled
    assert all(_download_states(app_test))
    fixture = (
        ROOT / "tests" / "fixtures" / "cct_2026_sa3_public_schedule.xlsx"
    ).read_bytes()
    app_test.file_uploader(key="schedule_upload").upload(
        "schedule.xlsx",
        fixture,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ).run()
    app_test.selectbox(key="parser_key_select").select(PARSER_KEY_ID).run()
    app_test.button(key="run_parse").click().run()

    assert not app_test.exception
    assert any("completed successfully" in item.value for item in app_test.success)
    assert len(app_test.dataframe) >= 1
    preview = app_test.dataframe[0].value
    assert list(preview.columns)[:6] == [
        "date",
        "time",
        "team_a",
        "team_b",
        "bo",
        "stage",
    ]
    assert preview.iloc[0]["date"] == "27-06-2026"
    assert app_test.segmented_control(key="preview_sort_order").value == "↑ Ascending"
    app_test.segmented_control(key="preview_sort_order").select("↓ Descending").run()
    descending_preview = app_test.dataframe[0].value
    assert descending_preview.iloc[0]["date"] == "09-07-2026"
    assert descending_preview.iloc[0]["time"] == "18:00"
    assert not any(_download_states(app_test))

    blocked = workbook_bytes([valid_row(team_a=None)])
    app_test.file_uploader(key="schedule_upload").set_value(
        (
            "blocked.xlsx",
            blocked,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    ).run()
    assert all(_download_states(app_test))
    app_test.button(key="run_parse").click().run()

    assert any("Parse blocked" in item.value for item in app_test.error)
    assert all(_download_states(app_test))


def test_streamlit_official_mode_fetches_and_exposes_metadata_filters(monkeypatch) -> None:
    official_match = ParsedMatch(
        source_row=1,
        source_sheet="lol_esports",
        date_original="2026-07-20",
        time_original="18:00:00",
        timezone="UTC",
        start_time_utc="2026-07-20T18:00:00Z",
        team_a="Alpha",
        team_b="Beta",
        stage="Groups",
        bo="BO3",
        match_label="Summer 2026",
        official=OfficialMatchMetadata(
            source_id="lol_esports",
            match_id="official-1",
            source_url="https://lolesports.com/en-US",
            competition_id="league-1",
            competition_name="Test League",
            match_state="scheduled",
            raw_state="unstarted",
        ),
    )
    fetched = ParseResult(
        status="parsed",
        matches=[official_match],
        notice="retrieval_strategy: riot_graphql_persisted_query.",
        ingestion=IngestionMetadata(
            method="official_web",
            source_id="lol_esports",
            source_label="League of Legends Esports",
            source_url="https://lolesports.com/en-US",
            strategy="riot_graphql_persisted_query",
            fetched_at_utc="2026-07-12T12:00:00Z",
            request_count=1,
            range_start="2026-07-20",
            range_end="2026-07-20",
            range_timezone="America/Lima",
        ),
    )
    monkeypatch.setattr("official_web.fetch_official_schedule", lambda request: fetched)

    app_test = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    app_test.run()
    app_test.segmented_control(key="ingestion_mode").select("Official Website").run()

    assert not app_test.exception
    assert app_test.selectbox(key="official_source_select").value == "lol_esports"
    assert not app_test.button(key="run_parse").disabled
    app_test.button(key="run_parse").click().run()

    assert not app_test.exception
    assert app_test.multiselect(key="preview_competition").options == ["Test League"]
    assert app_test.multiselect(key="preview_match_state").options == ["scheduled"]
    assert not any(_download_states(app_test))
    assert any("retrieval_strategy" in caption.value for caption in app_test.caption)


def test_official_cache_keeps_successes_but_not_failures(monkeypatch) -> None:
    calls = 0

    def successful_fetch(request):
        nonlocal calls
        calls += 1
        return ParseResult(status="parsed")

    app_module._cached_fetch_official.clear()
    monkeypatch.setattr(app_module, "fetch_official_schedule", successful_fetch)
    args = ("lol_esports", "2030-01-01", "2030-01-02", "UTC")
    app_module._cached_fetch_official(*args)
    app_module._cached_fetch_official(*args)
    assert calls == 1

    def failed_fetch(request):
        nonlocal calls
        calls += 1
        return ParseResult.failed("temporary failure")

    app_module._cached_fetch_official.clear()
    monkeypatch.setattr(app_module, "fetch_official_schedule", failed_fetch)
    with pytest.raises(app_module._OfficialFetchFailed):
        app_module._cached_fetch_official(*args)
    with pytest.raises(app_module._OfficialFetchFailed):
        app_module._cached_fetch_official(*args)
    assert calls == 3
