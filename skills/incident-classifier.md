# Skill — Incident Classifier

## Purpose

Classify a Hyperliquid-related event into the correct attack bucket, attack type, and confidence level. This is the entry point for the incident research pipeline — every downstream skill depends on getting the classification right.

## Reference documents

- `docs/architecture/hyperliquid_attack_taxonomy.md` — five system surfaces and their mechanisms
- `docs/research/SOURCE_HIERARCHY.md` — evidence tier definitions (Tier 1–4)
- `docs/analysis/INVARIANTS_AND_BREAKERS.md` — seven system invariants

## Inputs

Require at least one of:
- Incident text (postmortem, announcement, blog post)
- Postmortem excerpts or team statements
- Wallet flow traces or bridge activity
- Code snippet or contract source
- Order-book or trade traces

More input types increase confidence. A single social post (Tier 4) alone caps confidence at `low`.

## Qualify before proceeding

- Do not classify until you have read and cited at least one piece of evidence.
- If the only source is a social media post (Tier 4), state that explicitly and cap confidence at `low`.
- If the incident description is ambiguous, list competing interpretations rather than picking one.

## Procedure

### 1. Identify the loss mechanism

Walk through the four-bucket decision tree in order. Stop at the first match, but note secondary buckets.

1. Is the loss caused by code execution in a HyperEVM or ecosystem contract? → **Bucket D** (Ecosystem Apps)
2. Is the loss caused by stolen signing authority or account compromise? → **Bucket C** (User Accounts)
3. Is the issue driven by pricing, liquidation, or market-structure abuse? → **Bucket B** (Market Structure / Core Protocol)
4. Is the issue a core infrastructure, matching, bridge, validator, or protocol logic issue? → **Bucket A** (Infrastructure / Crisis Path)

**Qualify:** If none of the four buckets match clearly, classify as `unresolved` and list what additional evidence would disambiguate.

### 2. Assign attack type

Map the loss mechanism to a specific attack type from the taxonomy (e.g., Thin Market Manipulation, Toxic Position Transfer, Arbitrary Router Calls, Private Key Compromise). Use the taxonomy's exact names.

**Qualify:** If the mechanism spans two attack types, list both and state which has stronger evidence support.

### 3. Assess confidence

Assign confidence based on evidence tier and completeness:
- `high` — Tier 1 or Tier 2 source confirms the mechanism; multiple evidence types corroborate
- `medium` — Tier 2 source with partial corroboration, or Tier 1 source with limited detail
- `low` — Tier 3/4 source only, or single evidence type with gaps

**Qualify:** Do not assign `high` confidence without at least one Tier 1 or Tier 2 source. State the tier of every source used.

### 4. Identify evidence gaps and recommend next skill

List what is missing (e.g., "no wallet trace available," "no order-book data for the timeframe"). Recommend the next pipeline skill based on the primary bucket:
- Bucket B → `market-manipulation-analyzer` or `risk-engine-stress-tester`
- Bucket C → `user-compromise-analyzer`
- Bucket D → `ecosystem-exploit-analyzer`
- Bucket A → `governance-override-analyzer`
- All buckets → `attack-movie-builder` (default next step)

## Output format

```yaml
primary_bucket: <A | B | C | D>
secondary_bucket: <A | B | C | D | none>
attack_type: <taxonomy attack type name>
confidence: <high | medium | low>
evidence_summary: <2-3 sentence description of what happened and why this bucket>
evidence_sources:
  - source: <description>
    tier: <1 | 2 | 3 | 4>
evidence_gaps:
  - <what is missing>
recommended_next_skill: <skill name>
```

## Worked example references

- **JELLY** — Primary: Bucket B (thin-market mark distortion → toxic position inheritance). Secondary: Bucket A (governance override response). Confidence: high (Tier 1 postmortem + onchain data). Next: `attack-movie-builder`.
- **Hyperdrive** — Primary: Bucket D (arbitrary router call + overbroad operator). Confidence: high (Tier 1 contract source). Next: `attack-movie-builder`.

## Relationship to other skills

- **Upstream:** None. This is the pipeline entry point.
- **Downstream:** `attack-movie-builder` consumes this output as its starting point. Domain analyzers use the primary bucket to decide which skill applies.

## Anti-patterns

- Do not anchor on headlines. A tweet saying "Hyperliquid hacked" does not mean the core protocol had a code bug.
- Do not assign `high` confidence without a Tier 1 or Tier 2 source.
- Do not force a single bucket when the evidence genuinely points to two. Use the secondary bucket field.
- Do not confuse "loss happened on Hyperliquid" with "Hyperliquid core protocol failed." That distinction is the foundation of the taxonomy.

## Limitations

- Classification depends entirely on available evidence. Incomplete evidence produces incomplete classification.
- This skill does not investigate — it classifies. Deep investigation happens in downstream skills.
- Novel attack types not in the taxonomy will be classified as the closest match with a note that the type may need to be added.
