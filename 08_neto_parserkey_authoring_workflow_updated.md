# NETO ParserKey v2 — Authoring Workflow

## Goal

Turn one uploaded esports schedule XLSX into:

1. a schema-valid `neto.parser_key.v2` draft;
2. an inspection report;
3. an external validation report.

The CustomGPT may author and simulate a ParserKey. Only the real NETO runtime can establish `runtime_verified`.

The workflow targets the effective current NETO runtime, not every feature accepted by the JSON Schema.

## Required deliverables

1. `<tournament_slug>_parserkey_v1.json`
2. `<tournament_slug>_inspection_report.md`
3. `<tournament_slug>_validation_report.json`

The ParserKey must begin with:

```text
status: draft
```

The `status` value is advisory. The current NETO loader does not enforce the approval ladder.

## Current runtime boundary

Operational ParserKeys may use only operators listed in:

```text
04_neto_runtime_capabilities_v1.json
```

Use only:

- `sheet.exact`;
- `records.row_scan`;
- `records.row_ranges`;
- `records.tile_grid`;
- `cell.absolute`;
- `cell.column`;
- `cell.relative`;
- `cell.merged_origin`;
- `record.row_index`;
- `context.get` with record-set context;
- `extract.regex`;
- `extractor.output`;
- `literal.value`;
- supported predicates;
- supported text transforms;
- supported datetime transforms.

Do not generate operational keys that depend on:

- plugins;
- `additional_fields`;
- `start_datetime`;
- field-level timezone values;
- arbitrary cross-sheet lookups;
- custom validation rules;
- unsupported extractor failure policies;
- schema-only output extensions;
- undeclared or catalog-only operators.

If the workbook requires one of these capabilities, stop and report:

```text
approval_recommendation: needs_runtime_capability
```

Do not fabricate an executable ParserKey.

## Phase 1 — Workbook inventory

Inspect the workbook programmatically, not only visually.

Record:

- filename and SHA-256;
- workbook date system;
- all sheet names and order;
- sheet visibility;
- dimensions and used ranges;
- hidden rows and columns;
- merged ranges;
- named ranges and tables for inspection purposes;
- formulas, cached values, and cell data types;
- cell number formats;
- repeated structural patterns;
- tournament name, game, edition/year, and timezone evidence.

Named ranges, tables, hidden columns, and hidden sheets may be documented in the inspection report, but they are not automatically usable runtime sources.

Do not assume that the first sheet or largest used range contains the schedule.

## Phase 2 — Locate schedule-bearing regions

Identify every area that represents scheduled matches.

Separate:

- schedule tables;
- brackets;
- team data;
- results-only tables;
- operational notes;
- timezone conversion columns;
- duplicate views;
- presentation-only regions.

For each schedule-bearing region, determine whether it should become a `record_set`.

Do not use a result table as the authoritative schedule merely because it is visually convenient.

## Phase 3 — Define the record unit

A record must correspond to exactly one scheduled match or series.

Choose the simplest supported locator:

1. `records.row_scan`;
2. `records.row_ranges`;
3. `records.tile_grid`;
4. another operator explicitly marked supported in the capability manifest.

Do not use `records.explicit_rows`, `records.matrix_scan`, `records.cell_search`, `records.union`, or plugin locators.

Avoid explicit hardcoded cell lists when a reusable supported structural rule exists.

If no supported locator can represent the workbook, stop at capability escalation.

## Phase 4 — Map effective fields

For each record set, locate or derive only these effective fields:

- `date`;
- `time`;
- `team_a`;
- `team_b`;
- `stage`;
- `bo`;
- `match_label`.

Use `date` plus `time` for UTC conversion.

Do not use:

- `start_datetime`;
- a field-level `timezone`;
- `round`;
- `group`;
- `stream`;
- `venue`;
- `notes`;
- arbitrary `additional_fields`.

If the workbook contains useful auxiliary information, document it in the inspection report. Do not place it in the ParserKey as operational output.

Prefer workbook values over hardcoded literals. Literals are appropriate for stable context such as a record set's stage or an explicitly justified placeholder.

## Phase 5 — Handle structure and context

Use supported mechanisms for:

- merged cells;
- section headers represented through record-set context;
- nearest non-empty values through the supported `cell.merged_origin` fallback;
- non-contiguous row blocks;
- horizontal tiles;
- relative addressing;
- formula-backed fields using cached values;
- compound text extraction using `extract.regex`;
- explicit placeholders;
- genuine record-level exceptions using overrides.

