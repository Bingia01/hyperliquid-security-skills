# Hyperliquid Security

An evidence-checked knowledge base, rule engine and Claude Code skill set for
Hyperliquid-ecosystem security: HyperCore markets, HIP-3/HIP-4 deployer
markets, HyperEVM applications and user accounts.

- **Incidents** are sets of sourced claims. Evidence tiers are *derived* from
  the sources, never asserted.
- **Rules** are typed, unit-checked expressions over a declared data
  dictionary, with fixtures that must pass. Missing data yields `unknown`,
  never a silent pass.
- **A read-only adapter** computes features from Hyperliquid's public API, so
  rules run on live markets today.
- **Skills** for Claude Code turn sources and code into records the validator
  accepts.

Read [docs/DESIGN.md](docs/DESIGN.md) for the reasoning, assumptions and
constraints, and for what changed from v1/v2 and why.

## Status at v3.3.0, stated plainly

Live numbers are in the generated reports; these describe the release.

- 14 incidents (derived tiers: 2 confirmed, 8 credible reports, 4 research leads).
  Claim-to-source mappings were verified line by line for JELLY and
  xyz:SKHYNIX; the rest come from a research pass and are marked unchecked.
- 17 rules. Five threshold values are calibrated on recorded market data to
  stated targets (see [calibration.md](docs/generated/calibration.md)); five
  are definitional; the rest are placeholders and say so. Two rules have
  fixtures reconstructed from real incidents; the rest are validated on
  synthetic fixtures, which test logic only.
- Exactly one rule (`mark_jump_short_window`) meets the bar for paging a human.
- Rules needing positions of all accounts, order lifetimes or wallet clusters
  need node data; on public data they return `unknown`.

See [docs/generated/rules.md](docs/generated/rules.md),
[incidents.md](docs/generated/incidents.md),
[coverage.md](docs/generated/coverage.md) and
[calibration.md](docs/generated/calibration.md) - all computed from the data.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'

hyperliquid-security validate                     # check the knowledge base
hyperliquid-security report                       # regenerate docs/generated/

hyperliquid-security snapshot --coin ETH -o eth.json
hyperliquid-security evaluate eth.json            # run every applicable rule

hyperliquid-security snapshot --coin xyz:SKHX --dex xyz -o skhx.json
hyperliquid-security evaluate skhx.json           # HIP-3 profile applied automatically

# History features compare with earlier snapshots of the same market:
# one 4-6 minutes old (mark move), one 55-65 minutes old (open interest growth).
hyperliquid-security snapshot --coin ETH --previous eth-5m.json --previous eth-1h.json -o eth.json

# Record a day of passes for calibration (rerun the same command to resume),
# or run the `record` workflow on GitHub (Actions -> record -> Run workflow).
hyperliquid-security record --out-dir recordings/day1 --hours 24
hyperliquid-security pack recordings/day1 -o knowledge/calibration/data/passes_day1.jsonl.gz
hyperliquid-security calibrate --passes knowledge/calibration/data/passes_day1.jsonl.gz
```

Example (recorded 2026-10-12, see `examples/`): on HIP-3 market xyz:SKHX the
deployer's open interest cap ($1B) is 144x the thinner side's depth within 2%
(about $7M), and the xyz dex holds about $1.0B of deposits against a minimum
slashable stake of about $42M. Rules that need node data report `unknown` and
list the missing inputs.

## Using the skills in Claude Code

Open this repository in Claude Code; the skills in `.claude/skills/` load
automatically.

| Skill | Use it to |
|---|---|
| `analyze-incident` | Turn a postmortem, article or trace into a validated incident record |
| `author-rule` | Write or tune a rule, its features, thresholds and fixtures |
| `monitor-market` | Snapshot a live market and explain every rule outcome |
| `hyperevm-review` | Review HyperEVM contracts before deployment, HyperCore interactions first |

## Layout

```
knowledge/ontology/   control owners, mechanisms, invariants, primitives, surfaces, entities
knowledge/features.yaml   data dictionary (source type for every feature)
knowledge/incidents/  one file per incident: sources, claims, movie, primitives
knowledge/rules/      one file per rule, with fixtures
knowledge/profiles/   per-surface threshold overrides
src/hyperliquid_security/  engine, validator, adapter, CLI
docs/generated/       computed reports (CI fails if stale)
.claude/skills/       Claude Code skills
examples/             recorded snapshots and evaluations
```

## Development

```bash
ruff check src tests && ruff format --check src tests
mypy
pytest
hyperliquid-security validate && hyperliquid-security report --check
```

This is a research tool. It places no orders, signs nothing, and its outputs
are inputs to human judgment.
