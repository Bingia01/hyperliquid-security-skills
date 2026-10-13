# Changelog

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
