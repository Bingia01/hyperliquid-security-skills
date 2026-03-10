# Heuristic library

Each heuristic is written in three layers:
1. a human-readable research heuristic,
2. a machine-usable rule in `rules/heuristics.v1.yaml`,
3. a threshold profile in `rules/threshold_profiles/`.

## thin_market_squeeze_risk
- Detects: markets where open interest and liquidation pressure are too large relative to executable depth.
- Why it matters: this is the skeleton of JELLY- and POPCAT-style manipulation.
- Signals: OI/depth imbalance, liquidation notional/depth imbalance, fast venue move, anchor divergence.
- Evidence tier: confirmed / credible_report
- Anchor cases: JELLY, POPCAT

## protocol_absorbed_toxic_position
- Detects: liquidation or transfer logic that pushes hard-to-unwind exposure into HLP or another backstop.
- Why it matters: once the system inherits the wrong inventory, the attacker no longer needs clean market exit liquidity.
- Signals: system inventory growth, no bounded unwind plan, inherited size > normal depth.
- Evidence tier: confirmed
- Anchor cases: ETH margin drain, JELLY

## strategic_margin_drain
- Detects: outsized positions that become liquidatable after discretionary collateral withdrawal.
- Why it matters: a system can be exploited without a code bug if incentives reward forced unwind over normal exit.
- Signals: large notional, collateral withdrawal, approach to maintenance threshold, unwind routed to backstop.
- Evidence tier: confirmed
- Anchor cases: ETH margin drain

## settlement_cliff
- Detects: cases where mark, index, and settlement pathways diverge in a weakly anchored market.
- Why it matters: rule-dependent repricing can be gamed near crisis points.
- Signals: mark/index spread, emergency repricing, end-window prints dominating outcome.
- Evidence tier: confirmed / theoretical
- Anchor cases: JELLY, weak-anchor synthetic markets

## crisis_centralization_trigger
- Detects: conditions where a normal “decentralized” path is likely to be replaced by human or validator intervention.
- Why it matters: once users believe there is a validator put, incentives change.
- Signals: emergency delisting, manual settlement, absence of precommitted circuit breakers.
- Evidence tier: confirmed
- Anchor cases: JELLY

## coordinated_multi_wallet_positioning
- Detects: several wallets funded in a short window and opening similar positions in the same asset.
- Why it matters: sharded capital can hide coordination and amplify manipulation.
- Signals: common funding source, same asset, same direction, same time band.
- Evidence tier: credible_report
- Anchor cases: JELLY, POPCAT

## spoofing_wall_reversal
- Detects: a large visible order that is cancelled quickly around a price swing.
- Why it matters: visible depth may be fake.
- Signals: very large displayed order, short lifetime, reversal after liquidity follows.
- Evidence tier: credible_report
- Anchor cases: POPCAT

## account_behavioral_break
- Detects: abrupt change in a wallet’s transfer, bridge, trade, or signer behavior.
- Why it matters: for user-compromise cases, behavior is the detection surface.
- Signals: new bridge destination, rapid sweep, unusual asset mix, signer change if available.
- Evidence tier: credible_report
- Anchor cases: key compromise

## arbitrary_call_surface
- Detects: contracts or routers that can invoke external targets too broadly.
- Why it matters: overbroad call surfaces often turn one privileged path into total loss.
- Signals: arbitrary call entrypoints, weak allowlists, missing post-call checks.
- Evidence tier: confirmed
- Anchor cases: Hyperdrive
- Taxonomy reference: `docs/architecture/hyperevm_vulnerability_taxonomy.md` — Arbitrary external call

## operator_permission_scope_creep
- Detects: operator-like privileges broader than the minimum needed for the feature.
- Why it matters: excessive authority multiplies blast radius.
- Signals: broad approvals, router overreach, admin-like actions exposed to convenience flows.
- Evidence tier: confirmed
- Anchor cases: Hyperdrive
- Taxonomy reference: `docs/architecture/hyperevm_vulnerability_taxonomy.md` — Permission boundary failure
