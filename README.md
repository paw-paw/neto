# NETO v0

NETO (Normalized Esports Tournament Output) is a small internal Streamlit tool for prematch traders. It converts public native Google Sheets, fallback XLSX uploads, official esports website schedules, and supported tournament wiki pages into a normalized, validated table with UTC start times and operator-friendly exports.

## Requirements

- Python 3.11 or newer
- A public native Google Sheet or an `.xlsx` schedule
- At least one valid ParserKey JSON in `parser_keys/`

Install and run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Choose **Google Sheets** to load a public native spreadsheet, or open **Upload XLSX (fallback)** for a local workbook. Review NETO's existing structural ParserKey suggestions, explicitly confirm a key, and click **Run Parse**. Choose **Official Website** to select an official source, inclusive date range, and range timezone. Choose **Tournament Page** for a Leaguepedia / LoL Fandom event URL. Each ingestion method has a short hover explanation. Export is enabled only when the result status is `parsed` or `parsed_with_warnings`.

The interface uses a compact multi-column dashboard on wide displays and automatically stacks the same workflow vertically on narrow or near-square viewports. Findings, validation issues, and export controls share a summary row; the match table always uses the full content width below it.

NETO ships its Deep Ocean Terminal visual identity with the application. The mascot, JetBrains Mono, DM Sans, design tokens, and font licenses are stored under `assets/` and embedded locally at runtime, so the interface does not depend on Google Fonts or another visual CDN. Streamlit's base dark theme lives in `.streamlit/config.toml`; the wider dashboard layout remains intentional even though the source design reference describes a narrow editorial page.

The match table prioritizes natural date/time values, teams, BO, and stage. Its toolbar supports:

- Descending start-time sorting by default, with ascending sorting available.
- Free-text search across teams, stage, and match label.
- Stage and row-status filters in the same row as visible matches and schedule timezone.
- Collapsed source-metadata filters for Competition and Match state when available.

The table header also shows visible/total matches and the ParserKey schedule timezone.

CSV, Markdown, XLSX, and PDF exports reflect the current filtered and sorted view. CSV retains NETO's fixed canonical ten-column schema; the other formats use the human-readable table headers and displayed local date/time.

## Google Sheets ingestion

NETO accepts public native Google Sheets URLs in the form `https://docs.google.com/spreadsheets/d/<id>/...`. The document must be shared as **Anyone with the link — Viewer**. NETO constructs Google's XLSX export endpoint itself, downloads the complete workbook in memory, validates it against the same 25 MB and archive-safety policy as uploads, and then reuses the existing fingerprint, ParserKey confirmation, parser, validation, preview, and export flow.

Only `docs.google.com/spreadsheets` URLs are accepted; arbitrary URLs, embedded credentials, private sheets, Google Drive file links, and non-native documents are rejected. The selected `gid` is retained in the canonical source URL, but the complete workbook is downloaded because ParserKeys may require multiple tabs. Successful downloads are cached for five minutes and failures are not cached. No Google credentials or API key are required. Detailed behavior and deployment notes are in `docs/google_sheets.md`.

## Official website ingestion

NETO currently supports four allowlisted official sources:

- League of Legends Esports — official Riot GraphQL persisted query.
- VALORANT Esports — an independent adapter using the corresponding Riot sport contract.
- Call of Duty League — season data embedded in the official Next.js page state.
- Rainbow Six Siege — complete month data embedded in the official calendar page state.

Official ranges are inclusive in the selected IANA timezone and limited to 90 days. The browser's IANA timezone is the default, `UTC` is used when it is unavailable, and the searchable selector contains the complete timezone database. Successful results are cached in the Streamlit process for five minutes. Failed requests are not cached. Retrieval strategy, request count, official match states, IDs, competitions, regions, and source URLs remain available in Findings and the official metadata expander.

Official Stage values include available Competition context so schedules containing several tournaments remain distinguishable. The original Competition value is still retained as source metadata.

Blank official participants become `TBD`. When Rainbow Six explicitly marks a published timestamp as TBD, NETO retains the provisional timestamp, adds `official_time_tbd`, and keeps the row exportable. A valid response containing no matches is reported as a legitimate empty result rather than an extraction failure.

The canonical CSV remains the same ten-column NETO contract. Official metadata is intentionally UI/internal only so existing downstream consumers remain compatible. Deployment requires outbound HTTPS access to `lolesports.com`, `valorantesports.com`, `callofdutyleague.com`, and `www.ubisoft.com`; no browser runtime, credentials, cookies, or private tokens are required.

Detailed source contracts and maintenance risks are documented in `docs/official_web.md`.

## Tournament wiki ingestion

The preliminary release supports Leaguepedia / LoL Fandom tournament URLs (`lol.fandom.com/wiki/...`) through the public MediaWiki Cargo `MatchSchedule` table. Successful responses are cached for one hour, all published matches are requested, and source URLs and attribution remain visible in Findings and source metadata. Liquipedia ingestion is intentionally disabled for this release.

