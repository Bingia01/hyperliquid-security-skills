# CLAUDE.md

When using this repository, follow the pipeline:

1. classify the incident by surface and evidence tier,
2. reconstruct an attack movie,
3. extract primitives,
4. map broken invariants,
5. draft heuristics,
6. map heuristics to machine-readable rules,
7. choose the correct threshold profile.

## Important rules
- Do not treat every loss on Hyperliquid as a core protocol bug.
- Do not let `research_lead` incidents anchor strong rules.
- Always map incidents to one of four buckets: core protocol, market abuse, user compromise, ecosystem app risk.
- Use the architecture taxonomy in `docs/architecture/hyperliquid_attack_taxonomy.md` as the starting mental model. For HyperEVM and ecosystem-app analysis, also refer to `docs/architecture/hyperevm_vulnerability_taxonomy.md`.
