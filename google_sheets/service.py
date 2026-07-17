"""Secure public Google Sheets to XLSX ingestion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePath
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

import httpx

from parser import parse_workbook
from parser.models import IngestionMetadata, ParseResult, ParserKey
from parser.workbook_security import (
    MAX_XLSX_BYTES,
    WorkbookSafetyError,
    validate_xlsx_archive,
)

from .errors import (
    GoogleSheetsAccessError,
    GoogleSheetsDownloadError,
    GoogleSheetsUrlError,
)


GOOGLE_SHEETS_HOST = "docs.google.com"
EXPORT_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPORT_STRATEGY = "google_sheets_public_xlsx_export"
USER_AGENT = "NETO-google-sheets/0.1 (+public workbook ingestion)"
_SHEET_PATH = re.compile(r"^/spreadsheets/d/([A-Za-z0-9_-]+)(?:/.*)?$")
_SAFE_FINAL_HOSTS = (GOOGLE_SHEETS_HOST, ".googleusercontent.com")


@dataclass(frozen=True)
class GoogleSheetReference:
    spreadsheet_id: str
    gid: str | None
    canonical_url: str
    export_url: str


@dataclass(frozen=True)
class FetchedGoogleSheet:
    reference: GoogleSheetReference
    file_name: str
    content: bytes
    fetched_at_utc: str
    request_count: int = 1

    def ingestion_metadata(self) -> IngestionMetadata:
        return IngestionMetadata(
            method="google_sheets",
            source_id=self.reference.spreadsheet_id,
            source_label=self.file_name,
            source_url=self.reference.canonical_url,
            strategy=EXPORT_STRATEGY,
            fetched_at_utc=self.fetched_at_utc,
            request_count=self.request_count,
        )


def parse_google_sheets_url(url: str) -> GoogleSheetReference:
    """Validate a native public Google Sheets URL and derive its export URL."""

    value = str(url or "").strip()
    if not value:
        raise GoogleSheetsUrlError("Enter a public Google Sheets URL.")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise GoogleSheetsUrlError("The Google Sheets URL is malformed.") from exc
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != GOOGLE_SHEETS_HOST:
        raise GoogleSheetsUrlError(
            "Only HTTPS URLs from docs.google.com/spreadsheets are supported."
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise GoogleSheetsUrlError("The Google Sheets URL has an invalid port.") from exc
    if parsed.username or parsed.password or port not in (None, 443):
        raise GoogleSheetsUrlError("Credentials and custom ports are not supported.")
    match = _SHEET_PATH.fullmatch(parsed.path)
    if not match:
        raise GoogleSheetsUrlError(
            "Use a native Google Sheets URL containing /spreadsheets/d/<id>."
        )

    spreadsheet_id = match.group(1)
    query = parse_qs(parsed.query)
    fragment = parse_qs(parsed.fragment)
    gid_values = query.get("gid") or fragment.get("gid") or []
    gid = str(gid_values[0]) if gid_values and str(gid_values[0]).isdigit() else None
    canonical_query = urlencode({"gid": gid}) if gid else ""
    canonical_url = (
        f"https://{GOOGLE_SHEETS_HOST}/spreadsheets/d/{spreadsheet_id}/edit"
        + (f"?{canonical_query}" if canonical_query else "")
    )
    export_url = (
        f"https://{GOOGLE_SHEETS_HOST}/spreadsheets/d/{spreadsheet_id}/export"
        "?format=xlsx"
    )
    return GoogleSheetReference(
        spreadsheet_id=spreadsheet_id,
        gid=gid,
        canonical_url=canonical_url,
        export_url=export_url,
    )


def _response_file_name(header: str, spreadsheet_id: str) -> str:
    encoded = re.search(r"filename\*=UTF-8''([^;]+)", header or "", re.IGNORECASE)
    quoted = re.search(r'filename="([^"]+)"', header or "", re.IGNORECASE)
    plain = re.search(r"filename=([^;]+)", header or "", re.IGNORECASE)
    raw = (
        unquote(encoded.group(1))
        if encoded
        else (quoted.group(1) if quoted else (plain.group(1).strip() if plain else ""))
    )
    name = PurePath(raw).name.strip().strip('"')
    if not name:
        name = f"google_sheet_{spreadsheet_id}.xlsx"
    if not name.lower().endswith(".xlsx"):
        name += ".xlsx"
    return name


def _validate_final_url(url: str) -> None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(
        host == allowed or (allowed.startswith(".") and host.endswith(allowed))
        for allowed in _SAFE_FINAL_HOSTS
    ):
        raise GoogleSheetsDownloadError(
            "Google Sheets redirected the download to an unexpected host."
        )


def fetch_google_sheet(
    url: str,
    *,
    client: httpx.Client | None = None,
) -> FetchedGoogleSheet:
    """Download and validate a public native Google Sheet as a complete XLSX."""

    reference = parse_google_sheets_url(url)
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(45.0, connect=10.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": EXPORT_MIME},
    )
    try:
        try:
            with active_client.stream("GET", reference.export_url) as response:
                _validate_final_url(str(response.url))
                if response.status_code in {401, 403}:
                    raise GoogleSheetsAccessError(
                        "This sheet is not publicly accessible. Share it as "
                        '"Anyone with the link — Viewer" and try again.'
                    )
                if response.status_code == 404:
                    raise GoogleSheetsAccessError(
                        "The Google Sheet was not found or is not publicly accessible."
                    )
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" in content_type:
                    raise GoogleSheetsAccessError(
                        "Google returned a sign-in page instead of a workbook. Share the "
                        'sheet as "Anyone with the link — Viewer".'
                    )
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_XLSX_BYTES:
                        raise GoogleSheetsDownloadError(
                            "The exported Google Sheet exceeds NETO's 25 MB limit."
                        )
                    chunks.append(chunk)
                content = b"".join(chunks)
                file_name = _response_file_name(
                    response.headers.get("content-disposition", ""),
                    reference.spreadsheet_id,
                )
        except GoogleSheetsAccessError:
            raise
        except GoogleSheetsDownloadError:
            raise
        except httpx.HTTPStatusError as exc:
            raise GoogleSheetsDownloadError(
                f"Google Sheets returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise GoogleSheetsDownloadError(
                f"Google Sheets could not be reached: {type(exc).__name__}."
            ) from exc

        try:
            validate_xlsx_archive(content)
        except WorkbookSafetyError as exc:
            raise GoogleSheetsDownloadError(
                f"Google did not return a safe XLSX workbook: {exc}"
            ) from exc
        return FetchedGoogleSheet(
            reference=reference,
            file_name=file_name,
            content=content,
            fetched_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    finally:
        if owned_client:
            active_client.close()


def parse_fetched_google_sheet(
    workbook: FetchedGoogleSheet,
    parser_key: ParserKey,
) -> ParseResult:
    """Run the existing workbook parser and attach Google Sheets provenance."""

    result = parse_workbook(workbook.content, parser_key)
    result.ingestion = workbook.ingestion_metadata()
    return result
