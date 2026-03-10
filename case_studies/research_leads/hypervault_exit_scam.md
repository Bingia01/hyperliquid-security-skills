# HyperVault suspected exit scam

```yaml
incident_name: HyperVault suspected exit scam
date: 2025-09
category: rug_pull / ecosystem_trust_failure
confidence: research_lead
affected_surface: ecosystem app / governance / custody behavior
loss_estimate: ~$3.6M reported
status: research_lead
sources:
  - public secondary reports
notes:
  Important for ecosystem risk accounting, but should not influence core protocol heuristics.
```

## Research lead summary
This looks like a custody or governance-trust failure rather than a Hyperliquid core exploit. Keep it documented, but isolate it from protocol-design heuristics.

## Candidate primitives
- custodial trust failure
- abnormal outflow before shutdown
- social-channel disappearance
- laundering after exit

## Candidate broken invariants
- ecosystem trust-boundary separation
