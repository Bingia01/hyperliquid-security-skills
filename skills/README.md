# Skills

This directory contains 11 Claude Code skill specifications. Ten are for structured incident research. One is a pre-deployment review tool for HyperEVM developers. Each skill is a markdown file that defines a focused investigation workflow — what it does, what inputs it expects, and what outputs it produces.

Each skill defines inputs, outputs, qualify-before-flagging gates, and anti-patterns. Skills are prompt specifications, not executable code. You use them by invoking them in Claude Code during a research session.

## Pipeline flow

The incident research skills map to the pipeline defined in `CLAUDE.md`. The pre-deployment skill is a separate entry point for developers.

```
  Incident research pipeline
  ──────────────────────────

  incident-classifier → attack-movie-builder → primitive-extractor
                                                       │
                          ┌────────────────────────────┼──────────────┐
                          ▼                            ▼              ▼
                 Domain analyzers              Surface maps    Rule generation
                          │                            │              │
                          ▼                            ▼              ▼
              market-manipulation              hip3-hip4-       heuristic-
              risk-engine-stress               surface-map      generator
              user-compromise
              governance-override
              ecosystem-exploit


  Pre-deployment review (separate entry point)
  ────────────────────────────────────────────

  Solidity source files → hyperevm-pre-ship-review → findings report
```

## Skill index

### Core pipeline

| Skill | What it does | When to use it |
|---|---|---|
| `incident-classifier` | Classifies a raw incident into a bucket (core protocol / market abuse / user compromise / ecosystem app), attack type, confidence level, and evidence gaps. References the attack taxonomy and source hierarchy for structured decision-making. | First step for any new incident. Use before doing deeper analysis. |
| `attack-movie-builder` | Reconstructs a classified incident as a step-by-step causal chain covering initial conditions, attacker setup, trigger action, protocol reaction, amplification, loss realization, defender response, and breakpoints. Each step cites evidence and links causally to the next. | After classification. The output becomes the input for primitive extraction. |
| `primitive-extractor` | Converts an attack movie into reusable building blocks (e.g., "toxic position inheritance," "arbitrary external call"). Maps each step to a named primitive from the canonical library, distinguishes cause from consequence, and maps to threatened invariants. | After building the attack movie. Produces the primitives that feed into heuristic generation. |

### Domain analyzers

| Skill | What it does | When to use it |
|---|---|---|
| `market-manipulation-analyzer` | Runs 7 structured checks for thin-market squeeze risk, spoofing, coordinated wallet positioning, HLP toxic inventory transfer, and forced-unwind liquidity gaps. Each check has a qualify-before-flagging gate. Outputs manipulation likelihood, toxic-transfer risk, HLP loss estimates, and candidate circuit breakers. | When the incident involves pricing abuse, liquidation cascades, or order book manipulation (Bucket B). |
| `risk-engine-stress-tester` | Runs 6 stress tests on forced unwind paths, collateral withdrawal before liquidation, depth-reduced liquidation, cross-asset drawdowns, and portfolio margin sensitivity. Outputs failure paths, loss estimates, and mitigations. Frames results as conditional paths, not confirmed vulnerabilities. | When the incident involves margin or liquidation mechanics. Complements the market manipulation analyzer. |
| `user-compromise-analyzer` | Evaluates 5 behavioral signals against account history: new destinations, sudden bridge-out, rapid liquidation plus withdrawal, multi-asset sweep, and signer profile break. Requires 2+ signals to escalate. Outputs compromise likelihood, spread pattern, timeline, and containment checklist. | When the incident involves stolen funds from a user account (Bucket C). |
| `governance-override-analyzer` | Analyzes whether the system's crisis response creates gameable incentives through a 5-step framework: override likelihood, predictability, incentive creation, precedent analysis, and downstream moral hazard. | When the incident involves or could trigger validator intervention (relevant to Bucket A and some Bucket B cases). |
| `ecosystem-exploit-analyzer` | Post-incident analysis of HyperEVM contracts through 8 structured checks: arbitrary calls, operator permissions, target allowlists, calldata restrictions, post-call invariants, balance accounting, liquidation hooks, and RWA assumptions. Includes Step 0 code classification. | When the incident involves a HyperEVM application or smart contract (Bucket D). |

### Surface maps

| Skill | What it does | When to use it |
|---|---|---|
| `hip3-hip4-surface-map` | Maps the attack surface for HIP-3 (builder-deployed perpetuals, 5 areas) and HIP-4 (outcome/prediction markets, 6 areas). Each area has qualify-before-flagging gates. References threshold profiles for HIP-3 and HIP-4 market types. | When analyzing incidents or risks on builder-deployed or outcome-trading markets rather than core perps. |

### Rule generation

| Skill | What it does | When to use it |
|---|---|---|
| `heuristic-generator` | Converts extracted primitives into detection heuristics following a 6-step procedure: check existing library, draft using template, specify namespaced inputs, write all_of/any_of logic, document false positives, and suggest follow-up tests. Output matches `heuristics.v1.yaml` format. | After primitives are extracted. The output feeds into `rules/heuristics.v1.yaml` and `docs/research/HEURISTIC_LIBRARY.md`. |

### Pre-deployment review

| Skill | What it does | When to use it |
|---|---|---|
| `hyperevm-pre-ship-review` | Reads Solidity source code and checks each contract against the HyperEVM vulnerability taxonomy (arbitrary calls, permission boundaries, approval abuse, reentrancy, upgrade bugs, HyperEVM-specific interactions). Produces findings with severity, line-number evidence, and fix recommendations. | Before deploying a HyperEVM contract. Point it at your Foundry/Hardhat project or a Solidity source directory. |

## Sample runs

The `examples/` directory contains two worked examples showing skill input/output in JSON format:

- `sample-run.hyperevm-router.*` — Ecosystem exploit analyzer applied to a Hyperdrive-style router contract. Shows how contract metadata produces `arbitrary_call_surface` and `operator_permission_scope_creep` alerts.
- `sample-run.market-manipulation.*` — Market manipulation analyzer applied to a JELLY-style thin-market scenario. Shows how market/HLP data produces `thin_market_squeeze_risk`, `toxic_inventory_transfer`, `settlement_cliff`, and `crisis_centralization_trigger` alerts.
