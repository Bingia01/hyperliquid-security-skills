# CLAUDE.md

This repository is a knowledge base plus a rule engine. The data lives in
`knowledge/`; the code in `src/hyperliquid_security/` validates and evaluates
it. Read `docs/DESIGN.md` before changing structure.

## Workflow

- Analyzing an incident: use the `analyze-incident` skill. Output is
  `knowledge/incidents/<id>.yaml`.
- Writing or tuning a rule: use the `author-rule` skill. Output is
  `knowledge/rules/<id>.yaml` with passing fixtures.
- Checking a live market: use the `monitor-market` skill.
- Reviewing HyperEVM contracts: use the `hyperevm-review` skill.
- Calibrating thresholds: `hyperliquid-security record`, then `calibrate`
  (see the `author-rule` skill); results go to `knowledge/calibration/`.

After any change to `knowledge/` or `src/`:

```bash
hyperliquid-security validate
pytest
hyperliquid-security report        # regenerate docs/generated/; never edit those by hand
```

## Rules that are never relaxed

- Never cite a source you have not read, and never write a URL you did not
  fetch or see verbatim. Set `citations_checked: true` only after reading every
  cited source against every claim citing it.
- A claim cites only sources that state it. Disagreements between sources
  become separate claims.
- Classify on two axes: `control_owner` (whose control failed) and
  `mechanisms` (how). A loss on Hyperliquid is a core-protocol code defect only
  when the evidence shows software violating its own specification.
- Record losses with their basis: `realized`, `peak_unrealized` or
  `reported_unspecified`.
- Evidence tiers and rule statuses are derived; never write them by hand.
- Do not fill missing data with defaults. Absent means `unknown`.
- Every number in a rule condition is a named threshold with a unit and a
  basis. Placeholders say so; calibrated values cite their calibration result,
  and nobody tunes a threshold to make an anchor fire.
- Facts about Hyperliquid mechanics change; verify against the live API or
  current docs before relying on them, and date what you verified.
