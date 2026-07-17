"""Call of Duty League adapter for official Next.js schedule state."""

from __future__ import annotations

import json

from parser.models import OfficialMatchMetadata, ParsedMatch

from .errors import OfficialSchemaError
from .models import OfficialHttpClientProtocol, OfficialScheduleRequest, OfficialSource
from .next_data import parse_next_data
from .normalization import (
    compose_stage,
    finish_official_result,
    mapping,
    normalize_text,
    parse_utc,
    request_bounds,
    sequence,
    utc_fields,
)


STATE_MAP = {
    "SCHEDULED": "scheduled",
    "PENDING": "scheduled",
    "UPCOMING": "scheduled",
    "LIVE": "live",
    "IN_PROGRESS": "live",
    "COMPLETED": "completed",
    "FINISHED": "completed",
}


def _find_named_values(node: object, key: str) -> list[object]:
    found: list[object] = []
    if isinstance(node, dict):
        for name, value in node.items():
            if name == key:
                found.append(value)
            found.extend(_find_named_values(value, key))
    elif isinstance(node, list):
        for value in node:
            found.extend(_find_named_values(value, key))
    return found


def _contains_season(node: object, season: str) -> bool:
    if isinstance(node, dict):
        if normalize_text(node.get("key")) == season and (
            "Season" in normalize_text(node.get("label"))
            or "Season" in normalize_text(node.get("name"))
        ):
            return True
        return any(_contains_season(value, season) for value in node.values())
    if isinstance(node, list):
        return any(_contains_season(value, season) for value in node)
    return False


class CallOfDutyLeagueAdapter:
    source = OfficialSource(
        source_id="call_of_duty_league",
        label="Call of Duty League",
        source_url="https://callofdutyleague.com/en-us/schedule",
        strategy="cod_next_data_season",
        allowed_hosts=("callofdutyleague.com",),
    )

    def fetch(
        self,
        request: OfficialScheduleRequest,
        client: OfficialHttpClientProtocol,
    ):
        start_utc, end_utc = request_bounds(request)
        raw_by_id: dict[str, tuple[dict, dict, str]] = {}
        fingerprints: dict[str, str] = {}
        conflict_ids: set[str] = set()
        found_supported_season = False

        candidate_years = set(
            range(request.start_date.year, request.end_date.year + 1)
        )
        if request.end_date.month == 12:
            candidate_years.add(request.end_date.year + 1)
        for year in sorted(candidate_years):
            season = str(year)
            html = client.get_text(
                self.source.source_url,
                params={"season": season, "stage": "entire-season"},
            )
            payload = parse_next_data(html, "CDL")
            props = mapping(payload.get("props"), "__NEXT_DATA__.props")
            page_props = mapping(props.get("pageProps"), "__NEXT_DATA__.props.pageProps")
            if not _contains_season(page_props, season):
                continue
            found_supported_season = True
            card_values = _find_named_values(page_props, "cdlEntireSeasonMatchCards")
            if not card_values:
                raise OfficialSchemaError(
                    f'CDL season {season} exists but "cdlEntireSeasonMatchCards" was not found.'
                )
            source_url = f"{self.source.source_url}?season={season}&stage=entire-season"
            for card_index, raw_cards in enumerate(card_values):
                cards = mapping(raw_cards, f"cdlEntireSeasonMatchCards[{card_index}]")
                groups = sequence(
                    cards.get("completedMatches", []),
                    f"cdlEntireSeasonMatchCards[{card_index}].completedMatches",
                ) + sequence(
                    cards.get("upcomingMatches", []),
                    f"cdlEntireSeasonMatchCards[{card_index}].upcomingMatches",
                )
                for group_index, raw_group in enumerate(groups):
                    group = mapping(raw_group, f"cdl group[{group_index}]")
                    for raw_match in sequence(group.get("matches"), "cdl group.matches"):
                        match_data = mapping(raw_match, "cdl group.matches[]")
                        official_match = mapping(match_data.get("match"), "cdl match.match")
                        match_id = normalize_text(official_match.get("id"))
                        if not match_id:
                            raise OfficialSchemaError("CDL match is missing match.id.")
                        fingerprint = json.dumps(
                            match_data, sort_keys=True, separators=(",", ":")
                        )
                        if match_id in raw_by_id:
                            if fingerprint != fingerprints[match_id]:
                                conflict_ids.add(match_id)
                                old = raw_by_id[match_id][0]
                                old_state = STATE_MAP.get(
                                    normalize_text(mapping(old.get("match"), "match").get("status")).upper(),
                                    "unknown",
                                )
                                new_state = STATE_MAP.get(
                                    normalize_text(official_match.get("status")).upper(),
                                    "unknown",
                                )
                                rank = {"unknown": 0, "scheduled": 1, "live": 2, "completed": 3}
                                if rank[new_state] >= rank[old_state]:
                                    raw_by_id[match_id] = (match_data, group, source_url)
                                    fingerprints[match_id] = fingerprint
                            continue
                        raw_by_id[match_id] = (match_data, group, source_url)
                        fingerprints[match_id] = fingerprint

        if not found_supported_season:
            # The response contract was valid; the requested seasons simply are not published.
            raw_by_id = {}

        matches: list[ParsedMatch] = []
        warning_specs: dict[str, list[tuple[str, str, str | None]]] = {}
        for match_id, (match_data, group, source_url) in raw_by_id.items():
            official_match = mapping(match_data.get("match"), f"match[{match_id}].match")
            timestamp = (
                match_data.get("startTime")
                or match_data.get("startDate")
                or official_match.get("playTime")
            )
            start = parse_utc(timestamp, f"match[{match_id}].startTime")
            if not start_utc <= start < end_utc:
                continue
            home = mapping(match_data.get("homeTeamCard", {}), f"match[{match_id}].homeTeamCard")
            away = mapping(match_data.get("awayTeamCard", {}), f"match[{match_id}].awayTeamCard")
            raw_state = normalize_text(official_match.get("status"))
            state = STATE_MAP.get(raw_state.upper(), "unknown")
            competition_name = normalize_text(group.get("title")) or "Call of Duty League"
            subtitle = normalize_text(group.get("subtitle"))
            stage = compose_stage(competition_name, subtitle)
            date_text, time_text, utc_text = utc_fields(start)
            match = ParsedMatch(
                source_row=0,
                source_sheet=self.source.source_id,
                date_original=date_text,
                time_original=time_text,
                timezone="UTC",
                start_time_utc=utc_text,
                team_a=normalize_text(home.get("name")) or "TBD",
                team_b=normalize_text(away.get("name")) or "TBD",
                stage=stage,
                bo="",
                match_label=f"Match {match_id}",
                official=OfficialMatchMetadata(
                    source_id=self.source.source_id,
                    match_id=match_id,
                    source_url=source_url,
                    competition_id=normalize_text(group.get("competitionId")),
                    competition_name=competition_name,
                    match_state=state,
                    raw_state=raw_state,
                ),
            )
            matches.append(match)
            if state == "unknown":
                warning_specs.setdefault(match_id, []).append(
                    (
                        "unknown_match_state",
                        f'Unrecognized official match state "{raw_state}" was preserved.',
                        None,
                    )
                )

        return finish_official_result(
            source=self.source,
            request=request,
            client=client,
            matches=matches,
            warning_specs=warning_specs,
            conflict_ids=conflict_ids,
        )
