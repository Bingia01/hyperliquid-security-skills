# Large wallet private-key compromise

```yaml
incident_name: Large Hyperliquid wallet private-key compromise
date: 2025-10-10
category: account_takeover / key_compromise
confidence: medium
affected_surface: user account security / bridge-out behavior
loss_estimate: ~$20.6M to ~$21.0M reported
status: credible_report
sources:
  - Yahoo Finance 2025-10-10
  - Hyperliquid support docs on compromised accounts
notes:
  Model as user-compromise risk, not as a confirmed core-protocol bug.
```

## Research summary
Available reports describe a large wallet drain after private-key leakage. The relevant detection surface is behavioral: sudden sweeping, unusual bridge destinations, and rapid dispersal.

## Extracted primitives
- stolen signing authority
- wallet behavioral break
- rapid multi-asset sweep
- bridge-out anomaly

## Broken invariants
- user-signing control

## Heuristics this case informs
- account_behavioral_break
- bridge_out_after_compromise
