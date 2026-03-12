# Skill — HIP-3 / HIP-4 Surface Map

## Purpose

Map the attack surface specific to HIP-3 (builder-deployed perpetuals) and HIP-4 (outcome/prediction-style markets). These market types introduce builder-defined parameters, custom oracles, and unique settlement logic that create risks not present in core perpetuals.

## Reference documents

- `docs/architecture/hyperliquid_attack_taxonomy.md` — Market Structure surface, Ecosystem Apps surface
- `docs/research/ATTACK_PRIMITIVES.md` — pricing primitives (`thin_market_mark_distortion`, `cross_exchange_price_anchor_abuse`, `weak_anchor_settlement`), risk-engine primitives (`liquidation_depth_mismatch`, `portfolio_offset_blind_spot`)
- `docs/analysis/INVARIANTS_AND_BREAKERS.md` — Invariant 2 (Fair-price integrity), Invariant 3 (Margin integrity)
- `rules/threshold_profiles/hip3_markets.yaml` — HIP-3 threshold adjustments
- `rules/threshold_profiles/hip4_style_markets.yaml` — HIP-4 threshold adjustments
- Related heuristic IDs: `thin_market_squeeze_risk`, `settlement_cliff`

## Inputs

- Market configuration: market type (core perp, HIP-3, HIP-4), leverage caps, margin parameters
- Builder oracle details: oracle source, update frequency, manipulation resistance
- Settlement rules: settlement reference, settlement window, resolution authority
- Leverage parameters: max leverage, maintenance margin, liquidation penalties
- Optional: incident classifier or market-manipulation-analyzer output for context

## Qualify before proceeding

- **Core perps → this skill does not apply.** Core perpetuals use protocol-managed oracles and standard parameters. Use `market-manipulation-analyzer` and `risk-engine-stress-tester` instead.
- **HIP-4 findings → label as theoretical** unless supported by observed incidents. HIP-4 is early-stage, and findings are largely anticipatory.
- State which market type you are analyzing at the top of the output.

## HIP-3 review areas

### Area 1: Builder oracle design

Evaluate the oracle the builder selected for their perpetual market.

**Check:** What is the oracle source? How frequently does it update? Can it be manipulated by the builder or a third party?

**Qualify:** A builder oracle that sources from a single low-liquidity exchange is high risk. A builder oracle that aggregates from 5+ liquid venues with outlier filtering is low risk. State the specific source and your assessment.

### Area 2: Leverage caps

Evaluate whether the leverage parameters are appropriate for the market's liquidity.

**Check:** What is the max leverage? What is the executable depth? Could the max leverage create positions that exceed the market's ability to liquidate them?

**Qualify:** High leverage on thin markets is a risk. High leverage on deep, liquid markets may be acceptable. The test is whether a max-leverage position can be liquidated within available depth.

### Area 3: Settlement authority

Evaluate who controls settlement and under what conditions.

**Check:** Can the builder manually settle or delist the market? Are there conditions under which automatic settlement occurs? Is the settlement price derived from a manipulable source?

**Qualify:** Builder settlement authority is a design choice, not inherently a bug. The risk is if the builder can settle at a favorable price while holding a position. Check for conflicts of interest.

### Area 4: Market parameter abuse

Evaluate whether the builder can change market parameters in ways that affect existing position holders.

**Check:** Can the builder change margin requirements, leverage caps, or oracle source after positions are open? Is there a timelock or governance process?

**Qualify:** Parameter changes without timelock on a market with open positions are high risk. Parameter changes with 24h+ timelock and notification are acceptable.

### Area 5: Portfolio-margin interactions

Evaluate how HIP-3 positions interact with the user's broader portfolio margin.

**Check:** Are HIP-3 positions included in portfolio margin calculations? Can a HIP-3 position's risk offset a core perp position? Could this create a hidden concentration risk?

**Qualify:** Portfolio margin offsets that include low-liquidity HIP-3 markets may understate real risk. The `portfolio_offset_blind_spot` primitive applies here.

## HIP-4 review areas

### Area 1: Resolution source quality

Evaluate the data source used to determine the outcome of the event market.

**Check:** What is the resolution source? Is it a single source or multiple? Can it be manipulated or disputed?

