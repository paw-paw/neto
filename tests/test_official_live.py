from __future__ import annotations

import os
from datetime import date

import pytest

from official_web import OfficialScheduleRequest, fetch_official_schedule, list_official_sources


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("NETO_RUN_LIVE_TESTS") != "1",
        reason="Set NETO_RUN_LIVE_TESTS=1 to call official public websites.",
    ),
]


@pytest.mark.parametrize(
    "source_id", [source.source_id for source in list_official_sources()]
)
def test_official_source_live_contract(source_id: str) -> None:
    today = date.today()
    result = fetch_official_schedule(
        OfficialScheduleRequest(
            source_id=source_id,
            start_date=today,
            end_date=today,
            range_timezone="America/Lima",
        )
    )

    assert result.status != "failed", result.technical_error
    assert result.ingestion is not None
    assert result.ingestion.strategy
    assert result.ingestion.request_count >= 1