Complete, partial-with-warnings, no-schedule, unsupported-structure, API-failure, and invalid-URL outcomes are reported separately. Records without a reliable date, time, Team A, and Team B are skipped with visible warnings; a page where no candidate record has all four required values fails as unsupported structure.

Provider contracts, supported URL patterns, configuration, attribution, and limitations are documented in `docs/tournament_wikis.md`.

## ParserKeys

Runtime keys are discovered from `parser_keys/*.json`. NETO supports:

- `neto.parser_key.v0`: the original linear-table format and its equivalent flat shape.
- `neto.parser_key.v2`: schema-validated operator pipelines used by the bundled eight-workbook universal corpus.

The v0 semantic fields are:

```text
parser_key_id, key_name, tournament_name, base_timezone,
target_sheet, layout_type, header_row, data_start_row,
field_mappings, forward_fill_rules
```

Only `layout_type = linear_table` is supported. Column mappings use Excel letters. `date`, `time`, `team_a`, and `team_b` mappings are mandatory, and team fields can never be forward-filled. Invalid keys are reported in the UI and excluded from selection.

ParserKey v2 files are validated against `neto_parserkey_v2.schema.json`, the declared operator catalog, and the operators implemented by the runtime before they appear in the UI. The initial runtime supports row scans/ranges, horizontal tile grids, merged and relative cells, contexts, regex extractors, predicates, fallbacks/defaults, overrides, formula-cache policies, and deterministic date/time transforms. Plugins remain unsupported.

Reference templates are stored in `examples/` so their placeholder values are not loaded as runtime keys. The v2 contract and operator semantics are documented under `docs/parserkey_v2/`.

When a Google Sheet or XLSX fallback is loaded, NETO ranks the top three keys using sheet-name compatibility, bounded header/content samples, sheet dimensions, and source filename metadata. It does not run every complete parser for ranking. The score is advisory, low confidence is stated explicitly, and parsing stays disabled until the user confirms the selected key. This release does not change ranking, scoring, confidence, or ParserKey validation behavior.

The XLSX workflow also links to the NETO ParserKey Creator Custom GPT and accepts uploaded ParserKey JSON. Uploads pass the same schema, operator capability, plugin policy, identifier, regex-size, and bounded-work validation as repository keys. Valid keys become available immediately in the current browser session and are never written to GitHub or the Community Cloud filesystem. See `docs/parserkey_registration.md`.

## Parsing behavior

- Target sheet matching is exact and case-sensitive.
- Reading starts at `data_start_row` and stops after five consecutive rows where all mapped fields are empty after whitespace normalization.
- Strings are trimmed, line breaks become spaces, internal whitespace is collapsed, and casing is preserved.
- Forward-fill is applied only to enabled fields and never to `team_a` or `team_b`.
- Native Excel date/time values are supported, along with documented ISO/day-first date strings and 12/24-hour time strings.
- The timezone always comes from the ParserKey and is converted with Python `zoneinfo`.
- ParserKey `output` configuration is informational in v0. The canonical CSV always uses NETO's fixed ten-column output, including `row_status`.
- Formula cells follow each key's `cached_value_only` or `first_available` policy. Missing caches become visible warnings/fallbacks rather than being silently recalculated.
- V2 matches retain source sheet, record set, tile, source cell, transform chain, fallback/default use, and override reason internally; these fields are excluded from CSV.

## Tests

The test suite includes generated workbooks, the original public CCT workbook, all eight v2 source workbooks, Google Sheets URL/download security tests, top-three suggestion regression, temporary ParserKey registration and resource-policy checks, sanitized official and Leaguepedia API fixtures, UTC conversion and validation cases, four-format export checks, and Streamlit smoke tests for all three ingestion modes. The v2 regression asserts all 363 expected records, source hashes, record counts, smoke checks, and absence of blocking errors.

```bash
pytest
```

Run only the universal corpus regression with:

```bash
pytest tests/test_v2_corpus.py -q
```

Live official-source smoke tests are opt-in and may return a legitimate empty range:

```bash
NETO_RUN_LIVE_TESTS=1 pytest tests/test_official_live.py -q
```

On PowerShell:

```powershell
$env:NETO_RUN_LIVE_TESTS = "1"
pytest tests/test_official_live.py -q
```

Wiki live checks are also opt-in and require an explicit page URL:

```powershell
$env:NETO_RUN_LIVE_TESTS = "1"
$env:NETO_WIKI_LIVE_URL = "https://lol.fandom.com/wiki/<tournament>"
pytest tests/test_wiki_live.py -q
```

The six public Google Sheets transport checks are opt-in. They verify only that Google exports a safe XLSX; ParserKey parse outcomes are intentionally outside this check:

```powershell
$env:NETO_RUN_LIVE_TESTS = "1"
pytest tests/test_google_sheets_live.py -q
```

## Intentional v0 exclusions

No database, private Google authentication, arbitrary Google Drive files, in-app key editor, JSON export, visual brackets, copy-table action, match editing, arbitrary website scraping, or production browser automation is included. The Custom GPT is an external authoring workflow; NETO itself does not generate ParserKeys with AI.
