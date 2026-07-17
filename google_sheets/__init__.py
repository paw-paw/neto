"""Public interfaces for native Google Sheets workbook ingestion."""

from .errors import (
    GoogleSheetsAccessError,
    GoogleSheetsDownloadError,
    GoogleSheetsError,
    GoogleSheetsUrlError,
)
from .service import (
    FetchedGoogleSheet,
    GoogleSheetReference,
    fetch_google_sheet,
    parse_fetched_google_sheet,
    parse_google_sheets_url,
)

__all__ = [
    "FetchedGoogleSheet",
    "GoogleSheetReference",
    "GoogleSheetsAccessError",
    "GoogleSheetsDownloadError",
    "GoogleSheetsError",
    "GoogleSheetsUrlError",
    "fetch_google_sheet",
    "parse_fetched_google_sheet",
    "parse_google_sheets_url",
]
