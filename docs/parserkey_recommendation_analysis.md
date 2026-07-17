# ParserKey recommendation analysis

This document records the current recommender behavior against the public Google
Sheets corpus in `tests/fixtures/public_google_sheets_cases.json`. The snapshot was
measured on 2026-07-17. Public workbooks are mutable, so parse outcomes can drift.

## Implemented outcome

The bounded structural recommender described below was implemented after the baseline
measurement. With the 15-key catalog, the current 14-case live corpus produces the
expected top-ranked ParserKey in all 14 cases. This includes CCT South America 4 ->
the South America 3 key and Exort Series 30 -> the Series 29 key. Both are explained
as same-family, different-edition matches.

All Google-exported worksheets now stop at exactly the configured 32-row and
40-column sample boundary even when worksheet dimensions are missing. Scores use
ParserKey-derived structural probes, Unicode-aware family identity, per-sheet known
bounds, independent evidence groups, and runner-up margin. Zero-score candidates are
omitted; results below the no-match floor return no recommendation. Draft status is
shown independently from structural strength.

The two newly supplied draft keys rank first for their sources. PARI Universe parses
29/29 matches without issues. Lunar Horse emits its declared 36 matches but remains
blocked on eight playoff records because its key declares time as blocking while its
playoff extractor supplies no time. That is a ParserKey/source-data limitation, not a
recommendation failure.

## Scope and boundary

The recommendation system should identify the most structurally compatible
ParserKey. It should not promise that the current live workbook will parse without
warnings or blocking errors. A ParserKey from edition X is an acceptable
recommendation for edition X+1 when the tournament family and workbook structure
remain compatible.

The initial ranking must remain lightweight. It must not execute every complete
parser. ParserKey runtime behavior, exact-record-count contracts, formula policies,
and source-data completeness are separate concerns.

## Baseline implementation (before this change)

`parser/suggestions.py` creates one `WorkbookFingerprint` and scores every loaded
ParserKey. The nominal fingerprint contains sheet names, reported dimensions, and
tokens from the first 32 rows and 40 columns. The score is:

- up to 55 points for expected sheet-name coverage (52 proportional plus 3 for
  exact-case matches);
- up to 22 points for source filename or tournament-name similarity;
- up to 16 points for header/content similarity;
- 7 points when dimensions cover the inferred requirement, 2 when the sheet exists
  but dimensions do not cover it, and 0 when the sheet is absent.

High confidence requires a score of at least 78 and all expected sheets; Medium
requires at least 55 and all expected sheets. Confidence does not consider the
runner-up margin. All keys, including zero-score and draft keys, participate equally.

For v0 keys, header matching checks generic field hints on the declared header row.
For v2 keys, the so-called header signal instead compares tournament identity tokens
with all sampled content from expected sheets. It does not derive a structural
signature from record locators, anchor columns, tile origins, or field extractors.

## Baseline public-corpus result

The current catalog has a known compatible key for 12 of the 14 cases. The observed
top candidate was acceptable for all 12, including both cross-edition cases. The two
workbooks without a known key received Low confidence, but NETO still displayed an
unrelated best-available candidate.

| Case | Observed top candidate | Score / margin | Expected relationship | Top-key parse snapshot |
| --- | --- | ---: | --- | --- |
| Stake Ranked Episode 3 | `stake_ranked_episode_3_offline_main_event_v1` | 79 / 79 | exact | blocked |
| Exort Series 29 | `exort_series_29_v1` | 79 / 8 | exact | blocked |
| BetBoom RUSH B Part Four | `betboom_rush_b_summit_part_four_v1` | 82 / 17 | exact | blocked |
| NODWIN Clutch Series 10 | `nodwin_clutch_series_10_v1` | 79 / 79 | exact | parsed |
| CCT South America 4 | `cct_2026_sa3_public_schedule_v1` | 87 / 14 | cross-edition | blocked |
| Exort Series 30 | `exort_series_29_v1` | 79 / 8 | cross-edition | blocked |
| StarSeries S20 | `starseries_s20_barcelona_2026_v1` | 79 / 79 | exact, draft key | blocked |
| United21 Season 52 | `united21_season_52_v1` | 79 / 79 | exact, draft key | parsed |
| European Pro League 39 | `european_pro_league_season_39_v1` | 79 / 18 | exact | parsed |
| Esports World Cup Dota 2 | `esports_world_cup_2026_dota2_v1` | 83 / 21 | exact | blocked |
| PARI Universe | `united21_season_52_v1` | 31 / 31 | no known key | failed |
| Lunar Horse Trophy 8 | `united21_season_52_v1` | 31 / 31 | no known key | failed |
| BetBoom Rise of Legends 10 | `betboom_rise_of_legends_10_v1` | 79 / 31 | exact, draft key | blocked |
| BetBoom Bitva Chempionov 4 | `betboom_bitva_chempionov_split_4_v1` | 79 / 17 | exact, draft key | parsed |

