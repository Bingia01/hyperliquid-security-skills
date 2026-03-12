# Skill — Heuristic Generator

## Purpose

Turn extracted primitives into detection heuristics — human-readable rules, machine-usable logic, and simulation recipes. Each heuristic must be testable, have documented false positives, and follow the namespace convention from `rules/heuristics.v1.yaml`.

## Reference documents

- `docs/research/HEURISTIC_LIBRARY.md` — existing heuristics with evidence tiers and anchor cases
- `rules/heuristics.v1.yaml` — 10 machine-readable rules with input namespaces and threshold logic
- `templates/heuristic_template.md` — required fields for each heuristic entry

## Inputs

- Primitive extractor output (`primitive_name`, `group`, `invariant_threatened`, `is_new_or_existing`, `confidence`)
- Incident classifier output (`primary_bucket`, `attack_type`) for context
- Optional: attack movie for threshold calibration from real incident data

## Qualify before proceeding

- Do not generate heuristics from primitives with `confidence: low` unless explicitly asked. Low-confidence primitives produce theoretical heuristics only.
- If the primitive is marked `is_new_or_existing: new`, the heuristic status must be `theoretical` until the primitive is confirmed by human review.
- Check the existing library first. Do not duplicate an existing heuristic.

## Procedure

### 1. Check existing library

Search `docs/research/HEURISTIC_LIBRARY.md` and `rules/heuristics.v1.yaml` for heuristics that already cover this primitive. The 10 existing heuristic IDs are:
- `thin_market_squeeze_risk`
- `toxic_inventory_transfer`
- `settlement_cliff`
- `crisis_centralization_trigger`
- `strategic_margin_drain`
- `coordinated_multi_wallet`
- `spoofing_wall_reversal`
- `account_behavioral_break`
- `arbitrary_call_surface`
- `operator_permission_scope_creep`

**Qualify:** If an existing heuristic covers the primitive, do not create a new one. Instead, note whether the existing heuristic's thresholds or logic need updating based on the new incident data. Output the update recommendation.

### 2. Draft new heuristic using template

If no existing heuristic covers the primitive, draft a new one following the template fields:
- **name** — `snake_case`, descriptive, matches the detection behavior (not the primitive name)
- **status** — `observed` (backed by confirmed incident), `adjacent` (backed by credible report), or `theoretical` (inferred or research-lead only)
- **detects** — one sentence describing what condition triggers
- **why it matters** — one sentence connecting to the invariant threatened
- **signals / evidence** — list the observable indicators
- **false positives / limitations** — at least 2 documented false positive scenarios
- **primitive links** — which primitives this heuristic detects
- **invariant links** — which invariants this heuristic protects

### 3. Specify inputs using namespace convention

All inputs must follow the namespace convention used in `heuristics.v1.yaml`. The 9 namespaces are:
- `market.*` — market-level data (prices, depth, OI, settlement)
- `hlp.*` — HLP vault inventory and PnL
- `account.*` — per-account position, collateral, behavior
- `cluster.*` — multi-wallet coordination signals
- `order.*` — individual order-level signals
- `contract.*` — smart contract static analysis flags
- `permission.*` — role and permission model flags
- `system.*` — system-wide config and state
- `governance.*` — governance and override capability

**Qualify:** Every input must use an existing namespace. If a new input is needed, propose it with a clear definition and source type (`api_direct`, `derived`, `static_analysis`, or `hypothetical`).

### 4. Write logic using all_of / any_of structure

Define the detection logic using the same structure as `heuristics.v1.yaml`:
- `all_of` — conditions that must all be true (conjunction, meaning every condition in this list must hold simultaneously)
- `any_of` — conditions where at least one must be true (disjunction, meaning the rule fires if any single condition in this list holds)

Each condition is a comparison expression using namespace inputs and threshold values.

**Qualify:** Thresholds are starter defaults for research and simulation, not production guarantees. State the basis for each threshold (incident data, estimation, or placeholder).

### 5. List false positives

Document at least 2 scenarios where the heuristic would fire but the situation is benign:
- What market condition triggers a false positive?
- Why is it benign?
- What follow-up check would distinguish it from a real alert?

**Qualify:** Never skip false positives. A heuristic without documented false positives is not ready for use.

### 6. Suggest follow-up tests

For each heuristic, suggest 2–3 follow-up validation steps:
- A data check that would confirm or reject the alert
- A simulation scenario that would test the threshold
- A related heuristic that should also be evaluated

## Output format

```yaml
heuristic:
  id: <snake_case_name>
  family: <heuristic family>
  status: <observed | adjacent | theoretical>
  severity: <critical | high | medium | low>
  applies_to: [<applicable surfaces>]
  description: <one sentence>
  required_inputs:
    - <namespace.input_name>
  thresholds:
    <threshold_name>: <value>
  logic:
    all_of:
      - "<condition>"
    any_of:
      - "<condition>"
  false_positives:
    - scenario: <description>
      distinguisher: <how to tell it apart from real alert>
  follow_up_tests:
    - <description>
  primitive_links:
    - <primitive_name>
  invariant_links:
    - <invariant_name>
  outputs:
    alert_key: <same as id>
    include:
      - <output field>
```

## Worked example reference

- **JELLY's `thin_market_mark_distortion`** → maps to existing `thin_market_squeeze_risk` heuristic. No new heuristic needed. Update recommendation: consider lowering `oi_to_depth_1pct` threshold from 8.0 to 6.0 based on JELLY's actual OI/depth ratio at incident time.

## Relationship to other skills

- **Upstream:** `primitive-extractor` provides the primitives to convert into heuristics.
- **Downstream:** New heuristics are added to `docs/research/HEURISTIC_LIBRARY.md` and `rules/heuristics.v1.yaml`. Threshold profiles in `rules/threshold_profiles/` may need updates.

## Anti-patterns

- Do not over-fit to one incident. A heuristic derived from JELLY must also make sense for a hypothetical similar attack on a different asset.
- Never skip false positives. Every heuristic fires on benign conditions sometimes — document when.
- Research-lead evidence (Tier 3/4) produces `theoretical` status only. Do not mark a heuristic as `observed` without confirmed-tier backing.
- Do not duplicate existing heuristics. Check the library first.
- Do not invent inputs outside the 9 namespaces without proposing them explicitly.

## Limitations

- Thresholds are calibrated from a small number of incidents. They will need adjustment as more data accumulates.
- Heuristics detect conditions, not intent. A triggered heuristic means the condition exists, not that an attack is underway.
- Machine-readable logic in `all_of` / `any_of` format cannot express all detection patterns (e.g., temporal sequences, cross-market correlations). Complex patterns may need custom implementation beyond the YAML rule format.
