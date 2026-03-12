# Skill — Risk Engine Stress Tester

## Purpose

Stress-test the risk engine's ability to handle forced unwinds, collateral withdrawals, liquidation cascades, and cross-asset drawdowns. This skill models forward-looking failure paths — it answers "what could happen" rather than "what did happen."

## Reference documents

- `docs/architecture/hyperliquid_attack_taxonomy.md` — Core Protocol surface (Risk Engine, Liquidation System, Portfolio Margin, HLP Backstop)
- `docs/research/ATTACK_PRIMITIVES.md` — risk-engine primitives (`toxic_position_inheritance`, `liquidation_depth_mismatch`, `strategic_margin_withdrawal`, `portfolio_offset_blind_spot`)
- `docs/analysis/INVARIANTS_AND_BREAKERS.md` — Invariant 1 (Liquidation absorbability), Invariant 3 (Margin integrity)
- Related heuristic IDs: `toxic_inventory_transfer`, `strategic_margin_drain`

## Inputs

- Market depth data: executable depth at 1% and 2% of mid, order book snapshot
- Position data: top positions by notional, margin ratios, liquidation prices
- HLP data: total inventory, unrealized PnL, unwind velocity
- Margin config: maintenance margin requirements, portfolio margin offsets, cross-collateral rules
- Optional: incident classifier or market-manipulation-analyzer output for context

## Qualify before proceeding

A failed stress test means a failure **path exists**, not that it was **exploited**. Frame all results as conditional: "If X happens, the system would face Y." Do not present stress test failures as confirmed vulnerabilities.

## Procedure

### Test 1: Forced unwind through top-N book levels

Simulate liquidating the largest position by walking through the top N order book levels.

**Scenario:** The largest position must be fully liquidated at current book depth.

**Failure criteria:** Estimated slippage exceeds 5% of position notional, or the position cannot be fully closed within available depth.

**Qualify:** This is a worst-case snapshot. Real liquidation may encounter liquidity response (new orders appearing). State that caveat.

### Test 2: Collateral withdrawal before liquidation

Simulate a trader withdrawing collateral to push a large position toward the liquidation threshold.

**Scenario:** Trader holds position at `account.position_notional_usd` and withdraws collateral until maintenance margin is breached.

**Failure criteria:** The withdrawal path from current margin to liquidation threshold requires less than $1M in withdrawals, and the resulting forced-close position exceeds executable depth.

**Qualify:** This tests the `strategic_margin_withdrawal` primitive. It is a design risk, not necessarily a bug — the question is whether the system allows value extraction through this path.

### Test 3: Liquidation under reduced depth

Simulate a liquidation event when book depth is reduced to 50% and 25% of current levels.

**Scenario:** Depth drops (e.g., market makers pull quotes during volatility) and a liquidation triggers at reduced depth.

**Failure criteria:** At 50% depth, the liquidation creates more than 3% price impact. At 25% depth, the liquidation cannot be absorbed without cascading into additional liquidations.

**Qualify:** Depth reduction is normal during stress. The question is how gracefully the system degrades.

### Test 4: Cross-asset collateral drawdown

Simulate a scenario where collateral assets lose value simultaneously with the position asset moving against the trader.

**Scenario:** Collateral asset drops 20% while the position moves 10% against the trader.

**Failure criteria:** The combined drawdown pushes the account below maintenance margin, and the resulting liquidation cascade affects multiple markets.

**Qualify:** This tests the `portfolio_offset_blind_spot` primitive. Cross-asset correlation during stress is higher than during normal conditions.

### Test 5: Borrow / collateral interaction

If applicable, simulate the interaction between borrowing and collateral requirements.

**Scenario:** A trader uses borrowed funds as margin for a leveraged position, and the borrow rate spikes or the borrowed asset is recalled.

**Failure criteria:** The borrow recall triggers a margin call that cascades into forced liquidation.

**Qualify:** Only applicable to accounts using borrow-based collateral. Skip if the market or account does not use this feature.

### Test 6: Portfolio maintenance requirement sensitivity

Test how small changes in maintenance margin requirements affect the number of positions at risk.

**Scenario:** Increase maintenance margin requirement by 10%, 25%, and 50% from current levels.

**Failure criteria:** A 10% increase puts more than 5% of open interest at risk of liquidation. A 25% increase triggers cascading liquidations.

**Qualify:** Margin parameter changes are governance decisions. This test informs the impact of potential parameter changes, not their likelihood.

## Output format

```yaml
stress_tests:
  - test_name: <name>
    scenario: <description>
    result: <pass | marginal | fail>
    failure_path: <description of how failure unfolds — null if pass>
    loss_estimate_usd: <number or range — null if pass>
    key_assumptions: <what the model assumes>
    mitigations:
      - <concrete control or parameter change that would address the failure>

summary:
  tests_passed: <count>
  tests_failed: <count>
  highest_severity_failure: <test name>
  aggregate_loss_estimate_usd: <number or range>
  priority_mitigations:
    - <top recommendation>
```

## Worked example reference

- **ETH margin drain** — Tests 1 and 2 both show failure paths. Test 2: a trader with $50M notional could withdraw ~$2M collateral to push maintenance margin below threshold, creating a forced-close position that exceeds available depth at 1% by 3x. Mitigation: collateral withdrawal rate limit proportional to position size.

## Relationship to other skills

- **Upstream:** `market-manipulation-analyzer` identifies current conditions; this skill models what happens under stress. `incident-classifier` provides context.
- **Downstream:** Results feed into `heuristic-generator` for threshold calibration. `governance-override-analyzer` uses stress results to assess override likelihood.
- **Related:** `market-manipulation-analyzer` looks backward at what happened; this skill looks forward at what could happen.

## Anti-patterns

- Do not assume mark price execution for liquidation modeling. Walk the actual book levels.
- Model unwind time, not just unwind size. A position that takes 10 hours to unwind at current depth faces changing conditions during that window.
- Do not present stress test failures as confirmed vulnerabilities. Frame results as conditional paths.
- Do not ignore liquidity response. State the assumption about whether new orders appear during the unwind.

## Limitations

- Stress tests use current snapshots. Market conditions change continuously.
- Liquidity response during stress is unpredictable — market makers may add or withdraw liquidity.
- Cross-asset correlations during stress are estimated, not observed. Historical correlations may understate real stress correlations.
- This skill models mechanical failure paths, not attacker intent. An exploitable failure path does not mean an attacker exists.
