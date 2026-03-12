# Changelog

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
