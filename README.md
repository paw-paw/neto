# NETO v0

NETO (Normalized Esports Tournament Output) is a Streamlit application for turning esports schedules into a consistent, reviewable match table. It is an internal operational tool in active preliminary release: the ingestion contracts are stable, while source adapters and ParserKeys remain intentionally allowlisted.

This repository is public exclusively so it can be deployed on Streamlit Community Cloud. It is a runtime distribution, not a public dataset or validation package. Source workbooks, validation URLs, manifests, logs, and private validation materials are not included.

## Quick start

Use Python 3.12, create an isolated environment, and run:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

The current runtime needs no database, API key, cookie, browser service, or Streamlit secret. It does require outbound HTTPS access for network-backed sources.

## Supported sources

- **Google Sheets:** accepts a native Google Sheet shared as “Anyone with the link — Viewer.” NETO validates the URL, downloads an XLSX export in memory, applies archive-safety limits, and never persists the workbook.
- **XLSX upload:** provides a local fallback with the same security, fingerprinting, parsing, validation, and export path.
- **Official Website:** retrieves allowlisted public schedules from League of Legends Esports, VALORANT Esports, Call of Duty League, and Rainbow Six Siege.
- **Tournament Page:** retrieves Leaguepedia / LoL Fandom schedules through the public MediaWiki Cargo API. Liquipedia and arbitrary web scraping are not supported.

Google Sheets and XLSX sources require a compatible ParserKey selected and confirmed by the operator. Official Website and Tournament Page adapters emit NETO records directly and do not use ParserKeys.

## Canonical output

Export is enabled only for `parsed` and `parsed_with_warnings` results. The canonical CSV contract remains fixed at ten columns:

```text
date_original, time_original, timezone, start_time_utc,
team_a, team_b, stage, bo, match_label, row_status
```

The interface also exports the current filtered view as Markdown, XLSX, and PDF. Formula text, workbook-library objects, internal provenance, and adapter-only metadata never enter the canonical CSV. ParserKeys may preserve source filenames for recommendations and provenance; distributed keys omit optional source hashes.

## Repository structure

```text
app.py                 Streamlit entrypoint
parser/                ParserKey runtime, validation, presentation, exports
google_sheets/         Google Sheets download adapter
official_web/          Allowlisted official-site adapters
wiki_ingestion/        Tournament-page adapters
parser_keys/           Runtime ParserKeys
assets/                Runtime CSS, logo, fonts, and font licenses
docs/                  Deployment and technical contracts
examples/              ParserKey authoring templates
```

Only runtime dependencies belong in `requirements.txt`; validation code, source material, and development-only dependencies are maintained separately from this distribution.

## Deployment

Connect this repository to Streamlit Community Cloud, select `main`, set the entrypoint to `app.py`, and choose Python 3.12. No secrets are required for the current runtime. Detailed host requirements, safety boundaries, and release steps are in [docs/deployment.md](docs/deployment.md).

## Technical documentation

- [Google Sheets ingestion](docs/google_sheets.md)
- [Official website adapters](docs/official_web.md)
- [Tournament-page ingestion](docs/tournament_wikis.md)
- [ParserKey suggestion and registration](docs/parserkey_registration.md)
- [ParserKey v2 contract](docs/parserkey_v2/README.md)

## Copyright and security

Do not commit private URLs, downloaded schedules, credentials, or validation material. Report security concerns privately to the repository owner rather than opening an issue containing sensitive data.

The NETO code, ParserKeys, schema, branding, and documentation are distributed under **all rights reserved** terms; public visibility does not grant an open-source license. See [COPYRIGHT.md](COPYRIGHT.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
