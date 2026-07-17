from __future__ import annotations

import json
from pathlib import Path

from wiki_ingestion import fetch_tournament_schedule, parse_tournament_url


FIXTURES = Path(__file__).parent / "fixtures" / "wiki"


class FakeClient:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.request_count = 0
        self.calls: list[tuple[str, dict[str, str], dict[str, str]]] = []

    def get_json(self, url, *, params=None, headers=None):
        self.request_count += 1
        self.calls.append((url, params or {}, headers or {}))
        return self.payloads.pop(0)


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_url_routing_is_strict_and_leaguepedia_only() -> None:
    leaguepedia = parse_tournament_url(
        "https://lol.fandom.com/wiki/LJL/2026_Season/Summer_Championship"
    )
    assert leaguepedia.provider_id == "leaguepedia"
    assert leaguepedia.game_label == "League of Legends"

    invalid = fetch_tournament_schedule(
        "https://liquipedia.net/dota2/The_International/2025"
    )
    assert invalid.status == "failed"
    assert "only Leaguepedia" in (invalid.technical_error or "")


def test_leaguepedia_cargo_partial_extraction_is_explicit() -> None:
    client = FakeClient([_fixture("leaguepedia_matches.json")])
    result = fetch_tournament_schedule(
        "https://lol.fandom.com/wiki/LJL/2026_Season/Summer_Championship",
        client=client,
    )

    assert result.status == "parsed_with_warnings"
    assert len(result.matches) == 1
    assert result.matches[0].start_time_utc == "2026-07-17T09:00:00Z"
    assert result.matches[0].team_b == "Burning Core Toyama"
    assert {issue.code for issue in result.issues} == {"wiki_required_field_ambiguous"}
    assert "Partial extraction" in (result.notice or "")
    assert client.calls[0][1]["action"] == "cargoquery"
    assert "MatchSchedule=MS" == client.calls[0][1]["tables"]


def test_no_schedule_unsupported_structure_and_api_failure() -> None:
    no_schedule = fetch_tournament_schedule(
        "https://lol.fandom.com/wiki/Empty/Event",
        client=FakeClient([{"cargoquery": []}]),
    )
    assert no_schedule.status == "parsed"
    assert no_schedule.ingestion.legitimate_empty
    assert "No schedule found" in (no_schedule.notice or "")

    unsupported = fetch_tournament_schedule(
        "https://lol.fandom.com/wiki/Broken/Event",
        client=FakeClient(
            [
                {
                    "cargoquery": [
                        {
                            "title": {
                                "MatchId": "broken",
                                "DateTimeUTC": "",
                                "Team1": "Alpha",
                                "Team2": "",
                                "HasTime": "0",
                            }
                        }
                    ]
                }
            ]
        ),
    )
    assert unsupported.status == "failed"
    assert "none had an unambiguous date" in (unsupported.technical_error or "")

    api_failure = fetch_tournament_schedule(
        "https://lol.fandom.com/wiki/Error/Event",
        client=FakeClient([{"error": {"code": "ratelimited", "info": "wait"}}]),
    )
    assert api_failure.status == "failed"
    assert "Cargo API error" in (api_failure.technical_error or "")
