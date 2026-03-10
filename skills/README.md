# Skills

This directory contains 11 Claude Code skill specifications. Ten are for structured incident research. One is a pre-deployment review tool for HyperEVM developers. Each skill is a markdown file that defines a focused investigation workflow — what it does, what inputs it expects, and what outputs it produces.

Skills are prompt specifications, not executable code. You use them by invoking them in Claude Code during a research session.

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
| `incident-classifier` | Takes raw incident information (tweets, postmortems, wallet traces, code snippets) and assigns it to a bucket (core protocol / market abuse / user compromise / ecosystem app), an attack type, a confidence level, and flags evidence gaps. | First step for any new incident. Use before doing deeper analysis. |
| `attack-movie-builder` | Turns a classified incident into a step-by-step causal chain covering initial conditions, attacker setup, trigger action, protocol reaction, amplification, loss realization, defender response, and breakpoints. | After classification. The output becomes the input for primitive extraction. |
| `primitive-extractor` | Converts an attack movie into reusable building blocks (e.g., "toxic position inheritance," "arbitrary external call"). Maps each step to a named primitive from the library in `docs/research/ATTACK_PRIMITIVES.md`. | After building the attack movie. Produces the primitives that feed into heuristic generation. |

### Domain analyzers

| Skill | What it does | When to use it |
|---|---|---|
| `market-manipulation-analyzer` | Checks for thin-market squeeze risk, spoofing, coordinated wallet positioning, HLP toxic inventory transfer, and forced-unwind liquidity gaps. Outputs manipulation likelihood, toxic-transfer risk, HLP loss estimates, and candidate circuit breakers. | When the incident involves pricing abuse, liquidation cascades, or order book manipulation (Bucket B). |
| `risk-engine-stress-tester` | Stress-tests forced unwind paths, collateral withdrawal before liquidation, depth-reduced liquidation, cross-asset drawdowns, and portfolio margin sensitivity. Outputs failure paths, loss estimates, and mitigations. | When the incident involves margin or liquidation mechanics. Complements the market manipulation analyzer. |
| `user-compromise-analyzer` | Detects private key compromise, operator misuse, and abnormal sweep/bridge behavior. Looks for behavioral breaks: new destinations, sudden bridge-outs, rapid multi-asset sweeps, signer profile changes. | When the incident involves stolen funds from a user account (Bucket C). |
| `governance-override-analyzer` | Analyzes when a system is likely to switch from automated rules to human or validator discretion. Checks for emergency delisting, manual settlement, manual repricing, and ad hoc exceptions. Asks whether the crisis response creates a gameable incentive. | When the incident involves or could trigger validator intervention (relevant to Bucket A and some Bucket B cases). |
| `ecosystem-exploit-analyzer` | Reviews HyperEVM contracts for arbitrary call surfaces, operator permissions, target allowlists, calldata restrictions, post-call invariant checks, balance accounting, and liquidation hooks. References `docs/architecture/hyperevm_vulnerability_taxonomy.md`. | When the incident involves a HyperEVM application or smart contract (Bucket D). |

### Surface maps

| Skill | What it does | When to use it |
|---|---|---|
| `hip3-hip4-surface-map` | Maps the attack surface specific to HIP-3 (builder-deployed perpetuals) and HIP-4 (outcome/prediction-style markets). HIP-3 focus: builder oracle design, leverage caps, settlement authority, portfolio margin interactions. HIP-4 focus: resolution source quality, settlement rule ambiguity, last-minute print domination, event-source manipulation. | When analyzing incidents or risks on builder-deployed or outcome-trading markets rather than core perps. |

### Rule generation

| Skill | What it does | When to use it |
|---|---|---|
| `heuristic-generator` | Turns extracted primitives into human-readable heuristics, machine-usable logic, and simulation recipes. Each heuristic includes: name, status, what it detects, why it matters, required data, logic sketch, false positives, and follow-up tests. | After primitives are extracted. The output feeds into `rules/heuristics.v1.yaml` and `docs/research/HEURISTIC_LIBRARY.md`. |

### Pre-deployment review

| Skill | What it does | When to use it |
|---|---|---|
| `hyperevm-pre-ship-review` | Reads Solidity source code and checks each contract against the HyperEVM vulnerability taxonomy (arbitrary calls, permission boundaries, approval abuse, reentrancy, upgrade bugs, HyperEVM-specific interactions). Produces findings with severity, line-number evidence, and fix recommendations. | Before deploying a HyperEVM contract. Point it at your Foundry/Hardhat project or a Solidity source directory. |

## Sample runs

The `examples/` directory contains two worked examples showing skill input/output in JSON format:

- `sample-run.hyperevm-router.*` — Ecosystem exploit analyzer applied to a Hyperdrive-style router contract. Shows how contract metadata produces `arbitrary_call_surface` and `operator_permission_scope_creep` alerts.
- `sample-run.market-manipulation.*` — Market manipulation analyzer applied to a JELLY-style thin-market scenario. Shows how market/HLP data produces `thin_market_squeeze_risk`, `toxic_inventory_transfer`, `settlement_cliff`, and `crisis_centralization_trigger` alerts.
