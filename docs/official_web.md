# Official web schedule ingestion

NETO retrieves only allowlisted public responses used by the four official websites. Every adapter emits `ParsedMatch` objects and a normal `ParseResult`; ParserKeys are not involved.

## Source strategies

### League of Legends Esports

- Strategy: `riot_graphql_persisted_query`.
- Endpoint: `https://lolesports.com/api/gql`.
- Operation: `homeEvents`, restricted to match events and scheduled, live, and completed states.
- Pagination: both `pages.older` and `pages.newer` cursors are traversed, with cycle detection and a 25-page safety limit.
- Risk: Riot may rotate the persisted-operation hash when its field selection changes. The bundled value can be overridden with the non-secret `NETO_RIOT_HOME_EVENTS_HASH` environment variable. GraphQL errors or missing core paths fail the whole fetch.

The initial server-rendered page contains only the site's current home window and cannot reliably cover arbitrary requested ranges, so it is not used as an automatic fallback.

### VALORANT Esports

- Strategy: `riot_graphql_persisted_query`.
- Endpoint: `https://valorantesports.com/api/gql`.
- Uses its own registered adapter and `sport=val`, while sharing the defensive Riot transport and pagination implementation.
- Official league IDs/names are preserved as Competition metadata. The normalized Stage joins the league name and Riot block name so simultaneous tournaments remain distinguishable. No region is inferred when Riot does not supply one.

### Call of Duty League

- Strategy: `cod_next_data_season`.
- Endpoint: the official schedule with `season=<year>&stage=entire-season`.
- The adapter parses `script#__NEXT_DATA__`, finds `cdlEntireSeasonMatchCards` by semantic key, and combines completed and upcoming groups.
- December ranges also inspect the following season because a season may begin in the prior calendar year.
- Risk: the CMS nesting can move. A published season without the semantic match-card block is treated as schema failure. BO is not inferred when absent and produces `bo_missing`.

The official standings page is not used because the schedule state contains IDs, teams, status, and timestamps directly.

### Rainbow Six Siege

- Strategy: `r6_next_data_month`.
- Endpoint: `/calendar/YYYY-MM` on the official Ubisoft site.
- Each response contains the complete month's `pageData.matches`; day selection in the website is a client-side filter over that payload.
- NETO retrieves every UTC month intersecting the requested range and then applies the exact range boundary.
- Status mapping is `1=scheduled`, `2=live`, and `3=completed`. Unknown values are retained with a warning.
- `isTimeTBD=true` retains the official provisional timestamp and adds `official_time_tbd`.

Competition pages are not used as fallback because the month payload reliably covers ranges.

## Reliability rules

- Requests are HTTPS-only and restricted to each adapter's official host.
- Connect/read timeouts are explicit; `429` and `5xx` receive one retry with a maximum three-second delay.
- Date ranges are at most 90 inclusive days and are converted from the selected IANA timezone to a half-open UTC interval.
- Required-page failures never return partial data. Valid empty responses return `parsed` with `legitimate_empty=true`.
- Official IDs deduplicate first. Remaining equal `(start_time_utc, team_a, team_b)` tuples use NETO's existing duplicate warning.
- Stage uses the available Competition plus source stage label. Competition remains available in the collapsed source-metadata filters and provenance table.
- No response headers, credentials, cookies, tokens, or analytics payloads are stored in test fixtures.
