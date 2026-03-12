# Skill — Primitive Extractor

## Purpose

Convert an attack movie into reusable building blocks. Each primitive is a named, composable unit of attacker technique or system weakness that can appear across multiple incidents. Primitives feed into heuristic generation and coverage tracking.

## Reference documents

- `docs/research/ATTACK_PRIMITIVES.md` — canonical library of 16 named primitives across 5 groups
- `docs/analysis/INVARIANTS_AND_BREAKERS.md` — 7 invariants; each primitive threatens at least one

## Inputs

- Attack movie output (all 8 steps with `step_name`, `description`, `evidence_source`, `observation_type`, `causal_link_to_next`)
- Incident classifier output (`primary_bucket`, `attack_type`) for context

## Qualify before proceeding

- Do not extract primitives from movie steps marked `UNKNOWN`. Unknown steps produce no primitives.
- If the movie has fewer than 3 observed or inferred steps, the incident is too thin for reliable extraction. State that and stop.
- Every primitive must be traceable to a specific movie step. If you cannot point to the step, do not extract the primitive.

## Procedure

### 1. Walk the movie steps

Read each step of the attack movie in order. For each step, ask: does this step contain a reusable attacker technique or a system weakness that could appear in a different incident?

**Qualify:** Not every step produces a primitive. "Initial conditions" often sets context rather than containing a technique. Only extract where there is a distinct, nameable action or weakness.

### 2. Map to known primitives

Check each candidate against the 16 named primitives in `docs/research/ATTACK_PRIMITIVES.md`. Use the canonical name if it matches. The five groups are:
- Pricing and market primitives (4): `thin_market_mark_distortion`, `cross_exchange_price_anchor_abuse`, `weak_anchor_settlement`, `spoof_wall_support`
- Risk-engine primitives (4): `toxic_position_inheritance`, `liquidation_depth_mismatch`, `strategic_margin_withdrawal`, `portfolio_offset_blind_spot`
- Governance and crisis primitives (2): `crisis_path_governance_override`, `validator_put_dynamics`
- Operational primitives (2): `wallet_behavioral_break`, `bridge_out_after_compromise`
- Smart-contract / app primitives (4): `arbitrary_external_call`, `operator_permission_scope_creep`, `missing_post_call_invariant`, `ecosystem_trust_failure`

**Qualify:** If the technique does not match any existing primitive, propose a new name following the `snake_case_descriptive` convention. Flag all new primitives for human review.

### 3. Distinguish cause from consequence

For each extracted primitive, determine whether it is a **cause** (the attacker used this technique to advance the attack) or a **consequence** (this happened as a result of the attack, but was not the attacker's tool).

**Qualify:** Consequences are not primitives. "HLP lost $10M" is a consequence. "toxic_position_inheritance" (the mechanism that caused the HLP to absorb the position) is a cause. If you cannot tell, label it `ambiguous` and include your reasoning.

### 4. Check granularity

Each primitive must be reusable — it should be general enough to appear in a different incident context. If a candidate is too specific to one incident (e.g., "attacker opened JELLY short on March 26"), it is an incident detail, not a primitive.

**Qualify:** If the candidate only makes sense in the context of this specific incident, do not extract it. Describe why in a note.

### 5. Map to invariant

For each extracted primitive, identify which of the 7 invariants it threatens:
1. Liquidation absorbability
2. Fair-price integrity
3. Margin integrity
4. Crisis-path consistency
5. Permission-bounded execution
6. User-signing control
7. Ecosystem trust-boundary separation

**Qualify:** Every primitive must map to at least one invariant. If it does not, either the primitive is too vague or the invariant list needs expansion — flag for review.

## Output format

```yaml
primitives:
  - primitive_name: <canonical name from library or proposed new name>
    group: <pricing | risk_engine | governance | operational | smart_contract>
    movie_step_source: <step number and name from the attack movie>
    role: <cause | consequence | ambiguous>
    invariant_threatened: <invariant name from INVARIANTS_AND_BREAKERS.md>
    is_new_or_existing: <existing | new>
    confidence: <high | medium | low>
    notes: <optional — reasoning for ambiguous cases or new primitives>
```

Cap at 6–8 primitives per incident. If you find more, consolidate or drop the lowest-confidence entries.

## Worked example references

- **JELLY** — 5 primitives: `thin_market_mark_distortion` (step 1, cause, fair-price integrity), `toxic_position_inheritance` (step 4, cause, liquidation absorbability), `liquidation_depth_mismatch` (step 5, cause, liquidation absorbability), `crisis_path_governance_override` (step 7, cause, crisis-path consistency), `validator_put_dynamics` (step 7, consequence, crisis-path consistency).
- **Hyperdrive** — 3 primitives: `arbitrary_external_call` (step 3, cause, permission-bounded execution), `operator_permission_scope_creep` (step 2, cause, permission-bounded execution), `missing_post_call_invariant` (step 4, cause, permission-bounded execution).

## Relationship to other skills

- **Upstream:** `attack-movie-builder` provides the step-by-step causal chain.
- **Downstream:** `heuristic-generator` uses extracted primitives to draft detection rules. Domain analyzers reference primitives for deeper investigation.

## Anti-patterns

- Cause is not consequence. "The market crashed" is what happened. "thin_market_mark_distortion" is the mechanism. Extract the mechanism, not the outcome.
- Cap at 6–8 primitives per incident. Over-extraction dilutes signal. If an incident genuinely has more, the movie probably needs decomposition into sub-incidents.
- New primitives need human review. Do not add new primitives to the canonical library without confirmation — propose them in the output and flag.
- Do not extract primitives from `UNKNOWN` movie steps. No evidence means no primitive.

## Limitations

- Extraction quality depends on movie quality. A vague or incomplete movie produces vague or missing primitives.
- The canonical library (16 primitives) covers known Hyperliquid-class attacks. Novel attack vectors may require new primitives not yet in the library.
- Cause vs consequence distinction is sometimes genuinely ambiguous, especially for amplification loops where the consequence of one step is the cause of the next.