Only 4 of the 12 High-confidence structural matches parsed cleanly at this snapshot.
The other 8 were blocked by live-data or ParserKey-contract issues such as missing
teams/times, absent formula caches, changed record counts, or changed cell contents.
This does not make the top candidate incorrect, but it demonstrates that the label
`confidence` is easy to interpret as parse-success confidence when it is only a
structural-match score.

Six cases produced zero-score candidates in the displayed top three. Nine of the 12
High-confidence matches landed on exactly 79 points, showing that the score has little
resolution once an expected sheet and a matching filename are present.

## Baseline material limitations

### The bounded sample is not bounded for Google exports

Every worksheet in all 14 Google-exported XLSX files reported `max_row == 0` and
`max_column == 0` before iteration. The fingerprint passes those zero values to
OpenPyXL, which causes iteration to continue past the intended cap. Although
`SAMPLE_ROWS` is 32, the corpus measurement observed as many as 1,050 sampled rows in
one sheet. This makes runtime content-dependent and means the current implementation
does not meet its stated bounded-work design.

The same exports yielded no non-zero reported dimensions, so the dimension signal was
not useful for any corpus case. Candidates generally received the 2-point fallback.
The current v2 bound inference also computes one global maximum across all record sets
and applies it to every expected sheet instead of deriving requirements per source.

### v2 content matching is identity matching, not structure matching

The v2 content score searches sampled cells for tokens from the key/tournament name.
It does not inspect the structures that actually determine compatibility. Therefore a
key can receive no content points even when its row ranges or tile layout are an exact
match, and can receive content points merely because the tournament name appears in
the workbook.

Common sheet names such as `Schedule` dominate the score. If filename evidence is
weak, several unrelated v2 keys tie at roughly the same score and alphabetical key
name becomes the effective tie-breaker.

### Filename similarity is useful but over-permissive

The containment-style similarity divides overlap by the smaller token set. A small
generic token set can therefore score as a perfect match inside a larger unrelated
name. Pure numeric tokens are discarded. That happens to support Exort 29 -> 30, but
it also removes potentially meaningful edition/game distinctions rather than modeling
them explicitly.

Tokenization only recognizes ASCII `[a-z0-9]`. Cyrillic and other Unicode words are
discarded, so the BetBoom Bitva filename effectively contributes little beyond the
shared `BetBoom` brand. Unique sheet names rescue the correct candidate in the current
corpus, but the filename signal itself is not reliable there.

### Confidence is absolute and status-blind

Confidence ignores the margin between candidates and whether the score is supported
by independent signal groups. Exort 29 and Exort 30 are High at 79 even though the
runner-up is only 8 points behind. Draft ParserKeys are scored and presented exactly
like enabled keys because normalized `ParserKey` objects do not expose top-level
`status`.

Low confidence is communicated, but NETO still lists the strongest unrelated key.
PARI Universe and Lunar Horse both show United21 at 31 because one generic sheet name
partially overlaps. Zero-score keys are also returned because ranking slices the full
catalog before filtering.

### Tests are optimistic

The deterministic suggestion test covers nine positive fixtures and expects each
exact key to rank first with High confidence. It has no no-match, cross-edition,
renamed-file, generic-sheet, Unicode, runner-up-margin, missing-dimension, or bounded-
sample regression. Live tests verify transport only and are correctly opt-in, but
until now their URLs were embedded in the test rather than stored as an evaluation
corpus.

## Implemented design

### 1. Fix fingerprint correctness before tuning weights

- Always request an explicit `1:32 x 1:40` sample, even when worksheet dimensions are
  unknown or zero. Do not pass zero as an iteration limit.
- Represent dimensions as optional. Treat unknown dimensions neutrally instead of as
  a failed lower-bound check. Do not call a full-sheet dimension calculation merely to
  rank keys.
- Track sampled cells by row/column and retain lightweight type information (empty,
  text, numeric/date/time, formula-cache missing), not just one workbook-wide token
  set.
