# Skill — Market Manipulation Analyzer

## Purpose

Investigate Bucket B incidents — pricing abuse, liquidation cascades, order book manipulation, and thin-market exploitation. This skill runs 7 structured checks against market and HLP data to determine manipulation likelihood, toxic-transfer risk, and HLP loss exposure.

## Reference documents

- `docs/architecture/hyperliquid_attack_taxonomy.md` — Market Structure surface (Order Book Liquidity, Mark Price Logic, Oracle Anchors, Cross-Exchange Pricing)
- `docs/research/ATTACK_PRIMITIVES.md` — pricing primitives (`thin_market_mark_distortion`, `cross_exchange_price_anchor_abuse`, `weak_anchor_settlement`, `spoof_wall_support`) and risk-engine primitives (`toxic_position_inheritance`, `liquidation_depth_mismatch`)
- `docs/analysis/INVARIANTS_AND_BREAKERS.md` — Invariant 1 (Liquidation absorbability), Invariant 2 (Fair-price integrity)
- Related heuristic IDs: `thin_market_squeeze_risk`, `toxic_inventory_transfer`, `settlement_cliff`, `spoofing_wall_reversal`, `coordinated_multi_wallet`

## Inputs

- Incident classifier output with `primary_bucket: B` or market-related `secondary_bucket`
- Market data: open interest, executable depth at 1% and 2%, mark price, oracle price, external anchor price
- Position data: top positions by notional, position concentration across wallets
- HLP data: total inventory, inventory delta, unwind velocity, unrealized PnL
- Order book data: large orders, cancel rates, spoofing signals
- Optional: attack movie if available

## Qualify before proceeding

Illiquidity alone is not manipulation. Require at least one of the following to escalate beyond informational:
- Coordinated positioning across linked wallets before the price move
- Mark price divergence from external anchor exceeding 150 bps
- Spoofing signal (large order placed and cancelled within 120 seconds around a price displacement)
- Position sizing that exceeds executable depth at the time of entry

If none of these are present, the situation may be normal thin-market volatility. State that assessment and stop.

## Procedure

### Check 1: OI vs executable depth

Compare open interest to executable depth at 1% of mid price.

**Metric:** `market.open_interest_usd / market.executable_depth_usd_1pct`

**Qualify:** Ratio above 8.0 is concerning. Above 15.0 is dangerous. Below 8.0 in isolation is not a finding — thin markets exist legitimately for low-cap assets.

### Check 2: Largest position vs depth

Compare the largest single position (or cluster of linked positions) to executable depth.

**Metric:** `max(market.top_positions.notional_usd) / market.executable_depth_usd_1pct`

**Qualify:** Ratio above 2.5 means one participant can move the market unilaterally. Below 2.5, large positions exist but may be manageable.

### Check 3: Concentration across linked wallets

Check whether multiple wallets funded from the same source hold positions in the same direction on the same asset.

**Metric:** `cluster.wallet_count`, `cluster.same_direction_ratio`, `cluster.combined_notional_usd`

**Qualify:** Coordination requires at least 3 wallets, >70% same-direction positioning, and combined notional above $5M. Wallets with independent funding histories are not coordinated by default.

### Check 4: Venue divergence vs external anchor

Compare the Hyperliquid mark price to external reference prices (CEX spot, other perp venues).

**Metric:** `bps(market.mark_price, market.external_anchor_price)`

**Qualify:** Divergence above 150 bps is notable. Above 300 bps during active trading suggests the venue price is detached from broader market consensus. Divergence during low-volume hours may be benign.

### Check 5: Spoofing behavior

Check for large orders placed and cancelled quickly around price displacements.

**Metric:** `order.large_order_notional_usd`, `order.cancel_time_seconds`, `market.price_change_bps_2m`

**Qualify:** Require notional above $10M, cancel within 120 seconds, and price change above 300 bps in the surrounding 2-minute window. Large orders that execute are not spoofs.

### Check 6: HLP inventory inheritance

Check whether HLP absorbed toxic inventory through liquidation processing.

**Metric:** `hlp.inventory_delta_usd_5m / market.executable_depth_usd_1pct`, `hlp.total_inventory_usd / market.executable_depth_usd_2pct`

**Qualify:** Inventory growth ratio above 1.0 over 5 minutes means HLP absorbed more than the market can unwind in one pass. Combined with unrealized PnL deterioration exceeding $1M over 15 minutes, this is a toxic transfer event.

### Check 7: Forced unwind vs plausible liquidity

Estimate the slippage cost of unwinding the inherited or forced-close position through available depth.

**Metric:** Walk the order book levels and compute cumulative fill cost for the position size.

**Qualify:** If the estimated unwind cost exceeds 5% of the position notional, the unwind path is impaired. This is a stress estimate, not a prediction — real unwind costs depend on liquidity response.

## Output format

```yaml
checks:
  - check_name: <name>
    result: <pass | concern | alert>
    evidence: <specific data cited>
    confidence: <high | medium | low>
    qualify_note: <why this result, what would change the assessment>

summary:
  manipulation_likelihood: <none | low | medium | high>
  toxic_transfer_risk: <none | low | medium | high>
  hlp_loss_estimate_usd: <number or range>
  candidate_circuit_breakers:
    - <description>
```

## Worked example references

- **JELLY** — Checks 1, 2, 3, 6, 7 all triggered. OI/depth ratio ~15x. Largest position exceeded depth by ~5x. Coordinated wallets identified. HLP inherited $10M+ in toxic inventory. Unwind cost estimated at >10% of position.
- **POPCAT** — Checks 1, 3, 5 triggered. Spoofing signal: large wall placed at $1.2M, cancelled in 45 seconds, coincided with 400 bps move. OI/depth imbalance present but less extreme than JELLY.

## Relationship to other skills

- **Upstream:** `incident-classifier` with Bucket B classification, or `attack-movie-builder` output.
- **Downstream:** Findings feed into `risk-engine-stress-tester` for deeper margin and liquidation analysis. Primitives feed into `primitive-extractor` if the movie path was skipped.
- **Related:** `governance-override-analyzer` — extreme manipulation cases often trigger governance intervention.

## Anti-patterns

- Do not call thin-market volatility "manipulation" without evidence of coordination or spoofing. Markets can move legitimately on low liquidity.
- Do not assume mark price execution for unwind estimates. Use actual order book depth, not theoretical mid-price fills.
- Model unwind time, not just unwind size. A $10M position in a market with $1M/hour of executable depth takes 10+ hours to unwind, during which conditions change.
- Do not anchor on a single check. Manipulation assessment requires multiple checks corroborating.

## Limitations

- Order book data is a snapshot. Historical depth reconstruction depends on data availability.
- Wallet linkage analysis is heuristic. Wallets funded from the same source may be independent actors using the same exchange.
- HLP loss estimates assume current depth and do not account for liquidity response (other traders providing or withdrawing liquidity during the unwind).
- This skill analyzes historical or current conditions. For forward-looking stress analysis, use `risk-engine-stress-tester`.
