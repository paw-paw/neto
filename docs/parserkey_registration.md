# ParserKey suggestion and registration

## Structural suggestions

`parser/suggestions.py` opens the workbook read-only and builds a bounded fingerprint from:

- exact and case-compatible sheet names;
- an unconditional maximum of 32 rows and 40 columns per sheet, including Google exports that omit worksheet dimensions;
- v0 header/mapped-column probes and v2 row-range, anchor-column, tile-origin, relative-cell, context, and extractor probes derived from the existing ParserKey contract;
- known per-sheet dimensions compared with that sheet's own declared requirements, while unknown dimensions remain neutral;
- Unicode-aware tournament-family and source-filename identity, with edition numbers handled separately so a compatible edition X key can rank for edition X+1.

The matcher does not execute complete v0 or v2 parsers. It returns at most three positive-score candidates with a 0–100 advisory score, High/Medium/Low structural-match strength, runner-up-aware confidence, and concise reasons. Zero-score candidates are omitted and a top score below the no-match floor returns no recommendation. Draft/enabled status is displayed separately from structural strength. The user must select and explicitly confirm a key before **Run Parse** is enabled.

## Upload acceptance gates

Uploaded JSON is limited to 1 MB, decoded as UTF-8, and passed to `normalize_parser_key`, the same entry point used by the repository registry. This enforces the currently deployed contracts:

- valid JSON and supported `neto.parser_key.v0` / `neto.parser_key.v2` versions;
- v2 JSON Schema validation;
- declared operator presence in the operator catalog;
- implementation of every required operator by the current runtime;
- no required plugins, because the current runtime does not load plugins;
- valid required identifiers, source references, sheet locators, mappings, and runtime sections;
- bounded v2 record sets, operator nodes, regex patterns, and locator anchor counts;
- no duplicate `parser_key_id` in the repository or current session.

## Temporary registration lifecycle

Accepted keys are stored only in Streamlit session state and become selectable immediately in the uploader's current browser session. NETO does not write uploaded ParserKeys to GitHub, the repository checkout, or another persistence service.

The key disappears when the session expires, the browser starts a new session, or Streamlit Community Cloud restarts the app. It is not visible to other users. To make a key permanent, an operator must review it and add it to `parser_keys/` through the normal repository development and deployment process.

This boundary intentionally keeps the preliminary internal release credential-free and prevents the deployed app from modifying its own source repository.

## Resource policy

Uploaded ParserKeys are treated as untrusted declarative input. In addition to the 1 MB JSON limit, v2 uploads are limited to 64 record sets, 5,000 operator nodes, 512 characters per regex pattern, 256 regex patterns, 50,000 anchors per locator, and 100,000 total anchors. These limits accommodate expected production documents while preventing obviously unbounded execution plans; they are not a substitute for restricting the app to trusted internal users.
