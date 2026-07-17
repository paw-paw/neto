from __future__ import annotations

import os

import pytest

from wiki_ingestion import fetch_tournament_schedule


pytestmark = pytest.mark.live


@pytest.mark.skipif(
    os.getenv("NETO_RUN_LIVE_TESTS") != "1" or not os.getenv("NETO_WIKI_LIVE_URL"),
    reason="Set NETO_RUN_LIVE_TESTS=1 and NETO_WIKI_LIVE_URL for the opt-in wiki check.",
)
def test_configured_wiki_page_live_contract() -> None:
    result = fetch_tournament_schedule(os.environ["NETO_WIKI_LIVE_URL"])
    assert result.status in {"parsed", "parsed_with_warnings"}
    assert result.ingestion is not None
    assert result.ingestion.method == "wiki_tournament"
