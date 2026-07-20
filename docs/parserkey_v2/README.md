# NETO ParserKey v2 contract

ParserKey v2 is NETO's declarative contract for schedules that do not fit the original linear-table format. Runtime keys live in `parser_keys/`, validate against `neto_parserkey_v2.schema.json`, and may use only operators declared in `neto_operator_catalog_v1.json` and implemented by the runtime.

## Runtime support

The current implementation supports:

- exact worksheet selection;
- row scans, non-contiguous row ranges, and horizontal tile grids;
- absolute, column, relative, and merged-origin cell access;
- contexts, regex extractors, predicates, fallbacks, defaults, and overrides;
- safe cached-formula handling and direct A1-reference resolution;
- deterministic date/time transforms, timezone normalization, validation, and provenance.

Required operators must be listed in `runtime.required_operators`. Plugins are rejected by the current runtime. Every record set emits `neto.normalized_match.v1`, and record-count bounds independently control warning or blocking behavior.

## Source metadata

`metadata.source_files[].filename` is retained because it supports workbook recommendations and provenance. `metadata.source_files[].sha256` remains an optional schema field for compatible private workflows, but distributed ParserKeys omit it.

Formula text and workbook-library objects never become normalized values. A missing participant or time becomes `TBD` only when a field or key explicitly declares that policy; unresolved required values otherwise produce visible validation issues.

See [operator_semantics.md](operator_semantics.md) for the executable semantics. Authoring examples are available in `examples/neto_parserkey_template_v2.json`.
