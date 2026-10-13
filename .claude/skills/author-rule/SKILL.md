---
name: author-rule
description: Draft or change a detection rule in knowledge/rules/ - its consumer and action, features, named thresholds with units, condition, false positives and fixtures - so that it compiles, type-checks and passes its fixtures. Use when turning a primitive or incident into a monitor, tuning thresholds, or adding a feature to the data dictionary.
---

# Author a rule

A rule is `knowledge/rules/<id>.yaml`. It is done when
`hyperliquid-security validate` and `pytest` pass and the generated
`docs/generated/rules.md` states honestly what the rule has and has not been
shown to do.

## Before writing anything, answer three questions

1. **Who acts on it, and what do they do?** (`consumer`, `action`.) If no one
   can act in time, the rule is a dashboard metric, not a monitor; say so in
   the summary. An HLP depositor has a four-day lockup; a HIP-3 deployer can
   halt a market within seconds.
2. **What stage is it?** `precondition` (exposure before any attack - long
   lead time, measure continuously), `active_attack` (minutes of lead time,
   higher false-positive cost), `post_loss` (response and forensics),
   `pre_deployment` (code review).
3. **Can the data be had?** Every feature must exist in
   `knowledge/features.yaml` with an honest `source.type`. For
   `public_api`, confirm the request and field against the live API before
   relying on it. Known limits: `l2Book` returns 20 levels per side (depth
   needs `nSigFigs` aggregation); there is no endpoint listing all positions;
   order lifetimes need node data; HLP inventory lives in the liquidator child
   vaults, not the parent.

## Writing the rule

- **Relative, not absolute, thresholds.** Divide by depth, equity or stake so
  one value means the same thing on BTC and on a thin market. An absolute
  "$10M order" threshold fires constantly on BTC and never on a small market.
- **Every number is a named threshold** with a `unit` and a `basis`
  (`placeholder`, `incident_reconstruction`, `calibrated`). Numeric literals
  other than 0 in a condition are rejected. Profiles override thresholds by
  name, per surface.
- **Units are checked.** `usd / usd` is a ratio; basis points are their own
  unit; convert with `to_bps(...)` or use `bps_diff(a, b)`.
- **Scope.** `scope` lists the entities the rule may read. Reading a
  vault-wide total and a single market's depth in one rule needs both declared;
  that is deliberate friction.
- **Missing data yields `unknown`, never `silent`** - provided nobody fills
  the gap upstream. Adapters and fixtures must leave an unmeasured feature
  absent, never 0 or a default: zero depth means "infinitely thin" and zero
  position means "no position", so a default silently changes the answer.
- **One excess capability is enough** for permission rules; do not count.

## Fixtures (required)

- At least one `fires` and one `silent` fixture; add `unknown` (missing data)
  and boundary cases (exactly at threshold).
- `synthetic` fixtures test logic only.
- A `reconstructed` fixture rebuilds an anchor incident's values, and every
  value the rule reads must cite a claim id from that incident in `evidence`.
  If the incident record lacks the number, you cannot reconstruct it - add the
  claim with its source first, or leave the rule unvalidated.

## Evidence policy (enforced)

- Status is derived from anchors: `observed` (a confirmed anchor),
  `reported` (credible report), `theoretical` (leads only, or none).
- `mode: alert` (pages a human) needs a non-theoretical status **and** a
  reconstructed or recorded fixture from an anchor that fires. Otherwise use
  `mode: report`.
- Anchors must exhibit at least one primitive the rule `detects`.
- `alert` rules document at least two false-positive scenarios; `report`
  rules at least one.

## Calibrating a threshold

A threshold's `basis` says where it comes from: `placeholder` (judgment),
`definitional` (follows from the ratio's meaning, e.g. 1.0 = cannot exit
within the band), `incident_reconstruction`, or `calibrated`. A calibrated
threshold names the result in `knowledge/calibration/` that computed it, and
the validator checks the value matches.

Decide the **target** before touching data:
- precondition rules: a cross-sectional rank ("the most exposed tenth of
  markets") on each market's median ratio;
- alert and active-attack rules: an alert budget (episodes per day across a
  surface), because a pager tolerates a fixed number of interruptions.
- When a rule has two thresholds, calibrate one and hold the other fixed, and
  say which.

Then record and compute. A recording session resumes when the same command is
rerun (exit status 3 means it stopped early), so a day can span restarts. On
GitHub, the `record` workflow (Actions -> record -> Run workflow) splits a
session into six-hour jobs and uploads the packed passes and the calibration
results as the `recording` artifact.

```bash
hyperliquid-security record --out-dir recordings/2026-10-13 --hours 24 --interval-seconds 600
hyperliquid-security pack recordings/2026-10-13 \
  -o knowledge/calibration/data/passes_2026-10-13.jsonl.gz
hyperliquid-security record --candles --out candles_5m.json
hyperliquid-security calibrate --passes knowledge/calibration/data/passes_2026-10-13.jsonl.gz \
  --candles candles_5m.json --anchors knowledge/calibration/data/anchor_moves.json
```

Apply the printed values to the rule (`basis: calibrated`,
`calibration: <id>`) and to profiles, and run `validate`. Never tune a
threshold to make an anchor fire; calibrate on the target, then report whether
anchors fire as a check. Archived order books hold 20 full-precision levels,
which never reach a 2% band on liquid markets - depth-based calibration needs
live recording with `nSigFigs` aggregation.

## Finish

```bash
hyperliquid-security validate
pytest
hyperliquid-security report
```
