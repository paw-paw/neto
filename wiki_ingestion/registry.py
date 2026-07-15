"""URL-routed non-raising service for tournament wiki providers."""

from __future__ import annotations

from parser.models import ParseResult

from .errors import TournamentUrlError, WikiIngestionError
from .http import WikiHttpClient
from .leaguepedia import LeaguepediaAdapter
from .models import WikiHttpClientProtocol
from .normalization import failure_metadata
from .urls import TournamentPage, parse_tournament_url


def fetch_tournament_schedule(
    url: str,
    *,
    client: WikiHttpClientProtocol | None = None,
) -> ParseResult:
    try:
        page = parse_tournament_url(url)
    except TournamentUrlError as exc:
        return ParseResult.failed(f"Invalid or unsupported tournament URL: {exc}")

    active_client = client
    owned_client: WikiHttpClient | None = None
    strategy = LeaguepediaAdapter.strategy
    try:
        adapter = LeaguepediaAdapter()
        if active_client is None:
            owned_client = WikiHttpClient(
                ("lol.fandom.com",),
                "NETO-tournament-schedule/1.0 (server-side Leaguepedia Cargo client)",
            )
            active_client = owned_client
        return adapter.fetch(page, active_client)
    except WikiIngestionError as exc:
        return ParseResult.failed(
            f"{page.game_label} tournament retrieval failed using {strategy}: {exc}",
            notice=f"retrieval_strategy: {strategy}.",
            ingestion=failure_metadata(page, strategy, active_client),
        )
    except Exception as exc:
        return ParseResult.failed(
            f"{page.game_label} tournament retrieval failed unexpectedly: {type(exc).__name__}: {exc}",
            notice=f"retrieval_strategy: {strategy}.",
            ingestion=failure_metadata(page, strategy, active_client),
        )
    finally:
        if owned_client is not None:
            owned_client.close()
