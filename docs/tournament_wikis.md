# Tournament-page wiki ingestion

Tournament-page ingestion is provider-oriented under `wiki_ingestion/`. URL routing, HTTP policy, Leaguepedia extraction, normalization, and result classification stay outside `app.py`. The adapter emits NETO's existing `ParsedMatch`, `OfficialMatchMetadata`, `IngestionMetadata`, and `ParseResult`, then reuses shared validation, preview, filtering, and exports.

## Preliminary supported scope

| Provider | Supported scope | URL form | API strategy |
|---|---|---|---|
| Leaguepedia | League of Legends tournaments | `https://lol.fandom.com/wiki/<page>` | MediaWiki Cargo `MatchSchedule` query |

`leaguepedia.com/wiki/...` aliases are accepted and routed to the LoL Fandom API. Liquipedia and generic MediaWiki/Fandom pages are deliberately rejected in this release.

## Leaguepedia adapter

The adapter calls `https://lol.fandom.com/api.php?action=cargoquery`, queries `MatchSchedule` by exact `OverviewPage`, excludes nullified copies using Leaguepedia's query convention, orders by UTC time and source position, and retrieves all pages up to a defensive 5,000-match ceiling.

It consumes `DateTime_UTC`, `HasTime`, `Team1`, `Team2`, `BestOf`, `Phase`, `Round`, `Tab`, `MatchId`, `Winner`, `Stream`, and `OverviewPage`. Leaguepedia's declaration is visible in [Module:CargoDeclare/MatchSchedule](https://lol.fandom.com/wiki/Module:CargoDeclare/MatchSchedule).

No credential or Streamlit secret is required. Deployment needs outbound HTTPS access to `lol.fandom.com`. Successful Streamlit results are cached for one hour; failures are not cached.

## Result classification

- **Complete extraction:** every API candidate has reliable date, explicit time, Team A, and Team B, with no optional-field warnings.
- **Partial extraction:** reliable records are returned while ambiguous candidates are skipped with visible warnings, or retained records have optional-field warnings.
- **No schedule found:** Cargo returns a valid empty result; `legitimate_empty=true` and export remains an empty valid result.
- **Unsupported page structure:** candidates exist but none has all four reliable required values; the fetch fails rather than presenting silent partial success.
- **Source/API failure:** HTTP, provider error payload, response-shape, or pagination-ceiling failure.
- **Invalid or unsupported URL:** non-HTTPS, credential-bearing, malformed, unsafe-title, Liquipedia, or unsupported host URLs.

Dates and times are normalized to UTC. Published `TBD` team values are retained as wiki placeholders; a missing team value is not. Optional stage, BO, and match labels may be empty only with warnings. Source page, strategy, fetch time, request count, provider match ID, competition, state, and supplied tournament URL remain available as provenance.

## Known limitations

- Coverage depends on the tournament populating `MatchSchedule` with an exact `OverviewPage`. Pages using a different Cargo model report no schedule or unsupported structure.
- Streams/results remain provenance-only and are not added to NETO's fixed ten-column CSV.
- Normal tests use deterministic fixtures. `tests/test_wiki_live.py` is opt-in and is not part of the default suite.
- Liquipedia support is intentionally deferred beyond this preliminary release; no Liquipedia API key, endpoint, or rate-limit configuration is present in the deployed application.
