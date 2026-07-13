"""Rainbow Six Siege adapter over official month-level Next.js data."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from parser.models import OfficialMatchMetadata, ParsedMatch

from .errors import OfficialSchemaError
from .models import OfficialHttpClientProtocol, OfficialScheduleRequest, OfficialSource
from .next_data import parse_next_data
from .normalization import (
    finish_official_result,
    mapping,
    normalize_text,
    parse_utc,
    request_bounds,
    sequence,
    utc_fields,
)


STATE_MAP = {"1": "scheduled", "2": "live", "3": "completed"}


def _months_between(start: datetime, end: datetime) -> list[tuple[int, int]]:
    final = end - timedelta(microseconds=1)
    year, month = start.year, start.month
    months: list[tuple[int, int]] = []
    while (year, month) <= (final.year, final.month):
        months.append((year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return months


class RainbowSixSiegeAdapter:
    source = OfficialSource(
        source_id="rainbow_six_siege",
        label="Rainbow Six Siege",
        source_url="https://www.ubisoft.com/en-us/esports/rainbow-six/siege/calendar",
        strategy="r6_next_data_month",
        allowed_hosts=("www.ubisoft.com",),
    )

    def fetch(
        self,
        request: OfficialScheduleRequest,
        client: OfficialHttpClientProtocol,
    ):
        start_utc, end_utc = request_bounds(request)
        raw_by_id: dict[str, tuple[dict, str]] = {}
        fingerprints: dict[str, str] = {}
        conflict_ids: set[str] = set()

        for year, month in _months_between(start_utc, end_utc):
            source_url = f"{self.source.source_url}/{year:04d}-{month:02d}"
            html = client.get_text(source_url)
            payload = parse_next_data(html, "Rainbow Six")
            props = mapping(payload.get("props"), "__NEXT_DATA__.props")
            page_props = mapping(props.get("pageProps"), "__NEXT_DATA__.props.pageProps")
            page_data = mapping(page_props.get("pageData"), "pageProps.pageData")
            if page_data.get("year") != year or page_data.get("month") != month:
                raise OfficialSchemaError(
                    f"Rainbow Six month payload expected {year:04d}-{month:02d} but returned "
                    f"{page_data.get('year')}-{page_data.get('month')}."
                )
            for index, raw_match in enumerate(
                sequence(page_data.get("matches"), "pageProps.pageData.matches")
            ):
                match_data = mapping(raw_match, f"pageData.matches[{index}]")
                match_id = normalize_text(match_data.get("id"))
                if not match_id:
                    raise OfficialSchemaError(
                        f"Rainbow Six match at pageData.matches[{index}] has no id."
                    )
                fingerprint = json.dumps(
                    match_data, sort_keys=True, separators=(",", ":")
                )
                if match_id in raw_by_id:
                    if fingerprint != fingerprints[match_id]:
                        conflict_ids.add(match_id)
                        old = raw_by_id[match_id][0]
                        old_state = STATE_MAP.get(normalize_text(old.get("status")), "unknown")
                        new_state = STATE_MAP.get(
                            normalize_text(match_data.get("status")), "unknown"
                        )
                        rank = {"unknown": 0, "scheduled": 1, "live": 2, "completed": 3}
                        if rank[new_state] >= rank[old_state]:
                            raw_by_id[match_id] = (match_data, source_url)
                            fingerprints[match_id] = fingerprint
                    continue
                raw_by_id[match_id] = (match_data, source_url)
                fingerprints[match_id] = fingerprint

        matches: list[ParsedMatch] = []
        warning_specs: dict[str, list[tuple[str, str, str | None]]] = {}
        for match_id, (match_data, source_url) in raw_by_id.items():
            start = parse_utc(match_data.get("timestamp"), f"match[{match_id}].timestamp")
            if not start_utc <= start < end_utc:
                continue
            competition = mapping(
                match_data.get("competition"), f"match[{match_id}].competition"
            )
            team_a = mapping(match_data.get("team1", {}), f"match[{match_id}].team1")
            team_b = mapping(match_data.get("team2", {}), f"match[{match_id}].team2")
            raw_state = normalize_text(match_data.get("status"))
            state = STATE_MAP.get(raw_state, "unknown")
            count = match_data.get("matchFormatNumberOfGames")
            bo = f"BO{int(count)}" if isinstance(count, (int, float)) and count > 0 else ""
            time_is_tbd = bool(match_data.get("isTimeTBD"))
            date_text, time_text, utc_text = utc_fields(start)
            competition_name = normalize_text(competition.get("name"))
            match = ParsedMatch(
                source_row=0,
                source_sheet=self.source.source_id,
                date_original=date_text,
                time_original=time_text,
                timezone="UTC",
                start_time_utc=utc_text,
                team_a=normalize_text(team_a.get("name")) or "TBD",
                team_b=normalize_text(team_b.get("name")) or "TBD",
                stage=competition_name,
                bo=bo,
                match_label=f"Match {match_id}",
                official=OfficialMatchMetadata(
                    source_id=self.source.source_id,
                    match_id=match_id,
                    source_url=source_url,
                    competition_id=normalize_text(competition.get("id")),
                    competition_name=competition_name,
                    region=normalize_text(competition.get("subRegion")),
                    match_state=state,
                    raw_state=raw_state,
                    time_is_tbd=time_is_tbd,
                ),
            )
            matches.append(match)
            if time_is_tbd:
                warning_specs.setdefault(match_id, []).append(
                    (
                        "official_time_tbd",
                        "The official source marks this timestamp as provisional/TBD.",
                        "start_time_utc",
                    )
                )
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
