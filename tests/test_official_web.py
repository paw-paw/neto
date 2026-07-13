from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from official_web import OfficialScheduleRequest, fetch_official_schedule, list_official_sources
from official_web.normalization import request_bounds
from parser.export import result_to_csv_bytes


FIXTURES = Path(__file__).parent / "fixtures" / "official"


class FakeClient:
    def __init__(self, *, json_pages: list[dict] | None = None, html_by_key: dict[str, str] | None = None):
        self.json_pages = list(json_pages or [])
        self.html_by_key = html_by_key or {}
        self.request_count = 0
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get_json(self, url, *, params=None, headers=None):
        self.request_count += 1
        self.calls.append((url, params or {}))
        return self.json_pages.pop(0)

    def get_text(self, url, *, params=None, headers=None):
        self.request_count += 1
        self.calls.append((url, params or {}))
        key = str((params or {}).get("season") or url.rsplit("/", 1)[-1])
        return self.html_by_key[key]


def _request(source_id: str) -> OfficialScheduleRequest:
    return OfficialScheduleRequest(
        source_id=source_id,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 3),
        range_timezone="UTC",
    )


def _json_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_registry_lists_four_official_sources() -> None:
    assert [source.source_id for source in list_official_sources()] == [
        "lol_esports",
        "valorant_esports",
        "call_of_duty_league",
        "rainbow_six_siege",
    ]


def test_riot_adapters_paginate_normalize_states_and_keep_sport_independent() -> None:
    pages = [_json_fixture("riot_page_initial.json"), _json_fixture("riot_page_next.json")]
    lol_client = FakeClient(json_pages=pages)
    result = fetch_official_schedule(_request("lol_esports"), client=lol_client)

    assert result.status == "parsed"
    assert len(result.matches) == 3
    assert [match.official.match_state for match in result.matches] == [
        "scheduled",
        "completed",
        "live",
    ]
    assert result.matches[2].team_a == "TBD"
    assert result.ingestion.strategy == "riot_graphql_persisted_query"
    assert result.ingestion.request_count == 2
    first_variables = json.loads(lol_client.calls[0][1]["variables"])
    assert first_variables["sport"] == "lol"
    assert json.loads(lol_client.calls[1][1]["variables"])["pageToken"] == "next-page"

    val_client = FakeClient(json_pages=[_json_fixture("riot_page_initial.json"), _json_fixture("riot_page_next.json")])
    val_result = fetch_official_schedule(_request("valorant_esports"), client=val_client)
    assert val_result.status == "parsed"
    assert json.loads(val_client.calls[0][1]["variables"])["sport"] == "val"


def test_call_of_duty_extracts_next_data_and_warns_for_missing_bo() -> None:
    html = (FIXTURES / "cod_schedule.html").read_text(encoding="utf-8")
    client = FakeClient(html_by_key={"2026": html})
    result = fetch_official_schedule(_request("call_of_duty_league"), client=client)

    assert result.status == "parsed_with_warnings"
    assert len(result.matches) == 2
    assert {match.official.match_state for match in result.matches} == {
        "scheduled",
        "completed",
    }
    assert all(match.bo == "" for match in result.matches)
    assert {issue.code for issue in result.issues} == {"bo_missing"}


def test_rainbow_six_uses_month_payload_and_marks_provisional_time() -> None:
    html = (FIXTURES / "r6_calendar_2026_07.html").read_text(encoding="utf-8")
    client = FakeClient(html_by_key={"2026-07": html})
    result = fetch_official_schedule(_request("rainbow_six_siege"), client=client)

    assert result.status == "parsed_with_warnings"
    assert [match.official.match_state for match in result.matches] == [
        "scheduled",
        "live",
        "completed",
    ]
    assert result.matches[0].team_a == "TBD"
    assert result.matches[0].official.time_is_tbd
    assert [issue.code for issue in result.issues] == ["official_time_tbd"]


def test_legitimate_empty_schema_failure_range_limit_and_fixed_csv() -> None:
    empty_payload = {"data": {"esports": {"events": [], "pages": {"older": None, "newer": None}}}}
    empty = fetch_official_schedule(
        _request("lol_esports"), client=FakeClient(json_pages=[empty_payload])
    )
    assert empty.status == "parsed"
    assert empty.ingestion.legitimate_empty
    assert result_to_csv_bytes(empty).startswith(
        b"\xef\xbb\xbfdate_original,time_original,timezone,start_time_utc"
    )

    malformed = fetch_official_schedule(
        _request("lol_esports"), client=FakeClient(json_pages=[{"data": {}}])
    )
    assert malformed.status == "failed"
    assert "data.esports" in (malformed.technical_error or "")

    too_long = OfficialScheduleRequest(
        source_id="lol_esports",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 4, 1),
        range_timezone="UTC",
    )
    blocked = fetch_official_schedule(too_long, client=FakeClient())
    assert blocked.status == "failed"
    assert "limited to 90 days" in (blocked.technical_error or "")


def test_source_schema_failures_and_dst_range_boundaries() -> None:
    malformed_cod = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"season":{"key":"2026","label":"2026 Season"}}}}'
        "</script>"
    )
    cod = fetch_official_schedule(
        _request("call_of_duty_league"),
        client=FakeClient(html_by_key={"2026": malformed_cod}),
    )
    assert cod.status == "failed"
    assert "cdlEntireSeasonMatchCards" in (cod.technical_error or "")

    malformed_r6 = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"pageData":{"year":2026,"month":7}}}}'
        "</script>"
    )
    r6 = fetch_official_schedule(
        _request("rainbow_six_siege"),
        client=FakeClient(html_by_key={"2026-07": malformed_r6}),
    )
    assert r6.status == "failed"
    assert "pageProps.pageData.matches" in (r6.technical_error or "")

    start, end = request_bounds(
        OfficialScheduleRequest(
            source_id="lol_esports",
            start_date=date(2026, 3, 29),
            end_date=date(2026, 3, 29),
            range_timezone="Europe/Berlin",
        )
    )
    assert start.isoformat() == "2026-03-28T23:00:00+00:00"
    assert end.isoformat() == "2026-03-29T22:00:00+00:00"
