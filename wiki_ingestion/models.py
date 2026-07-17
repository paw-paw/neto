"""Provider protocols used by tournament-page adapters and deterministic tests."""

from __future__ import annotations

from typing import Any, Protocol

from parser.models import ParseResult

from .urls import TournamentPage


class WikiHttpClientProtocol(Protocol):
    request_count: int

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any: ...


class TournamentProvider(Protocol):
    def fetch(self, page: TournamentPage, client: WikiHttpClientProtocol) -> ParseResult: ...
