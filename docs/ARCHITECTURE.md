# Repository architecture

This repository is organized around one research pipeline:

`incident -> attack movie -> primitive -> invariant -> heuristic -> rule -> threshold profile`

## Why this layout exists
Hyperliquid-class security analysis cannot be reduced to “smart contract hacks.” The public incident record spans:
- core market design and liquidation risk,
- market-structure abuse,
- user-account compromise,
- ecosystem-app contract issues,
- platform stress and reconnaissance events.

## Top-level directories
- `docs/architecture/` — the high-level attack taxonomy and surface-specific deep dives (including the HyperEVM vulnerability taxonomy)
- `docs/analysis/` — invariants, breakers, and system assumptions
- `docs/research/` — attack taxonomy, primitive library, heuristic library, coverage map
- `data/incidents/` — machine-readable incident records, split by evidence tier
- `case_studies/` — human-readable incident analysis, split by evidence tier
- `rules/` — machine-readable heuristics and threshold profiles
- `skills/` — Claude Code skill specs
- `templates/` — templates for adding incidents and heuristics

## Evidence hygiene
Weak evidence may be recorded, but it must not drive strong rules. Research leads preserve coverage without contaminating the core heuristic layer.