The current runtime does not provide a general cross-sheet lookup engine. Multiple sources and record sets may be declared, but do not assume that one field pipeline can perform arbitrary lookups across sheets.

## Phase 6 — Determine timezone

The ParserKey owns the tournament base timezone.

Timezone evidence may come from:

- a timezone label in the schedule;
- a venue or location;
- an official event document;
- a reliable conversion column;
- workbook metadata or notes.

Use an IANA timezone, not an abbreviation.

When evidence remains ambiguous:

1. report the candidate timezones;
2. add the issue to `required_user_inputs`;
3. use `needs_user_input`;
4. do not mark the key runtime-ready.

The current runtime uses `tournament.base_timezone` for conversion. A field-level timezone must not be used.

## Phase 7 — Build the ParserKey

Start from `02_neto_parserkey_template_v2.json`.

Requirements:

- `schema_version = neto.parser_key.v2`;
- unique snake-case `parser_key_id`;
- version suffix such as `_v1`;
- `status = draft`;
- all source sheets declared with `sheet.exact`;
- one or more record sets;
- only supported operators;
- effective date/time/team/stage/BO/match fields;
- `additional_fields = {}`;
- `runtime.required_plugins = []`;
- `normalization.datetime.precedence = ["date_plus_time"]`;
- normalized output model `neto.normalized_match.v1`;
- ten effective output columns, including `row_status`;
- provenance enabled;
- source metadata and notes;
- workbook-specific record-count bounds.

Do not claim that a key is runtime verified merely because it is schema-valid.

## Phase 8 — Structural validation

Validate the JSON against:

```text
01_neto_parserkey_v2.schema.json
```

Then verify:

- every operator appears in `runtime.required_operators`;
- every operator appears in the operator catalog;
- every operational operator is in `supported_by_initial_corpus`;
- every source uses `sheet.exact`;
- every `sheet.exact` node uses `args.sheet_name`;
- datetime transforms use `args.formats`, not `args.format`;
- all source sheets exist in the workbook;
- all referenced rows, columns, and cells are plausible;
- record-set source IDs resolve;
- required effective fields can be emitted;
- `additional_fields` is empty;
- `required_plugins` is empty;
- record-count bounds are integers and are based on workbook evidence.

Schema validity alone is insufficient.

## Phase 9 — Independent extraction simulation

Perform a best-effort simulation using Python/openpyxl or equivalent tooling.

The simulation should:

- enumerate records using the proposed locator;
- resolve fields and supported transformations;
- calculate UTC times;
- classify issues;
- count records;
- detect duplicates;
- sample first, middle, and last records;
- compare extracted values with visible workbook content;
- verify that no unsupported field is required for the output.

A simulation is evidence, not a replacement for runtime verification.

## Phase 10 — Report

### Inspection report

Document:

- workbook structure;
- selected extraction strategy;
- alternatives rejected;
- timezone evidence;
- assumptions;
- formula and cached-value behavior;
- unsupported workbook features;
- record-count reasoning;
- unresolved questions.

### Validation report

State:

- schema validity;
- operator validity;
- source reference validity;
- runtime constraints acknowledged;
- unsupported schema features avoided;
- simulation status;
- runtime verification status;
- expected and extracted records;
- smoke checks;
- warnings and blocking errors;
- approval recommendation.

The validation report is external. NETO does not generate it automatically.

## Missing capability escalation

When the current runtime cannot express the workbook:

1. identify the smallest missing capability;
2. show the workbook pattern requiring it;
3. state which current operator or field is insufficient;
4. propose a general future operator contract;
5. define inputs, outputs, failure behavior, provenance, and a regression test;
6. set `approval_recommendation` to `needs_runtime_capability`;
7. do not generate a supposedly executable key.

Plugins are not an available current-runtime fallback.

## Verification ladder

Use these states precisely:

- `draft`: authored but not fully checked;
- `schema_valid`: JSON Schema and structural checks pass;
- `simulation_passed`: independent simulation matches expectations;
- `runtime_verified`: the real NETO runtime passes against the target workbook;
- `enabled`: an operational owner approves the key.

The current loader does not enforce these states. The CustomGPT must not claim `runtime_verified` without execution evidence.
