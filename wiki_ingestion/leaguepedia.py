"""Leaguepedia tournament adapter using the public MediaWiki Cargo API."""

from __future__ import annotations

from typing import Any

from parser.models import OfficialMatchMetadata, ParsedMatch

from .errors import WikiApiError
from .models import WikiHttpClientProtocol
from .normalization import (
    finish_wiki_result,
    normalize_text,
    parse_api_utc,
    utc_fields,
    warning,
)
from .urls import TournamentPage


CARGO_LIMIT = 500
CARGO_MAX_PAGES = 10
CARGO_FIELDS = (
    "MS.MatchId=MatchId,MS.DateTime_UTC=DateTimeUTC,MS.Team1=Team1,MS.Team2=Team2,"
    "MS.BestOf=BestOf,MS.Phase=Phase,MS.Round=Round,MS.Tab=Tab,MS.HasTime=HasTime,"
    "MS.Stream=Stream,MS.Winner=Winner,MS.OverviewPage=OverviewPage"
)


def _cargo_records(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise WikiApiError("Leaguepedia returned a non-object Cargo response.")
    if isinstance(payload.get("error"), dict):
        error = payload["error"]
        message = normalize_text(error.get("info") or error.get("code"))
        raise WikiApiError(f"Leaguepedia Cargo API error: {message or 'unknown error'}.")
    rows = payload.get("cargoquery")
    if not isinstance(rows, list):
        raise WikiApiError("Leaguepedia response did not contain cargoquery rows.")
    records: list[dict[str, Any]] = []
    for row in rows:
        title = row.get("title") if isinstance(row, dict) else None
        if isinstance(title, dict):
            records.append(title)
    return records


def _value(record: dict[str, Any], *names: str) -> Any:
    folded = {str(key).casefold().replace("_", ""): value for key, value in record.items()}
    for name in names:
        key = name.casefold().replace("_", "")
        if key in folded:
            return folded[key]
    return None


def _stage(record: dict[str, Any]) -> str:
    values = [
        normalize_text(_value(record, "Phase")),
        normalize_text(_value(record, "Tab")),
        normalize_text(_value(record, "Round")),
    ]
    return " — ".join(dict.fromkeys(value for value in values if value))


class LeaguepediaAdapter:
    strategy = "leaguepedia_mediawiki_cargo_matchschedule"

    def fetch(self, page: TournamentPage, client: WikiHttpClientProtocol):
        escaped_title = page.title.replace("'", "''")
        records: list[dict[str, Any]] = []
        for page_number in range(CARGO_MAX_PAGES):
            params = {
                "action": "cargoquery",
                "format": "json",
                "formatversion": "2",
                "tables": "MatchSchedule=MS",
                "fields": CARGO_FIELDS,
                "where": (
                    f"MS.OverviewPage='{escaped_title}' AND "
                    '(MS.IsNullified IS NULL OR MS.IsNullified="0")'
                ),
                "order_by": "MS.DateTime_UTC ASC,MS.N_Page ASC,MS.N_TabInPage ASC,MS.N_MatchInTab ASC",
                "limit": str(CARGO_LIMIT),
                "offset": str(page_number * CARGO_LIMIT),
            }
            current = _cargo_records(client.get_json(page.api_url, params=params))
            records.extend(current)
            if len(current) < CARGO_LIMIT:
                break
        else:
            raise WikiApiError(
                f"Leaguepedia returned more than {CARGO_LIMIT * CARGO_MAX_PAGES} matches."
            )

        matches: list[ParsedMatch] = []
        issues = []
        skipped = 0
        seen_ids: set[str] = set()
        for index, record in enumerate(records, start=1):
            match_id = normalize_text(_value(record, "MatchId")) or f"leaguepedia-{index}"
            if match_id in seen_ids:
                continue
            seen_ids.add(match_id)
            team_a = normalize_text(_value(record, "Team1"))
            team_b = normalize_text(_value(record, "Team2"))
            has_time = str(_value(record, "HasTime") or "1").casefold() not in {
                "0",
                "false",
                "no",
            }
            try:
                start = parse_api_utc(
                    _value(record, "DateTimeUTC", "DateTime UTC"),
                    f"Leaguepedia match[{index}].DateTime_UTC",
                )
            except ValueError:
                start = None
            if start is None or not has_time or not team_a or not team_b:
                skipped += 1
                issues.append(
                    warning(
                        source_row=index,
                        page=page,
                        code="wiki_required_field_ambiguous",
                        message=(
                            "Leaguepedia record was skipped because date, explicit time, Team A, or Team B was missing."
                        ),
                    )
                )
                continue
            date_text, time_text, utc_text = utc_fields(start)
            bo_text = normalize_text(_value(record, "BestOf"))
            bo = f"BO{bo_text}" if bo_text and not bo_text.upper().startswith("BO") else bo_text.upper()
            round_name = normalize_text(_value(record, "Round"))
            winner = normalize_text(_value(record, "Winner"))
            match = ParsedMatch(
                source_row=index,
                source_sheet=page.title,
                date_original=date_text,
                time_original=time_text,
                timezone="UTC",
                start_time_utc=utc_text,
                team_a=team_a,
                team_b=team_b,
                stage=_stage(record),
                bo=bo,
                match_label=round_name or match_id,
                official=OfficialMatchMetadata(
                    source_id=page.source_id,
                    match_id=match_id,
                    source_url=page.url,
                    competition_name=page.title.rsplit("/", 1)[-1],
                    match_state="completed" if winner else "scheduled",
                    raw_state="winner_recorded" if winner else "unplayed",
                ),
            )
            matches.append(match)

        return finish_wiki_result(
            page=page,
            strategy=self.strategy,
            client=client,
            candidate_count=len(records),
            matches=matches,
            issues=issues,
            skipped_count=skipped,
        )
