# SNX oracle / pricing manipulation against HLP

```yaml
incident_name: SNX oracle / pricing manipulation against HLP
date: 2023-06
category: oracle_manipulation / pricing_anchor_abuse
confidence: research_lead
affected_surface: pricing, HLP, market abuse
loss_estimate: ~$37K often cited in public retellings
status: research_lead
sources:
  - secondary market reporting and ecosystem references
notes:
  Preserve as an early proof-of-pattern lead. Do not let it drive strong rules until primary evidence improves.
```

## Research lead summary
This entry exists because multiple public retellings cite it as an early example of external-price-anchor abuse against HLP. It belongs in the repo as a research lead, not as a confirmed anchor case.

## Candidate primitives
- cross-exchange price anchor abuse
- external reference fragility
- thin-anchor oracle distortion

## Candidate broken invariants
- fair-price integrity
