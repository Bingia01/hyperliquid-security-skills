# JELLY self-liquidation attack

```yaml
incident_name: JELLY self-liquidation / short squeeze against HLP
date: 2025-03-26
category: market_manipulation / liquidation_inheritance / governance_override
confidence: high
affected_surface: thin market pricing, liquidation engine, HLP, governance response
loss_estimate: ~$12M to ~$13.5M path before intervention
status: confirmed
sources:
  - Arkham 2025-03-26
  - CoinDesk 2025-03-26
  - Hyperliquid public statement
notes:
  Use as the canonical Hyperliquid-class economic exploit case study.
```

## Attack movie
1. Initial conditions: JELLY was a weakly anchored, easy-to-move market. HLP could inherit liquidated inventory.
2. Attacker setup: multiple accounts established coordinated opposing positions.
3. Trigger action: the short leg was driven into liquidation.
4. Protocol reaction: the short was transferred to HLP for clearance.
5. Amplification loop: attackers or aligned flow bought JELLY externally, increasing HLP mark-to-market pain.
6. Loss realization: HLP unrealized losses reportedly moved into the low-teens of millions.
7. Defender response: validators delisted the market and settled it manually.
8. Break points: tighter OI caps, bounded inheritance, depth-aware circuit breakers, precommitted crisis ladders.

## Extracted primitives
- thin-market mark distortion
- coordinated multi-wallet positioning
- self-liquidation
- toxic position inheritance
- external-anchor pump
- crisis-path governance override

## Broken invariants
- fair-price integrity
- liquidation absorbability
- crisis-path consistency

## Heuristics this case anchors
- thin_market_squeeze_risk
- protocol_absorbed_toxic_position
- settlement_cliff
- crisis_centralization_trigger
