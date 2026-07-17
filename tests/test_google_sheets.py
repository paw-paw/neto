from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

import google_sheets.service as service
from google_sheets import (
    GoogleSheetsAccessError,
    GoogleSheetsDownloadError,
    GoogleSheetsUrlError,
    fetch_google_sheet,
    parse_google_sheets_url,
)
from parser.parser_keys import load_parser_keys
from tests.helpers import valid_row, workbook_bytes


SHEET_ID = "1ouauktbqfjv1nW3RQTFucPU4zy85wQLo7ddp2SbGYc8"
SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
    "?gid=417448219#gid=417448219"
)
PUBLIC_CASES_PATH = (
    Path(__file__).parent / "fixtures" / "public_google_sheets_cases.json"
)


def _client(handler) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )


def test_public_google_sheets_corpus_is_valid_and_references_known_keys() -> None:
    manifest = json.loads(PUBLIC_CASES_PATH.read_text(encoding="utf-8"))
    cases = manifest["cases"]
    case_ids = [case["case_id"] for case in cases]
    sheet_ids = [parse_google_sheets_url(case["url"]).spreadsheet_id for case in cases]

    assert len(cases) == 14
    assert len(case_ids) == len(set(case_ids))
    assert len(sheet_ids) == len(set(sheet_ids))
    assert {case["compatibility"] for case in cases} <= {
        "exact",
        "cross_edition",
        "no_known_key",
    }

    catalog = load_parser_keys(Path(__file__).parents[1] / "parser_keys")
    assert not catalog.errors
    catalog_ids = {parser_key.parser_key_id for parser_key in catalog.keys}
    declared_ids = {
        parser_key_id
        for case in cases
        for parser_key_id in case["acceptable_parser_key_ids"]
    }
    assert declared_ids <= catalog_ids
    for case in cases:
        parse_expectation = case.get("live_parse_expectation")
        if parse_expectation:
            assert parse_expectation["parser_key_id"] in case[
                "acceptable_parser_key_ids"
            ]


def test_google_sheets_url_is_canonicalized_without_fetching_user_hosts() -> None:
    reference = parse_google_sheets_url(SHEET_URL)

    assert reference.spreadsheet_id == SHEET_ID
    assert reference.gid == "417448219"
    assert reference.canonical_url == (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid=417448219"
    )
    assert reference.export_url == (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"
    )

    invalid = (
        "http://docs.google.com/spreadsheets/d/id/edit",
        "https://drive.google.com/file/d/id/view",
        "https://example.com/spreadsheets/d/id/edit",
        "https://docs.google.com/document/d/id/edit",
        "https://user:secret@docs.google.com/spreadsheets/d/id/edit",
        "https://docs.google.com:notaport/spreadsheets/d/id/edit",
    )
    for value in invalid:
        with pytest.raises(GoogleSheetsUrlError):
            parse_google_sheets_url(value)


def test_public_sheet_download_returns_valid_complete_workbook_and_provenance() -> None:
    payload = workbook_bytes([valid_row()])

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"
        )
        return httpx.Response(
            200,
            headers={
                "content-type": service.EXPORT_MIME,
                "content-disposition": "attachment; filename*=UTF-8''Public%20Schedule.xlsx",
            },
            content=payload,
            request=request,
        )

    with _client(handler) as client:
        fetched = fetch_google_sheet(SHEET_URL, client=client)

    assert fetched.content == payload
    assert fetched.file_name == "Public Schedule.xlsx"
    assert fetched.reference.gid == "417448219"
    metadata = fetched.ingestion_metadata()
    assert metadata.method == "google_sheets"
    assert metadata.source_id == SHEET_ID
    assert metadata.source_url.endswith("edit?gid=417448219")
    assert metadata.request_count == 1


@pytest.mark.parametrize("status", [401, 403, 404])
def test_private_or_missing_sheets_have_an_actionable_error(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, request=request)

    with _client(handler) as client:
        with pytest.raises(GoogleSheetsAccessError, match="public"):
            fetch_google_sheet(SHEET_URL, client=client)


def test_sign_in_html_and_invalid_archives_are_rejected() -> None:
    def html_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html>Sign in</html>",
            request=request,
        )

    with _client(html_handler) as client:
        with pytest.raises(GoogleSheetsAccessError, match="sign-in"):
            fetch_google_sheet(SHEET_URL, client=client)

    def invalid_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": service.EXPORT_MIME},
            content=b"not an xlsx",
            request=request,
        )

    with _client(invalid_handler) as client:
        with pytest.raises(GoogleSheetsDownloadError, match="safe XLSX"):
            fetch_google_sheet(SHEET_URL, client=client)


def test_streaming_limit_and_redirect_host_are_enforced(monkeypatch) -> None:
    monkeypatch.setattr(service, "MAX_XLSX_BYTES", 10)

    def large_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 11, request=request)

    with _client(large_handler) as client:
        with pytest.raises(GoogleSheetsDownloadError, match="25 MB"):
            fetch_google_sheet(SHEET_URL, client=client)

    def redirect_handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "docs.google.com":
            return httpx.Response(
                302,
                headers={"location": "https://example.com/workbook.xlsx"},
                request=request,
            )
        return httpx.Response(200, content=b"unsafe", request=request)

    monkeypatch.setattr(service, "MAX_XLSX_BYTES", 25 * 1024 * 1024)
    with _client(redirect_handler) as client:
        with pytest.raises(GoogleSheetsDownloadError, match="unexpected host"):
            fetch_google_sheet(SHEET_URL, client=client)
