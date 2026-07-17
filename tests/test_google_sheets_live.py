from __future__ import annotations

import os

import pytest

from google_sheets import fetch_google_sheet


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("NETO_RUN_LIVE_TESTS") != "1",
        reason="Set NETO_RUN_LIVE_TESTS=1 to call the public Google Sheets exporter.",
    ),
]


PUBLIC_SHEETS = (
    "https://docs.google.com/spreadsheets/d/1ouauktbqfjv1nW3RQTFucPU4zy85wQLo7ddp2SbGYc8/edit?gid=417448219",
    "https://docs.google.com/spreadsheets/d/1fP6zrbzgmqTzM6sZqOo3fjyD8-nvtbOuyendKGbZPuE/edit?gid=683028203",
    "https://docs.google.com/spreadsheets/d/19cKagzrnA6BTCpqQvK4SPTGUDkbFfjh1Bk0HW5mb8pU/edit?gid=1105108609",
    "https://docs.google.com/spreadsheets/d/1nrY4DlizZ0JZDlxmPRrch9n5l4DVw1iR4jKpNDhN6Dk/edit?gid=1778001380",
    "https://docs.google.com/spreadsheets/d/12dfiEnSCrwYXOm9bCliRK7RKPZraCpGdM0i9dDkmb0Y/edit?gid=718451828",
    "https://docs.google.com/spreadsheets/d/14Cb-ZREABmFoEkxkGM7_15JTfeVhqSsebEfXZwUusMQ/edit?gid=1683736108",
)


@pytest.mark.parametrize("url", PUBLIC_SHEETS)
def test_public_google_sheet_exports_a_safe_xlsx(url: str) -> None:
    fetched = fetch_google_sheet(url)

    assert fetched.content.startswith(b"PK")
    assert fetched.file_name.lower().endswith(".xlsx")
    assert fetched.ingestion_metadata().method == "google_sheets"
