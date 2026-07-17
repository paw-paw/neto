# Public Google Sheets ingestion

NETO treats a public native Google Sheet as another source of XLSX bytes. It does not introduce a separate spreadsheet parser: after download, the existing workbook security, fingerprint, ParserKey confirmation, parser, validation, preview, filtering, and export systems remain authoritative.

## Supported URLs

Accepted URLs must:

- use HTTPS;
- use the exact host `docs.google.com`;
- contain `/spreadsheets/d/<spreadsheet_id>`;
- represent a native Google Sheet shared as **Anyone with the link — Viewer**.

NETO extracts an optional numeric `gid` from the query or fragment and retains it in the canonical provenance URL. The `gid` does not limit ingestion to one tab: NETO exports the complete workbook because ParserKeys may require several sheets.

Google Drive file URLs, private sheets, published HTML/CSV views, embedded credentials, custom ports, and arbitrary download URLs are not supported.

## Download and safety policy

NETO builds this endpoint from the validated spreadsheet ID:

```text
https://docs.google.com/spreadsheets/d/<spreadsheet_id>/export?format=xlsx
```

The provider uses an identifying User-Agent, connection-aware HTTP client, bounded connect/read timeouts, and Google-owned redirect validation. It streams the response into memory and stops once the existing 25 MB workbook limit is exceeded. The completed response must pass NETO's ZIP/XLSX member, expansion, encryption, and compression-ratio checks before fingerprinting or parsing.

Successful downloads are cached by Streamlit for five minutes. Exceptions are not cached. The Community Cloud filesystem is not used for persistence and no Google credentials or API key are required.

## User-visible failures

The provider distinguishes:

- invalid or unsupported URL;
- private, missing, or sign-in-gated sheet;
- Google HTTP/transport failure;
- oversized response;
- unexpected redirect host;
- malformed or unsafe XLSX response.

For private documents, users should change Google sharing to **Anyone with the link — Viewer** and load the URL again.

## Provenance

Google Sheets parse results retain:

- ingestion method `google_sheets`;
- spreadsheet ID;
- canonical source URL and optional `gid`;
- exported workbook filename;
- retrieval strategy and timestamp;
- request count.

The local **Upload XLSX (fallback)** path intentionally remains available and follows the previous non-network workflow.

## ParserKey boundary and known limitations

This provider only changes how XLSX bytes reach NETO. The shared recommender and parser receive the same workbook bytes as the XLSX fallback. The provider itself does not change record-count contracts, formula policies, field requirements, warnings, or blocking errors.

Consequently, a public sheet can download successfully while its selected ParserKey reports warnings or a blocked result because the live document differs from the snapshot used to create the key. The bounded structural recommender automatically recognizes CCT SA4 as compatible with the SA3 key and Exort Series 30 as compatible with the Series 29 key; it hides zero-score candidates. Exact record-count failures, missing formula caches or required fields, and updates required by draft keys remain ParserKey/runtime work rather than Google Sheets transport failures.

The bundled StarSeries S20 Barcelona key is registered as `draft`. It passes the current schema/runtime acceptance gates, but its current public sheet has diverged from the key's extraction and exact-count expectations; no compatibility claim is made in this release.

## Deployment

Streamlit Community Cloud needs outbound HTTPS access to:

- `docs.google.com`;
- Google-owned `*.googleusercontent.com` download hosts used by redirects.

There are no required secrets. Normal tests use mocked HTTP responses. The 14-case public corpus is stored in `tests/fixtures/public_google_sheets_cases.json`; `tests/test_google_sheets_live.py` is opt-in through `NETO_RUN_LIVE_TESTS=1` and verifies safe export plus expected top-ranked ParserKey identity. Full parser outcomes stay in separate regression checks.