- Derive expected bounds per v2 source/sheet. A bound belonging to one record set must
  not be applied to every sheet.
- Add hard tests that no sheet reads more than the configured row/column or probe cap.

### 2. Compile structural profiles from existing ParserKeys

Build an internal `ParserKeyProfile` from the current v0/v2 contracts; do not create a
parallel registry.

- v0 profile: target sheet, declared header row, mapped columns, and expected field
  header families.
- v2 profile: source-to-sheet mapping, locator type, per-source row/column bounds,
  anchor columns, a bounded sample of row-range anchors or tile origins, and critical
  field access patterns.
- Weight distinctive multi-sheet signatures more than ubiquitous names such as
  `Schedule`. Rarity can be calculated from the currently loaded catalog.
- Probe a small deterministic set of declared coordinates for plausible date, time,
  and team values. This is not a parser run: no record emission, transformations,
  formula policy, validation, or exact-count contract should execute.

The profile must be compiled for repository and session-uploaded ParserKeys through
the same code path.

### 3. Model tournament family separately from edition

Split filename identity into family/brand tokens and edition tokens. `season 52`,
`series 30`, `split 4`, years, and similar markers should be weak edition evidence,
not part of the core family identity. A different edition should produce an explicit
reason such as `Same tournament family; ParserKey is for Series 29` rather than a hard
penalty.

Use Unicode-aware normalization and tokenization. Preserve brand numbers that are
part of a name (for example `United21`) unless an edition marker shows that the number
is an edition.

The first implementation can derive this from existing key names, tournament names,
and `metadata.source_files`. If exceptions prove necessary, add optional matching
metadata to the existing v2 schema (for example family id and aliases). That would be
an additive schema change; a sidecar registry should be avoided.

### 4. Recalibrate score and confidence

A starting allocation for corpus calibration is:

- 40 points: required/distinctive sheet signature;
- 35 points: bounded structural probes derived from the ParserKey;
- 20 points: tournament family and source filename evidence;
- 5 points: known per-sheet bounds or sampled density.

Apply explicit negative evidence for missing required sheets or failed structural
probes. Unknown dimensions should add neither a bonus nor a penalty. An exact source
SHA-256 match can be a strong bonus when available, but a hash mismatch must not
disqualify cross-edition reuse.

Confidence should consider score, evidence diversity, and runner-up margin. Initial
thresholds to calibrate against fixtures are:

- High: score >= 80, at least two independent signal groups, and margin >= 12;
- Medium: score >= 60, at least one structural signal, and margin >= 8;
- Low: any weaker but still positive candidate;
- No match: no structural evidence or top score below a calibrated floor (start at
  45).

These numbers are hypotheses, not contracts; calibration should optimize the versioned
corpus rather than preserve current scores.

### 5. Make UI meaning explicit

- Show at most three positive-score candidates. Never show a 0% candidate.
- If the no-match rule fires, show no recommendation and direct the user to the
  ParserKey Creator/upload flow.
- Use `Structural match: High/Medium/Low`, not a generic confidence label.
- Keep explicit user confirmation before parsing.
- Show draft/enabled status separately from structural match strength. A draft key can
  still be the correct structural candidate, but users should know it is unverified.
- Explain cross-edition recommendations directly: same family/layout, different
  edition.
- Keep the recommended selector/modal first, then one compact recommended row with its
  reasons, followed by up to two alternatives. Detailed tournament/timezone/layout
  metadata can remain collapsed.

## Test strategy

1. Keep `public_google_sheets_cases.json` as the URL and expected-compatibility source
   of truth. Empty accepted-key lists mean no key is currently known.
2. Use the existing deterministic XLSX corpus plus generated cross-edition, no-match,
   missing-dimension, draft-status, score-margin, and zero-filter regressions. Normal
   tests must not require Google availability.
3. Keep the 14-case live check opt-in and connection-reusing. It should report drift
   without making normal CI dependent on mutable Sheets.
4. Keep parser-result tests separate. Recommendation tests assert compatible identity;
   parser regression tests assert extraction behavior.

Acceptance covered by this implementation includes:

- all 14 current public cases rank an acceptable key first;
- CCT SA4 -> SA3 and Exort 30 -> 29 remain explicitly supported;
- PARI Universe and Lunar Horse rank their new draft keys first;
- no zero-score candidates are returned or rendered;
- every fingerprint/probe stays within its configured work cap;
- confidence uses a runner-up margin and independent structural evidence;
- no complete parser is executed during initial ranking.
