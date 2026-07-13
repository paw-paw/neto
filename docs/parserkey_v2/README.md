# NETO ParserKey v2 — Initial Universal Corpus

This package contains **8 schema-valid ParserKeys** representing the schedule variants supplied for NETO.

## Included corpus

| ParserKey | Expected records | Main structural pattern |
|---|---:|---|
| BetBoom RUSH B! Summit Part Four | 15 | Direct linear table + override |
| Exort Series 29 | 73 | Very wide row-oriented schedule |
| CCT Contenders Europe 6 | 30 | Linear table + vertically merged dates |
| XSE Pro League Guangzhou 2026 | 41 | Multiple sheets + merged dates + two timezones |
| Stake Ranked Episode 3 | 14 | Schedule embedded in bracket + non-contiguous blocks |
| Esports World Cup 2026 Dota 2 | 88 | Cached Google Sheets formulas + compound match text |
| European Pro League Season 39 | 30 | Repeated horizontal day tiles |
| NODWIN Clutch Series #10 | 72 | Multiple phase sheets + merged dates + future slots |

**Total expected normalized records: 363.**

## Status

All ParserKeys:

- validate against `neto_parserkey_v2.schema.json`;
- use only operators present in `neto_operator_catalog_v1.json`;
- declare an exact expected record count;
- include source-file SHA-256 hashes and smoke checks.

This package is a **runtime implementation contract**, not proof that the parser already executes.
The next engineering milestone is implementing the operator registry and running these keys against
the source XLSX files.

## Important decisions

- The schedule's primary displayed timezone becomes `tournament.base_timezone`.
- Formula-heavy XLSX files are read from cached values; NETO does not recalculate arbitrary formulas.
- Known future schedule slots with missing participants become `TBD`.
- Every record set emits `neto.normalized_match.v1`.
- Plugins remain available as a final escape hatch, but none of these eight keys require one.

## Recommended implementation order

1. JSON Schema and runtime capability validation.
2. Workbook loader, cached formula values and merged-cell index.
3. `row_scan` and `row_ranges`.
4. Cell sources and transform pipelines.
5. Regex extractors, fallbacks and overrides.
6. `tile_grid` and relative addressing.
7. UTC normalization, validation and provenance.
8. Regression runner using `neto_parserkey_v2_corpus_manifest.json`.
