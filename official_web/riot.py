"""Independent LoL and VALORANT adapters over Riot's official GraphQL proxy."""

from __future__ import annotations

import json
import os
from datetime import timedelta

from parser.models import OfficialMatchMetadata, ParsedMatch

from .errors import OfficialSchemaError
from .models import (
    OfficialHttpClientProtocol,
    OfficialScheduleRequest,
    OfficialSource,
)
from .normalization import (
    finish_official_result,
    mapping,
    normalize_text,
    parse_utc,
    request_bounds,
    sequence,
    utc_fields,
)


DEFAULT_HOME_EVENTS_HASH = (
    "7246add6f577cf30b304e651bf9e25fc6a41fe49aeafb0754c16b5778060fc0a"
)
MAX_PAGES = 25
STATE_MAP = {
    "unstarted": "scheduled",
    "inprogress": "live",
    "completed": "completed",
}


class RiotScheduleAdapter:
    def __init__(self, source: OfficialSource, sport: str) -> None:
        self.source = source
        self.sport = sport

    def _request_page(
        self,
        client: OfficialHttpClientProtocol,
        request: OfficialScheduleRequest,
        page_token: str | None,
    ) -> dict:
        start_utc, end_utc = request_bounds(request)
        inclusive_end = end_utc - timedelta(milliseconds=1)
        variables: dict[str, object] = {
            "hl": "en-US",
            "sport": self.sport,
            "eventDateStart": start_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "eventDateEnd": inclusive_end.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "eventState": ["completed", "inProgress", "unstarted"],
            "eventType": "match",
            "pageSize": 300,
        }
        if page_token:
            variables["pageToken"] = page_token
        extensions = {
            "clientLibrary": {"name": "@apollo/client", "version": "4.1.2"},
            "persistedQuery": {
                "version": 1,
                "sha256Hash": os.getenv(
                    "NETO_RIOT_HOME_EVENTS_HASH", DEFAULT_HOME_EVENTS_HASH
                ),
            },
        }
        return client.get_json(
            f"{self.source.source_url}/api/gql",
            params={
                "operationName": "homeEvents",
                "variables": json.dumps(variables, separators=(",", ":")),
                "extensions": json.dumps(extensions, separators=(",", ":")),
            },
            headers={
                "Accept": "application/json",
                "x-apollo-operation-name": "homeEvents",
                "apollographql-client-name": "neto-official-schedule",
                "apollographql-client-version": "0.1",
            },
        )

    def fetch(
        self,
        request: OfficialScheduleRequest,
        client: OfficialHttpClientProtocol,
    ):
        start_utc, end_utc = request_bounds(request)
        queue: list[str | None] = [None]
        visited: set[str] = set()
        raw_by_id: dict[str, dict] = {}
        fingerprints: dict[str, str] = {}
        conflict_ids: set[str] = set()

        while queue:
            token = queue.pop(0)
            marker = token or "__initial__"
            if marker in visited:
                continue
            if len(visited) >= MAX_PAGES:
                raise OfficialSchemaError(
                    f"Riot pagination exceeded the {MAX_PAGES}-page safety limit."
                )
            visited.add(marker)
            payload = self._request_page(client, request, token)
            if payload.get("errors"):
                raise OfficialSchemaError(
                    f"Riot GraphQL returned errors: {payload['errors']}"
                )
            data = mapping(payload.get("data"), "data")
            esports = mapping(data.get("esports"), "data.esports")
            events = sequence(esports.get("events"), "data.esports.events")
            pages = mapping(esports.get("pages"), "data.esports.pages")
            if "older" not in pages or "newer" not in pages:
                raise OfficialSchemaError(
                    "Riot GraphQL pagination is missing pages.older or pages.newer."
                )
            for page_key in ("older", "newer"):
                next_token = pages.get(page_key)
                if next_token and str(next_token) not in visited:
                    queue.append(str(next_token))

            for index, raw_event in enumerate(events):
                event = mapping(raw_event, f"data.esports.events[{index}]")
                match_id = normalize_text(event.get("id"))
                if not match_id:
                    raise OfficialSchemaError(
                        f"Missing Riot match id at data.esports.events[{index}].id."
                    )
                fingerprint = json.dumps(event, sort_keys=True, separators=(",", ":"))
                if match_id in raw_by_id:
                    if fingerprint != fingerprints[match_id]:
                        conflict_ids.add(match_id)
                        old_state = STATE_MAP.get(
                            normalize_text(raw_by_id[match_id].get("state")).lower(),
                            "unknown",
                        )
                        new_state = STATE_MAP.get(
                            normalize_text(event.get("state")).lower(), "unknown"
                        )
                        rank = {"unknown": 0, "scheduled": 1, "live": 2, "completed": 3}
                        if rank[new_state] >= rank[old_state]:
                            raw_by_id[match_id] = event
                            fingerprints[match_id] = fingerprint
                    continue
                raw_by_id[match_id] = event
                fingerprints[match_id] = fingerprint

        matches: list[ParsedMatch] = []
        warning_specs: dict[str, list[tuple[str, str, str | None]]] = {}
        for match_id, event in raw_by_id.items():
            start = parse_utc(event.get("startTime"), f"event[{match_id}].startTime")
            if not start_utc <= start < end_utc:
                continue
            teams = sequence(event.get("matchTeams"), f"event[{match_id}].matchTeams")
            if len(teams) > 2:
                raise OfficialSchemaError(
                    f"Expected at most two teams at event[{match_id}].matchTeams."
                )
            names = [
                normalize_text(mapping(team, f"event[{match_id}].matchTeams").get("name"))
                or "TBD"
                for team in teams
            ]
            names += ["TBD"] * (2 - len(names))
            league = mapping(event.get("league"), f"event[{match_id}].league")
            tournament = mapping(
                event.get("tournament"), f"event[{match_id}].tournament"
            )
            match_data = mapping(event.get("match"), f"event[{match_id}].match")
            strategy = mapping(
                match_data.get("strategy"), f"event[{match_id}].match.strategy"
            )
            count = strategy.get("count")
            bo = f"BO{int(count)}" if isinstance(count, (int, float)) and count > 0 else ""
            raw_state = normalize_text(event.get("state"))
            normalized_state = STATE_MAP.get(raw_state.lower(), "unknown")
            date_text, time_text, utc_text = utc_fields(start)
            source_url = f"{self.source.source_url}/en-US"
            official = OfficialMatchMetadata(
                source_id=self.source.source_id,
                match_id=match_id,
                source_url=source_url,
                competition_id=normalize_text(league.get("id")),
                competition_name=normalize_text(league.get("name")),
                region=normalize_text(league.get("region")),
                match_state=normalized_state,
                raw_state=raw_state,
            )
            match = ParsedMatch(
                source_row=0,
                source_sheet=self.source.source_id,
                date_original=date_text,
                time_original=time_text,
                timezone="UTC",
                start_time_utc=utc_text,
                team_a=names[0],
                team_b=names[1],
                stage=normalize_text(event.get("blockName")),
                bo=bo,
                match_label=normalize_text(tournament.get("name")) or f"Match {match_id}",
                official=official,
            )
            matches.append(match)
            if normalized_state == "unknown":
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


LOL_SOURCE = OfficialSource(
    source_id="lol_esports",
    label="League of Legends Esports",
    source_url="https://lolesports.com",
    strategy="riot_graphql_persisted_query",
    allowed_hosts=("lolesports.com",),
)
VALORANT_SOURCE = OfficialSource(
    source_id="valorant_esports",
    label="VALORANT Esports",
    source_url="https://valorantesports.com",
    strategy="riot_graphql_persisted_query",
    allowed_hosts=("valorantesports.com",),
)


class LolEsportsAdapter(RiotScheduleAdapter):
    def __init__(self) -> None:
        super().__init__(LOL_SOURCE, "lol")


class ValorantEsportsAdapter(RiotScheduleAdapter):
    def __init__(self) -> None:
        super().__init__(VALORANT_SOURCE, "val")
