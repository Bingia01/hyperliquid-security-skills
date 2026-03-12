# Skill — Attack Movie Builder

## Purpose

Turn a classified incident into a step-by-step causal chain. Every step must cause the next. The output is a precise reconstruction — not a summary, not a narrative, but a chain of causation with evidence citations.

## Reference documents

- `docs/research/ATTACK_PRIMITIVES.md` — 16 named primitives to reference when labeling steps
- `docs/analysis/INVARIANTS_AND_BREAKERS.md` — 7 invariants to check which ones break at each step

## Inputs

- Incident classifier output (`primary_bucket`, `attack_type`, `confidence`, `evidence_summary`)
- Raw evidence: postmortem text, wallet traces, order-book data, contract source, trade logs
- Optional: prior attack movies from similar incidents for structural reference

## Qualify before proceeding

- Do not build a movie from a single social post. Require at least one Tier 1 or Tier 2 source, or multiple Tier 3 sources that corroborate.
- If classifier confidence is `low`, state that the movie is provisional and flag which steps are inferred vs observed.
- If key evidence is missing for a step, write `UNKNOWN` for that step rather than guessing.

## Procedure

Build the movie using the 8-step template below. For each step, state what happened, cite the evidence, and explain the causal link to the next step.

### Step 1: Initial conditions

Describe the market state, position sizes, liquidity depth, and system configuration before the incident. Include relevant numbers (OI, depth, mark price, HLP inventory).

**Qualify:** Label each data point as observed (from evidence) or estimated (from inference). Do not present estimates as facts.

### Step 2: Attacker setup

Describe what the attacker did before the trigger — position building, wallet funding, multi-wallet coordination, contract deployment, or social engineering.

**Qualify:** If the setup phase is not visible in evidence (e.g., no wallet funding trace), write `UNKNOWN — setup not observable in available evidence`.

### Step 3: Trigger action

Identify the specific action that set the attack in motion — the trade, the withdrawal, the contract call, the bridge transaction.

**Qualify:** The trigger must be a single identifiable action or tight sequence. If you cannot identify it, the movie is incomplete — state that.

### Step 4: Protocol reaction

Describe how the protocol responded to the trigger — mark price movement, liquidation engine activation, HLP inventory absorption, margin recalculation.

**Qualify:** Distinguish between protocol-as-designed behavior and protocol bugs. Most incidents involve the protocol working as designed under adversarial conditions.

### Step 5: Amplification loop

Describe any feedback loop that made the situation worse — cascading liquidations, mark price deviation amplifying position losses, HLP inventory growing faster than unwind capacity.

**Qualify:** Not every incident has an amplification loop. If there is none, state `No amplification loop identified` rather than inventing one.

### Step 6: Loss realization

Quantify the loss — who lost what, how much, and through what mechanism (HLP loss absorption, user liquidation, contract drain, bridged-out funds).

**Qualify:** Distinguish between realized loss (confirmed) and estimated loss (modeled). State the source of loss figures.

### Step 7: Defender response

Describe what the protocol team, validators, or community did in response — emergency delisting, manual settlement, contract pause, social coordination.

**Qualify:** If no defender response occurred or is documented, state that. Do not infer a response from absence of evidence.

### Step 8: Breakpoints

Identify where the chain could have been broken — at which step could a control, circuit breaker, or design change have prevented or limited the loss?

**Qualify:** Breakpoints are counterfactual. Label them clearly as "could have" not "should have." Each breakpoint must reference a specific step number.

## Output format

For each step:

```yaml
steps:
  - step_number: <1-8>
    step_name: <initial_conditions | attacker_setup | trigger_action | protocol_reaction | amplification_loop | loss_realization | defender_response | breakpoints>
    description: <what happened>
    evidence_source: <specific source cited — document, tx hash, data point>
    observation_type: <observed | inferred | unknown>
    causal_link_to_next: <why this step caused the next step>
    confidence: <high | medium | low>
```

## Worked example references

- **JELLY** — All 8 steps populated. Initial conditions: $15M OI on a market with ~$1M executable depth. Trigger: large short position opened across coordinated wallets. Amplification: mark price distortion → liquidation → HLP toxic inheritance → further mark deviation. Breakpoints: OI/depth ratio circuit breaker (step 1), position concentration limit (step 2), HLP inheritance cap (step 4).
- **ETH margin drain** — 6-step movie (no amplification loop, no significant defender response). Trigger: strategic collateral withdrawal pushing position toward liquidation at favorable economics. Breakpoint: collateral withdrawal rate limit (step 3).

## Relationship to other skills

- **Upstream:** `incident-classifier` provides the bucket, attack type, and initial evidence.
- **Downstream:** `primitive-extractor` reads this movie to identify reusable attack building blocks.

## Anti-patterns

- Do not summarize. Every step must contain specific, citable detail — not "the attacker manipulated the market."
- Do not fill gaps with speculation. Write `UNKNOWN` and move on.
- Label every claim as `observed` or `inferred`. If you cannot tell, it is `inferred`.
- Do not skip steps. If a step does not apply (e.g., no amplification loop), state that explicitly.
- Do not editorialize. The movie describes what happened, not what should have happened. Save that for breakpoints.

## Limitations

- The movie is only as good as the evidence. Missing wallet traces, incomplete order-book data, or absent postmortems produce incomplete movies.
- Causal links between steps may be probabilistic rather than certain, especially for amplification loops.
- This skill reconstructs — it does not predict. Use `risk-engine-stress-tester` for forward-looking analysis.
