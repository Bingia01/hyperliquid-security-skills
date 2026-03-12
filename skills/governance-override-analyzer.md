# Skill — Governance Override Analyzer

## Purpose

Analyze whether a system's expected crisis response creates gameable incentives for attackers. This skill evaluates the likelihood, predictability, and downstream effects of manual intervention — emergency delisting, manual settlement, manual repricing, ad hoc exceptions, and validator coordination under stress.

## Reference documents

- `docs/architecture/hyperliquid_attack_taxonomy.md` — Infrastructure and Crisis Path surface (Emergency Intervention)
- `docs/research/ATTACK_PRIMITIVES.md` — governance primitives (`crisis_path_governance_override`, `validator_put_dynamics`)
- `docs/analysis/INVARIANTS_AND_BREAKERS.md` — Invariant 4 (Crisis-path consistency)
- Related heuristic ID: `crisis_centralization_trigger`

## Inputs

- Market stress data: HLP unrealized PnL, halt state, delisting risk flags
- System config: circuit breaker presence, manual override capability
- Incident context: what triggered the stress, how severe is the current situation
- Historical precedent: prior override events, validator coordination patterns
- Optional: `risk-engine-stress-tester` output for loss magnitude context

## Qualify before proceeding

Override capability existing is not a finding. Every system has emergency procedures. The question is whether the override path is **predictable enough to be gamed** by an attacker who can set up positions in advance.

Do not proceed with a finding unless you can articulate the specific incentive the override creates for an attacker.

## Procedure

### Step 1: Assess override likelihood

Determine how likely manual intervention is given current conditions.

**Inputs:** `hlp.unrealized_pnl_delta_usd_15m`, `market.halt_state`, `market.delisting_risk_flags`, `system.circuit_breakers_present`

**Assessment:** Override becomes likely when:
- HLP PnL deterioration exceeds $3M in 15 minutes AND
- Manual override capability exists AND
- At least 2 delisting risk flags are active OR no automated circuit breakers exist

**Qualify:** High HLP losses alone do not trigger override. The system must also lack automated protection mechanisms that would handle the situation without human intervention.

### Step 2: Assess override predictability

Determine whether an attacker could predict the override in advance.

**Questions:**
- Has the system overridden in similar conditions before? (check historical precedent)
- Are the override conditions publicly known or inferable from documentation?
- Is there a consistent threshold (loss amount, market condition) at which overrides happen?

**Qualify:** One override event is a data point. Two overrides under similar conditions is a pattern. Three or more creates a reliable prediction. Do not claim predictability from a single precedent.

### Step 3: Assess incentive creation

Determine what economic incentive the override creates.

**Questions:**
- Can an attacker position before the override and profit from the override action? (e.g., short a token, then trigger conditions that lead to delisting, which settles at a favorable price)
- Does the override settle positions at a price different from what the market would have reached naturally?
- Can the override be triggered by a single actor creating the stress conditions?

**Qualify:** Incentive creation requires the attacker to be able to both trigger the conditions AND position to profit. If either is missing, the incentive is incomplete.

### Step 4: Assess precedent impact

Determine whether this override (if it occurs) sets a precedent that changes future behavior.

**Questions:**
- Does this override establish a pattern that future attackers can exploit?
- Does it create a "validator put" — an expectation that the protocol will intervene to limit losses?
- Does the precedent change how market participants assess risk on this platform?

**Qualify:** Do not claim `validator_put_dynamics` without repeated evidence. A single intervention may be a one-off judgment call. The "put" emerges when participants begin to price in rescue behavior.

### Step 5: Assess downstream moral hazard

Determine whether the override creates moral hazard — does it reduce the perceived cost of risk-taking?

**Questions:**
- After the override, will traders take larger positions in thin markets because they expect intervention?
- Does the override signal that losses above a certain threshold will be socialized?
- Are there second-order effects on HLP depositors, market makers, or protocol credibility?

**Qualify:** Moral hazard is a tendency, not a certainty. Frame it as "this creates conditions favorable to" rather than "this will cause."

## Output format

```yaml
governance_assessment:
  override_likelihood: <none | low | medium | high>
  predictability: <unpredictable | partially_predictable | predictable>
  incentive_risk: <none | low | medium | high>
  precedent_impact: <none | low | medium | high>
  downstream_moral_hazard: <none | low | medium | high>
  analysis:
    - step: <step name>
      finding: <description>
      evidence: <cited data>
      confidence: <high | medium | low>
  recommendations:
    - <concrete recommendation>
```

## Worked example reference

- **JELLY governance response** — Steps 1, 2, 3 all triggered. Step 1: HLP PnL deterioration exceeded threshold, validators coordinated emergency delisting. Step 2: Partially predictable — first major override, but conditions (extreme HLP loss on thin market) were observable. Step 3: Attacker could theoretically profit by shorting JELLY spot elsewhere before triggering conditions that lead to delisting settlement. Precedent impact: medium — establishes that extreme HLP stress leads to intervention.

## Relationship to other skills

- **Upstream:** `incident-classifier` provides context. `risk-engine-stress-tester` quantifies loss magnitude. `market-manipulation-analyzer` identifies the conditions leading to stress.
- **Downstream:** Findings inform `heuristic-generator` — the `crisis_centralization_trigger` heuristic detects conditions that make override likely.
- **Related:** `market-manipulation-analyzer` — extreme manipulation cases are the most common trigger for governance intervention.

## Anti-patterns

- Not all intervention is bad. Emergency circuit breakers and orderly wind-downs are good practice. The concern is with unpredictable, ad hoc overrides that change the economic outcome.
- Do not claim validator put without repeated evidence. A single intervention is a judgment call, not a systemic commitment.
- Do not assume malicious intent behind governance decisions. The question is whether the decision creates exploitable incentives, regardless of intent.
- Do not confuse "the protocol has override capability" with "the protocol will override." Capability is not action.

## Limitations

- Governance analysis is inherently qualitative. Override likelihood and predictability assessments involve judgment, not mechanical thresholds.
- Historical precedent on Hyperliquid is limited. As more override events occur (or do not occur), assessments will become more reliable.
- This skill cannot observe validator communication or decision-making processes directly. Assessments are based on observable outcomes and public information.
- Moral hazard effects are second-order and unfold over time. They cannot be confirmed or denied in a single analysis.
