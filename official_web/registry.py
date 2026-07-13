"""Registry and non-raising public service for official adapters."""

from __future__ import annotations

from datetime import datetime, timezone

from parser.models import IngestionMetadata, ParseResult

from .call_of_duty import CallOfDutyLeagueAdapter
from .errors import OfficialWebError
from .http import OfficialHttpClient
from .models import (
    OfficialHttpClientProtocol,
    OfficialScheduleAdapter,
    OfficialScheduleRequest,
    OfficialSource,
)
from .normalization import request_bounds
from .rainbow_six import RainbowSixSiegeAdapter
from .riot import LolEsportsAdapter, ValorantEsportsAdapter


_ADAPTERS: tuple[OfficialScheduleAdapter, ...] = (
    LolEsportsAdapter(),
    ValorantEsportsAdapter(),
    CallOfDutyLeagueAdapter(),
    RainbowSixSiegeAdapter(),
)
_BY_ID = {adapter.source.source_id: adapter for adapter in _ADAPTERS}


def list_official_sources() -> tuple[OfficialSource, ...]:
    return tuple(adapter.source for adapter in _ADAPTERS)


def _failure_metadata(
    source: OfficialSource,
    request: OfficialScheduleRequest,
    client: OfficialHttpClientProtocol | None,
) -> IngestionMetadata:
    return IngestionMetadata(
        method="official_web",
        source_id=source.source_id,
        source_label=source.label,
        source_url=source.source_url,
        strategy=source.strategy,
        fetched_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        request_count=getattr(client, "request_count", 0),
        legitimate_empty=False,
        range_start=request.start_date.isoformat(),
        range_end=request.end_date.isoformat(),
        range_timezone=request.range_timezone,
    )


def fetch_official_schedule(
    request: OfficialScheduleRequest,
    *,
    client: OfficialHttpClientProtocol | None = None,
) -> ParseResult:
    adapter = _BY_ID.get(request.source_id)
    if adapter is None:
        return ParseResult.failed(f'Unknown official source "{request.source_id}".')

    owned_client: OfficialHttpClient | None = None
    active_client = client
    try:
        request_bounds(request)
        if active_client is None:
            owned_client = OfficialHttpClient(adapter.source.allowed_hosts)
            active_client = owned_client
        return adapter.fetch(request, active_client)
    except OfficialWebError as exc:
        return ParseResult.failed(
            f"{adapter.source.label} retrieval failed using {adapter.source.strategy}: {exc}",
            notice=f"retrieval_strategy: {adapter.source.strategy}.",
            ingestion=_failure_metadata(adapter.source, request, active_client),
        )
    except Exception as exc:
        return ParseResult.failed(
            f"{adapter.source.label} retrieval failed unexpectedly: {type(exc).__name__}: {exc}",
            notice=f"retrieval_strategy: {adapter.source.strategy}.",
            ingestion=_failure_metadata(adapter.source, request, active_client),
        )
    finally:
        if owned_client is not None:
            owned_client.close()
