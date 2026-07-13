"""Public contracts for official website adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from parser.models import ParseResult


@dataclass(frozen=True)
class OfficialSource:
    source_id: str
    label: str
    source_url: str
    strategy: str
    allowed_hosts: tuple[str, ...]


@dataclass(frozen=True)
class OfficialScheduleRequest:
    source_id: str
    start_date: date
    end_date: date
    range_timezone: str = "America/Lima"


class OfficialHttpClientProtocol(Protocol):
    request_count: int

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict: ...

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str: ...


class OfficialScheduleAdapter(Protocol):
    source: OfficialSource

    def fetch(
        self,
        request: OfficialScheduleRequest,
        client: OfficialHttpClientProtocol,
    ) -> ParseResult: ...
