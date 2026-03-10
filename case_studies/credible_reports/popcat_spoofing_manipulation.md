# POPCAT spoofing and manipulation

```yaml
incident_name: POPCAT spoofing and liquidity manipulation against HLP
date: 2025-11-12
category: spoofing / manipulation / toxic_transfer
confidence: medium
affected_surface: thin market order book, HLP, liquidation path
loss_estimate: ~$4.9M to ~$5.0M reported
status: credible_report
sources:
  - Halborn 2025 analysis
  - secondary public reporting
notes:
  Keep in credible reports until stronger primary material is added.
```

## Research summary
Public writeups describe capital sharded across many wallets, leveraged longs, an apparent fake buy wall, cancellation, then a crash that left HLP absorbing losses.

## Extracted primitives
- coordinated multi-wallet positioning
- spoof-wall support
- thin-book reversals
- toxic transfer into shared liquidity

## Broken invariants
- fair-price integrity
- liquidation absorbability

## Heuristics this case informs
- coordinated_multi_wallet_positioning
- spoofing_wall_reversal
- thin_market_squeeze_risk
