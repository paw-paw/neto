from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

import app as app_module
from app import (
    _presentation_dataframe,
    _timezone_options,
    _validated_browser_timezone,
)
from google_sheets import FetchedGoogleSheet, parse_google_sheets_url
from parser.models import (
    IngestionMetadata,
    OfficialMatchMetadata,
    ParseResult,
    ParsedMatch,
)
from parser.presentation import canonical_view_dataframe, presentation_dataframe
from parser.ui_exports import canonical_csv_bytes, markdown_bytes, pdf_bytes, xlsx_bytes
from tests.helpers import valid_row, workbook_bytes
from tests.test_parser_keys import nested_key_data


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

    descending = _presentation_dataframe(result)
    ascending = _presentation_dataframe(result, descending=False)

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
    assert app_test.button(key="run_parse").disabled
    assert app_test.checkbox(key="parser_key_confirm").value is False
    app_test.checkbox(key="parser_key_confirm").check().run()
    assert not app_test.button(key="run_parse").disabled
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
    assert preview.iloc[0]["date"] == "09-07-2026"
    assert preview.iloc[0]["time"] == "18:00"
    assert app_test.segmented_control(key="preview_sort_order").value == "↓ Descending"
    app_test.segmented_control(key="preview_sort_order").select("↑ Ascending").run()
    ascending_preview = app_test.dataframe[0].value
    assert ascending_preview.iloc[0]["date"] == "27-06-2026"
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
    assert app_test.button(key="run_parse").disabled
    app_test.checkbox(key="parser_key_confirm").check().run()
    app_test.button(key="run_parse").click().run()

    assert any("Parse blocked" in item.value for item in app_test.error)
    assert all(_download_states(app_test))


def test_streamlit_google_sheet_reuses_workbook_parse_flow(monkeypatch) -> None:
    fixture = (
        ROOT / "tests" / "fixtures" / "cct_2026_sa3_public_schedule.xlsx"
    ).read_bytes()
    url = (
        "https://docs.google.com/spreadsheets/d/"
        "1ouauktbqfjv1nW3RQTFucPU4zy85wQLo7ddp2SbGYc8/edit?gid=417448219"
    )
    fetched = FetchedGoogleSheet(
        reference=parse_google_sheets_url(url),
        file_name="CCT 2026 SA3 Public Schedule.xlsx",
        content=fixture,
        fetched_at_utc="2026-07-16T12:00:00Z",
    )
    monkeypatch.setattr("google_sheets.fetch_google_sheet", lambda value: fetched)

    app_test = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    app_test.run()
    app_test.text_input(key="google_sheets_url").input(url).run()
    app_test.button(key="load_google_sheet").click().run()

    assert not app_test.exception
    assert any("CCT 2026 SA3 Public Schedule.xlsx" in item.value for item in app_test.success)
    app_test.selectbox(key="parser_key_select").select(PARSER_KEY_ID).run()
    app_test.checkbox(key="parser_key_confirm").check().run()
    app_test.button(key="run_parse").click().run()

    assert not app_test.exception
    assert any("completed successfully" in item.value for item in app_test.success)
    assert any("google_sheets_public_xlsx_export" in item.value for item in app_test.markdown)
    assert not any(_download_states(app_test))


def test_ingestion_methods_have_individual_help_and_timezones_are_searchable() -> None:
    app_test = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    app_test.run()

    for key in (
        "ingestion_google_sheets",
        "ingestion_official_website",
        "ingestion_tournament_page",
    ):
        assert app_test.button(key=key).proto.help

    assert _validated_browser_timezone("Europe/Madrid") == "Europe/Madrid"
    assert _validated_browser_timezone("Not/A_Zone") == "UTC"
    options = _timezone_options("Asia/Tokyo")
    assert options[0] == "Asia/Tokyo"
    assert "America/Lima" in options
    assert "Europe/Berlin" in options


def test_parserkey_creator_and_session_registration_are_available_immediately() -> None:
    app_test = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    app_test.run()

    links = app_test.get("link_button")
    assert any("ParserKey Creator" in link.label for link in links)
    uploaded = nested_key_data()
    uploaded["parser_key_id"] = "session_uploaded_key"
    uploaded["key_name"] = "Session Uploaded Key"
    app_test.file_uploader(key="parser_key_upload").upload(
        "session_uploaded_key.json",
        json.dumps(uploaded).encode(),
        "application/json",
    ).run()
    app_test.button(key="register_parser_key").click().run()
    assert any(
        "available for this session" in notice.value
        for notice in app_test.success
    )
    app_test.run()

    assert not app_test.exception
    assert any(
        "session_uploaded_key" in option
        for option in app_test.selectbox(key="parser_key_select").options
    )


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
    app_test.button(key="ingestion_official_website").click().run()

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


def test_streamlit_tournament_page_mode_reuses_preview_and_export(monkeypatch) -> None:
    wiki_match = ParsedMatch(
        source_row=1,
        source_sheet="Test/Event",
        date_original="2026-07-20",
        time_original="18:00:00",
        timezone="UTC",
        start_time_utc="2026-07-20T18:00:00Z",
        team_a="Alpha",
        team_b="Beta",
        stage="Final",
        bo="BO5",
        match_label="wiki-1",
        official=OfficialMatchMetadata(
            source_id="leaguepedia_league_of_legends",
            match_id="wiki-1",
            source_url="https://lol.fandom.com/wiki/Test/Event",
            competition_name="Event",
            match_state="scheduled",
        ),
    )
    fetched = ParseResult(
        status="parsed",
        matches=[wiki_match],
        notice="Complete extraction: 1 match(es).",
        ingestion=IngestionMetadata(
            method="wiki_tournament",
            source_id="leaguepedia_league_of_legends",
            source_label="Leaguepedia — League of Legends",
            source_url="https://lol.fandom.com/wiki/Test/Event",
            strategy="leaguepedia_mediawiki_cargo_matchschedule",
            fetched_at_utc="2026-07-15T12:00:00Z",
            request_count=1,
        ),
    )
    app_module._cached_fetch_tournament.clear()
    monkeypatch.setattr(
        "wiki_ingestion.fetch_tournament_schedule", lambda *args, **kwargs: fetched
    )

    app_test = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    app_test.run()
    app_test.button(key="ingestion_tournament_page").click().run()
    app_test.text_input(key="tournament_page_url").input(
        "https://lol.fandom.com/wiki/Test/Event"
    ).run()

    assert not app_test.button(key="run_parse").disabled
    app_test.button(key="run_parse").click().run()
    assert not app_test.exception
    assert app_test.dataframe[0].value.iloc[0]["team_a"] == "Alpha"
    assert not any(_download_states(app_test))
    assert any("Complete extraction" in caption.value for caption in app_test.caption)
