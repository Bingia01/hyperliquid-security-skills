# Changelog

## v3.3.1

- **Recorder survives network failures.** The info client now retries dropped
  connections (`http.client.RemoteDisconnected`, resets, other `OSError`s) like
  a 5xx; before, one dropped connection ended a recording session (it did, on
  2026-10-13 at 14:57 UTC, after two hours). A pass whose shared requests still
  fail after retries is skipped and the session continues. Log lines are
  flushed as written.
- **`record` workflow keeps partial segments.** The recording step has its own
  time limit, and a segment's passes are uploaded even when recording fails or
  times out.

## v3.3.0

- **Recording sessions.** `record --out-dir DIR --hours H` writes one gzipped
  file per pass and a manifest; rerunning resumes the session, and
  `--stop-after-hours` ends a run early with exit status 3. `pack` merges a
  session into one file; `calibrate --passes` also reads a session directory.
  Each row records the capital of the backstop that would inherit the market's
  liquidations. (`record --out FILE --passes N` is gone.)
- **`record` workflow** (`.github/workflows/record.yml`, run on demand): a
  session as six-hour segments that resume one another, then `pack` and
  `calibrate`, uploaded as the `recording` artifact.
- **Growth rule materiality** is now `min_growth_usd` ($250k, placeholder)
  instead of 1% of backstop capital, which was vacuous on HIP-3 (backstops held
  $0-$104k). The rule no longer reads backstop features.
- `calibrate` computes the growth rule's depth threshold to an alert budget of
  one episode per day per surface (floor 1.0, rounded up).
- Removed `calibration.base_rate` and the base-rate test, superseded by the
  calibration.

## v3.2.0

- **Open-interest growth rule** `open_interest_growth_exceeds_depth`: the last
  hour's new open interest against the thinner side's 2% depth (definitional
  1.0) and against the backstop's capital (placeholder 1%). Report mode,
  uncalibrated; its base rate on the committed recording is stated in the rule
  and pinned by a test.
- Features `market.open_interest_base_asset` (public API) and
  `market.open_interest_change_usd_1h` (history: asset units, valued at the
  current mark, so a price move is not growth).
- `snapshot --previous` is repeatable; each history feature uses the earlier
  snapshot of the same market whose age fits its window, and says why when
  none does.
- `calibration.base_rate` evaluates a rule as written on recorded samples;
  backstop capital measured on 2026-10-13 is committed for it.

## v3.1.0

- **Calibrated thresholds.** `open_interest_exceeds_depth` (validator-operated
  67.27, HIP-3 39.35), `oi_cap_exceeds_depth` (558.64) and
  `mark_jump_short_window` (validator-operated 832.1 bps, HIP-3 725.3 bps),
  computed from committed recordings of all 337 listed perps; method, data,
  limitations and incident checks in `knowledge/calibration/`.
- `record` and `calibrate` commands; calibration targets are a cross-sectional
  rank (precondition rules) or an alert-episode budget (alert rules).
- Threshold basis `definitional`; `calibrated` thresholds must cite their
  result and match it exactly; fixtures run with their surface's profile.
- A test recomputes every calibrated value from the committed data.
- Finding: archived 20-level books cannot measure 2% depth (BTC: 0 of 157,225
  snapshots; JELLY: levels spanned 0.7%); the archive check bounds ratios
  instead.

## v3.0.0

Rebuilt from first principles; see `docs/DESIGN.md` for the full rationale and
the defects found in v2.

- **Knowledge base as validated data.** `knowledge/` holds the ontology,
  feature dictionary, incidents, rules and profiles; pydantic models reject
  unknown keys; a strict YAML loader rejects duplicate keys.
- **Two-axis classification** (`control_owner`, `mechanisms`, `code_defect`)
  replaces the four-bucket / five-surface / A-D schemes, which disagreed.
- **Derived evidence tiers** from claim-level sources replace asserted
  `status` / `confidence` / `confidence_score`.
- **Rule engine.** Safe expression language with unit and scope checking,
  three-valued logic (`unknown` on missing data), named thresholds, profiles
  that override by name, fixtures that must pass.
- **Evidence policy enforced in code.** Research leads cannot raise a rule's
  status; alerting needs a credible anchor and a reconstructed or recorded
  firing fixture; anchors must exhibit the primitives a rule detects.
- **Read-only public API adapter** with correct depth measurement (v2's method
  undercounted depth within 2% by 6x-94x) and HLP liquidator child vaults.
- **Incidents corrected and extended.** JELLY loss relabeled as peak
  unrealized (HLP ended about +$703K) with source disagreements recorded;
  added XPL hyperp squeeze, July 2025 API outage, October 2025
  auto-deleveraging, FARTCOIN, Purrlend and the xyz:SKHYNIX HIP-3 oracle
  failure.
- **Rules rewritten.** Fixed the arbitrary-call blind spot, the
  two-excess-powers requirement, the unused funding-link input and the
  vault-wide-over-single-market ratio; thresholds are relative to depth,
  equity or stake.
- **Skills** moved to `.claude/skills/<name>/SKILL.md` so Claude Code loads
  them; eleven specifications consolidated into four.
- **Generated reports** replace hand-kept consistency and coverage matrices.
- CI: lint, format, strict typing, tests, validation, report freshness.


## v2

### Skill specification expansion

All 10 incident research skills expanded from 15-32 lines to 60-120 lines each. Every skill now includes:
- Purpose statement
- Reference documents (linked to taxonomy, primitives, invariants)
- Typed inputs with minimum requirements
- Qualify-before-flagging gates at each procedure step
- Numbered procedure with step-by-step instructions
- Structured output format (YAML)
- Worked example references tied to real incidents
- Relationship to upstream and downstream skills
- Anti-patterns (common mistakes to avoid)
- Limitations

### Data dictionary

New file: `docs/DATA_DICTIONARY.md`. Defines all 56 unique inputs referenced in `rules/heuristics.v1.yaml`:
- 9 namespaces: market, hlp, account, cluster, order, contract, permission, system, governance
- Each input documented with description, source type (api_direct, derived, static_analysis, hypothetical), source detail (API endpoint or computation method), and heuristic cross-references
- 11 api_direct, 30 derived, 11 static_analysis, 4 hypothetical inputs

### Skills README

Updated skill descriptions to match expanded purpose statements. Added note about qualify-before-flagging and anti-patterns as standard skill features.

## v1

- Hyperliquid attack taxonomy and visual attack surface map
- HyperEVM smart contract vulnerability taxonomy
- Evidence-tiered incident records (confirmed, credible_reports, research_leads)
- Case studies for all documented incidents
- Seven system invariants and breaker analysis
- Attack primitive library
- Heuristic library with 10 machine-readable rules
- Surface-specific threshold profiles (core perps, HIP-3, HIP-4, HyperEVM apps)
- Incident schema and master incident ledger
- 11 Claude Code skill specs including pre-deployment HyperEVM review
- Skills index with pipeline flow and sample runs
- Consistency matrix and coverage matrix
- Open-source boundary and contributing guidelines