**Qualify:** A single-source resolution (e.g., one API endpoint) is high risk. A multi-source resolution with dispute mechanism is lower risk. All HIP-4 resolution analysis is theoretical until observed incidents occur.

### Area 2: Settlement rule ambiguity

Evaluate whether the settlement rules have edge cases or ambiguities.

**Check:** Are the rules clear about all possible outcomes? What happens if the resolution source is unavailable? What happens in case of ties or disputed results?

**Qualify:** Ambiguous settlement rules create arbitrage opportunities for participants who understand the edge cases. Check for under-specified conditions.

### Area 3: Last-minute print domination

Evaluate whether a single trade or data point near the settlement window can determine the outcome.

**Check:** What is the settlement window? Is the settlement price a snapshot or a TWAP? Can a well-timed trade in the last minute dominate the settlement.

**Qualify:** Snapshot settlement is high risk for print domination. TWAP over 30+ minutes is lower risk. State the specific mechanism.

### Area 4: Event-source manipulation

Evaluate whether the underlying event (not the price) can be manipulated.

**Check:** For a prediction market on "will X happen by date Y," can a participant influence whether X actually happens? This is outside the market's control but creates a conflict of interest.

**Qualify:** This is theoretical for most event markets. Only flag if the event is influenceable by a market participant with sufficient resources.

### Area 5: Bounded payoff accounting

Evaluate whether the payoff structure correctly bounds losses and gains.

**Check:** Is the maximum payoff correctly implemented? Can rounding, overflow, or edge cases in the payoff calculation create unexpected results?

**Qualify:** This is a code-level check if source is available. Otherwise, evaluate based on the market specification.

### Area 6: Cross-product hedge assumptions

Evaluate whether participants might use HIP-4 positions to hedge other positions in ways the system does not account for.

**Check:** Can a HIP-4 position create a synthetic hedge that portfolio margin does not recognize? Could this lead to under-margined positions?

**Qualify:** Theoretical concern. Flag if the HIP-4 market's underlying correlates strongly with a core perp market.

## Output format

```yaml
market_type: <hip3 | hip4>

areas:
  - area: <area name>
    risk_level: <low | medium | high | critical>
    finding: <description>
    evidence_basis: <observed | adjacent | theoretical>
    recommendations:
      - <concrete recommendation>

summary:
  overall_risk: <low | medium | high>
  highest_risk_area: <area name>
  priority_recommendations:
    - <top recommendation>
```

## Worked example reference

- **JELLY as HIP-3 adjacent** — While JELLY was a core perp, the thin-market dynamics mirror risks in poorly-configured HIP-3 markets. Area 1: if a HIP-3 builder uses a single low-liquidity oracle, the same mark distortion primitive applies. Area 2: if max leverage is set too high relative to depth, the same OI/depth imbalance emerges. This case illustrates why HIP-3 parameters need review against core perp incident precedents.

## Relationship to other skills

- **Upstream:** `incident-classifier` provides market type context. `market-manipulation-analyzer` provides baseline market health data.
- **Downstream:** Findings feed into `primitive-extractor` for HIP-3/HIP-4 specific primitives. `heuristic-generator` uses results to calibrate HIP-3/HIP-4 threshold profiles.
- **Related:** `market-manipulation-analyzer` covers core perp manipulation; this skill extends that analysis to builder-deployed and outcome markets.

## Anti-patterns

- Do not apply this skill to core perps. Core perps have protocol-managed parameters and are covered by `market-manipulation-analyzer` and `risk-engine-stress-tester`.
- Do not present theoretical HIP-4 findings as confirmed. Label evidence basis clearly.
- Do not evaluate HIP-3 parameters in isolation. Always check them against the market's actual liquidity and depth.
- Do not assume builder malice. Most parameter issues are configuration errors, not intentional exploitation.

## Limitations

- HIP-3 and HIP-4 are evolving. New market types and parameter options may introduce risks not covered by this skill.
- HIP-4 analysis is largely theoretical due to limited production history. Findings should be treated as anticipatory.
- Builder oracle quality assessment depends on knowing the oracle source, which may not always be documented.
- This skill evaluates market-level risks, not contract-level code bugs. For code-level analysis of HyperEVM contracts underlying HIP-3/HIP-4 markets, use `ecosystem-exploit-analyzer` or `hyperevm-pre-ship-review`.
