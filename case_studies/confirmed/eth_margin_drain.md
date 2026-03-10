# ETH whale strategic liquidation / margin drain

```yaml
incident_name: ETH whale strategic liquidation / margin drain
date: 2025-03-12
category: strategic_liquidation / toxic_position_transfer
confidence: high
affected_surface: liquidation engine, HLP, margin rules
loss_estimate: ~$4M HLP loss; attacker profit reported around ~$1.8M
status: confirmed
sources:
  - CoinDesk 2025-03-12
  - Arkham 2025-03-12
  - Hyperliquid public statement
notes:
  Important because Hyperliquid publicly framed it as not a core code exploit.
```

## Attack movie
1. Open an outsized leveraged ETH long.
2. Accumulate unrealized profit.
3. Withdraw collateral instead of exiting normally in the market.
4. Move the liquidation threshold toward current price.
5. Allow liquidation and force HLP to handle the exit.
6. Realize better economics than a clean market exit while HLP absorbs the unwind loss.

## Extracted primitives
- strategic margin withdrawal
- liquidation threshold steering
- protocol-absorbed toxic position
- unwind exceeds safe depth

## Broken invariants
- margin integrity
- liquidation absorbability

## Heuristics this case anchors
- strategic_margin_drain
- protocol_absorbed_toxic_position
- unwind_depth_mismatch
