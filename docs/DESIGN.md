# Design

This document explains why version 3 is built the way it is, starting from
what the program is for. It replaces the v1/v2 layout (prose pipeline, hand-kept
matrices, unevaluated YAML rules) with an evidence-checked knowledge base, a
typed rule engine and a read-only data adapter.

## 1. Purpose

Help a person or an agent answer three questions about the Hyperliquid
ecosystem, and show how much each answer can be trusted:

1. **What happened?** Reconstruct an incident from sources, classify whose
   control failed and how, and record what is established versus disputed.
2. **What could happen?** Measure exposures that made past incidents
   profitable (depth versus open interest, backstop inventory, deployer
   incentives) on live markets.
3. **Is this code exposed?** Review HyperEVM contracts for known failure
   classes, with HyperCore-interaction risks first.

The deliverable of each answer is a validated record or a rule outcome with
its evidence, never prose alone.

## 2. What v1/v2 did, and where it fell short

v1/v2 described a seven-stage pipeline (incident -> attack movie -> primitive
-> invariant -> heuristic -> rule -> threshold profile) as Markdown documents,
YAML records and eleven prompt specifications. Its central ideas - separate
"loss on Hyperliquid" from "Hyperliquid bug", and keep weak evidence out of
strong rules - are correct and are kept. Verified defects:

| Area | Finding |
|---|---|
| Skills | The 11 files in `skills/` had no frontmatter and were outside `.claude/skills/<name>/SKILL.md`, so Claude Code never loaded them as skills. |
| Rules | Logic hard-coded numbers that duplicated the `thresholds` block, so editing a threshold changed nothing. No rule had been evaluated by any program. |
| Profiles | Zero of the threshold profiles' keys matched any rule's threshold names; profiles could not be applied. |
| Rule logic | `arbitrary_call_surface` did not fire on a permissionless `execute(target, data)` with unrestricted targets if the contract had a post-call check (the check matched only `'broad'`, not `'unrestricted'`). `operator_permission_scope_creep` required two excess powers; one power to move user funds is total loss. `coordinated_multi_wallet` never read its defining input (common funding). `toxic_inventory_transfer` divided HLP-wide inventory by one market's depth. |
| Data dictionary | Cited a nonexistent API type (`userTransfers`, rejected by the live API), fields absent from the API (market type, settlement window, halt state), and the HLP parent vault where inventory lives in child vaults. Its depth method (sum one `l2Book` response) undercounted depth within 2% by 6x to 94x on every market sampled on 2026-10-12, because the API returns 20 levels per side. |
| Examples | The sample output reported `mark_oracle_bps: 81.63` (below the rule's 100 threshold) for an alert that fired; the correct value from the sample input is 851. Inputs mixed JELLY's real settlement price ($0.0095) with an invented mark price ($0.51), 54x apart. |
| Evidence | Sources were free text ("CoinDesk 2025-03-12") with no URLs. Tiers were asserted, in three overlapping fields (`status`, `confidence`, `confidence_score`). "Confirmed" Hyperdrive cited only news. HyperVault, documented by two security firms and two major outlets, was a "research lead". |
| Facts | JELLY's "$12M-13.5M HLP loss" was peak unrealized; HLP's final result was about +$703K. The three technical write-ups disagree on JELLY's position sizes and trigger; the record presented one clean sequence. SNX 2023 could not be verified. |
| Classification | CLAUDE.md required four buckets, the taxonomy had five surfaces, the schema used A-D with no stated mapping, and the classifier skill merged "market structure / core protocol" into one bucket - the distinction the repository exists to make. |
| Consistency | The hand-written consistency matrix reported "Yes" for heuristic mappings that named heuristics which did not exist (`unwind_depth_mismatch`, `protocol_absorbed_toxic_position`); case studies named primitives absent from the primitive library. |
| Staleness | The rules modeled HLP as an unbounded backstop and margin withdrawal as unrestricted. Since March 2025 liquidator vaults are capped with auto-deleveraging beyond them, and transfers require max(initial margin, 10% of position value). |
| Coverage | Missing: the XPL hyperp squeeze (2025-08), the 10 October 2025 auto-deleveraging event, the July 2025 API outage, and the xyz:SKHYNIX HIP-3 oracle failure (2026-07) - the risk class v1 listed as "no confirmed incident" with arbitrary thresholds. |

The root cause behind most rows: nothing was executable, so nothing could
fail. Consistency depended on people remembering it.

## 3. Assumptions that must hold

Each assumption is listed with what the design does when it fails.

| # | Assumption | If it fails |
|---|---|---|
| A1 | Public sources about incidents exist and can be read. | Incidents stay research leads; tiers are derived, so weak sourcing is visible instead of hidden. |
| A2 | Citations are honest (a cited source states the claim). | Unverifiable by code. `citations_checked` records whether a reviewer read every source; the report shows it. |
| A3 | Mechanisms leave traces in observable data before losses become irreversible. | True for exposures (preconditions), partly true for attacks in progress, false for key theft (detected after loss). Each rule declares its `stage`. |
| A4 | Someone can act on a rule's output in time. | Each rule names a `consumer` and `action`. A rule nobody can act on is a dashboard metric. |
| A5 | The data a feature needs can be obtained. | Each feature declares its source type. Public API covers market, backstop, dex and named-account features; clusters and orders need node data; external venues are out of scope today. Missing data yields `unknown`. |
| A6 | Thresholds can separate attacks from normal activity. | Unproven. Incidents are rare (fourteen recorded in about three and a half years, two of them confirmed) while evaluation is frequent, so precision collapses at any non-trivial false-positive rate. Five threshold values are now calibrated on recorded data (section 9) to stated targets - a cross-sectional rank or an alert budget - and the rest are marked `placeholder` or `definitional`. |
| A7 | Attackers do not adapt to published rules. | False in general (POPCAT sharded across 19 wallets). Relative, mechanism-level measures (exposure versus depth, incentive versus bond) are harder to evade than signatures. |
| A8 | Hyperliquid's mechanics stay as documented. | They change (liquidator cap, transfer margin, hyperp mark caps). Facts the code relies on are dated in comments and docs. |

## 4. Invariants

### Of the ecosystem (`knowledge/ontology/invariants.yaml`)

Stated so a violation is observable:

1. **Loss containment** - losses beyond an account's collateral are absorbed by designated backstops within stated capacity, in a published order.
2. **Price integrity** - prices used for margin, liquidation and settlement cannot be moved at a cost lower than the value moving them extracts.
3. **Liquidation is never the cheaper exit** - no account gets better execution by being liquidated than by closing.
4. **Rule stability under stress** - outcomes follow rules published before the stress.
5. **Signing authority** - only the holder, or a delegate within its scope, moves an account's assets.
6. **Least privilege** - delegated execution can do only what its function needs.
7. **Custody conservation** - an application's obligations never exceed its assets, and assets move only under its published rules.
8. **Exit availability** - users can cancel, close and withdraw when markets move.
9. **Cross-domain consistency** - an application's record of HyperCore state matches HyperCore once asynchronous actions settle.
10. **Operator bond covers abuse** - a party with power over prices, settlement or funds stands to lose more by abusing it than abuse extracts.

v1's "ecosystem trust-boundary separation" was a rule for analysts (do not
misattribute losses). It is enforced as classification structure (section 5)
and as a validator check, and it is no longer listed as a system property.
Invariants 2, 3 and 10 are inequalities between costs and payoffs; that framing
is what makes them measurable.

### Of the program (enforced by `validate.py` and tests)

- Every reference resolves (owners, mechanisms, surfaces, primitives, invariants, features, claims, sources, incidents, rules, thresholds).
- Every rule compiles: references are declared, inside the rule's entity scope, unit-consistent, and string comparisons use declared vocabularies.
- Every number in a condition is a named threshold with a unit; profiles may override only thresholds that exist, on surfaces where the rule runs.
- Evidence tiers are derived from sources, never asserted.
- A rule's anchors exhibit at least one primitive the rule detects.
- Research leads cannot raise a rule's status; `alert` mode needs a credible anchor **and** a reconstructed or recorded fixture from an anchor that fires; reconstructed values cite incident claims.
- A claimed core-protocol code defect needs a confirmed tier.
- Every rule has fixtures that fire and stay silent, and they pass.
- Missing data evaluates to `unknown`; adapters never substitute defaults.
- Generated documents equal a fresh render.

## 5. Design

### Classification: two axes in place of one bucket

A single bucket cannot express JELLY, which is market manipulation (how)
against a core-protocol design (whose control). The record carries
`control_owner` and `mechanisms` separately, plus `code_defect`
(`present`/`absent`/`undetermined`). The v1 rule "do not treat every loss as a
core bug" becomes a field and a validator check.

### Evidence: claims, then sources, then a derived tier

An incident is a set of atomic claims, each citing sources. Support per claim
is strong (a primary source, or two independent technical analyses), moderate,
or weak; the incident's tier is its weakest core claim. Disagreements become
separate claims. This replaces three overlapping confidence fields with one
computed value whose reason can be printed.

### Primitives: actions versus weaknesses

Primitives are tagged `attacker_action` or `system_weakness`. Weaknesses
support precondition monitoring with long lead time; actions support
detection in progress, with short lead time and costly false positives.

### Rules: data, compiled and tested

Rules are YAML data, not code, so they are portable across evaluators, safe to
load, and statically analyzable. Expressions use a restricted subset of Python
expression syntax parsed by `ast` and interpreted by walking the tree (no
`eval`). The checker infers kinds and dimensional units (`usd/usd` is a ratio;
basis points are a distinct unit) and enforces entity scope. Evaluation uses
three-valued Kleene logic so missing inputs produce `unknown` with a list of
what was missing. Each rule declares stage, mode, consumer, action, anchors,
named thresholds with a basis, false positives and fixtures.

Two kinds of validation are kept apart in every report:
- *evidence status* - has the mechanism been seen? (from anchors)
- *detection validation* - has this rule fired on real data from such a case?
  (from fixture provenance)

### Data: read-only, honest adapter

`hyperliquid_api.py` computes features from the public info API. Depth within
2% escalates `nSigFigs` aggregation until 20 levels reach the band edge, or
reports absence. Backstop inventory sums HLP's liquidator child vaults (or a
HIP-3 dex's `0x4000...` liquidator). HIP-3 features read deployer, oracle
updater and `setOracle` sub-deployers from `perpDexs`. Every value carries
provenance; every absence carries a reason.

### Agent layer: four skills that write validated data

`analyze-incident`, `author-rule`, `monitor-market`, `hyperevm-review` live in
`.claude/skills/`. The model reads sources and code and proposes structured
values; deterministic code checks them. v1's eleven overlapping specifications
(with worked examples that contradicted each other and the incidents) are
replaced by four procedures whose outputs must pass `validate`.

### Architecture

```
knowledge/            data (YAML): ontology, features, incidents, rules, profiles
src/hyperliquid_security/
  units.py            dimensional units
  expressions.py      parser, type checker, three-valued evaluator
  model.py            pydantic records (unknown keys rejected)
  knowledge_base.py   strict YAML loading (duplicate keys, 1e6 floats)
  evidence.py         claim support, incident tier, rule status
  engine.py           compile rules, evaluate snapshots, apply profiles
  validate.py         every methodology rule as a check
  reports.py          generated docs (CI fails if stale)
  hyperliquid_api.py  read-only snapshot builder
  cli.py              validate | report | evaluate | snapshot
.claude/skills/       agent procedures
docs/generated/       computed summaries
```

### Language: Python

- The work is data validation and analysis over small inputs; Python with
  pydantic (runtime schemas) and mypy `--strict` (static types) gives strong
  correctness checks at low contribution cost for security researchers.
- `ast` gives a safe parser for the rule language without a grammar
  dependency; YAML and JSON are first-class.
- Claude Code skills can call the CLI directly.
- A production streaming detector over node data (about 100 GB/day) would be
  better written in Rust, which Hyperliquid's node uses. Because rules are
  data with a small, specified semantics, a second evaluator can be written
  against the same files and the same fixtures; the fixtures become a
  conformance suite.

## 6. Safety and robustness in the implementation

- No `eval`/`exec`; expressions are interpreted from a whitelisted syntax tree; references must match `namespace.name`.
- YAML is loaded with a SafeLoader subclass that rejects duplicate keys and parses `1e6` as a number (PyYAML's default reads it as a string); `code_defect` avoids `yes`/`no`, which YAML 1.1 turns into booleans.
- Pydantic models forbid unknown keys, so a misspelled field is an error.
- The API client is read-only, HTTPS-only, with bounded retries; failures mark features absent with the reason, and never crash the snapshot or invent values.
- Division by zero is defined (non-zero over zero is infinite, zero over zero is unknown); NaN is unknown.
- Tests: unit tests per module, property tests for Kleene logic (De Morgan, classical agreement without unknowns), one test per validator policy that injects a single defect, adapter tests against a scripted fake API, a gate that the repository's own knowledge base validates and its generated docs are fresh. Mutation checks (disabling a policy, collapsing unknown into false) were confirmed to fail the suite.

## 7. Constraints

- **Data.** No public endpoint lists all positions; liquidation overhang, clusters and order lifetimes need a non-validating node (`--write-order-statuses`, `--write-raw-book-diffs`, fills) or the requester-pays S3 archives. External venue data (oracle inputs) is out of scope today, so external price pushes - JELLY's amplifier - have no rule yet (listed as a gap in `docs/generated/coverage.md`).
- **Base rates.** Confirmed incidents are rare; thresholds without calibration produce mostly false alarms. Calibrated values cover one quiet regime (section 9); stress regimes are absent from the data.
- **Archives.** Hyperliquid's S3 archive is requester-pays (AWS credentials billed to the requester) and, like Tardis, stores the 20-level full-precision book, which never reaches a 2% band on liquid markets and did not on thin JELLY either. Depth-based quantities need live recording; archives give only bounds.
- **Evidence.** Hyperliquid publishes few postmortems; many tiers rest on technical secondary sources. Claim-to-source mappings were verified line by line for JELLY and xyz:SKHYNIX only.
- **Mechanics drift.** Facts about the protocol are dated; re-verify before relying on numbers.
- **Scope.** Detection informs people; this repository places no orders, signs nothing and ships no exploit code.

## 8. Status and next steps

What runs today: validation of 14 incidents and 17 rules, live snapshots and
evaluation for validator-operated and HIP-3 markets, generated reports, four
skills.

Ordered by value:
1. **Calibrate across regimes** - repeat the recording during volatile weeks and
   compare; calibrate `mark_diverges_from_oracle` from continuous mark and
   oracle history (Tardis `derivative_ticker`); normalize price moves by each
   market's volatility so alerts spread across markets.
2. **Choose the growth rule's HIP-3 target, and record more days** (§9). One
   alert a day per surface gave HIP-3 a threshold of 133.65, set by one new
   listing; the options are a larger HIP-3 budget, excluding markets in their
   first days, or the definitional 1.0 as a watchlist. With one day, every
   budget threshold is that day's maximum; a week of passes would make it an
   estimate.
3. **Reconstruct anchors** - add depth and position numbers to incident
   records from archives, so depth-based rules get reconstructed fixtures.
4. **Node-data adapter** - order lifetimes, fills with liquidation tags,
   cluster discovery.
5. **External venues** - oracle-source depth, to measure cost-to-move against
   open interest (invariant 2 directly).
6. **Link checker** - fetch every source URL in CI on a schedule; flag dead
   links.
7. **Verify citations** for the remaining twelve incidents.

## 9. Calibration (2026-10-13, recalibrated 2026-10-15)

**Data.** Hyperliquid's S3 archive could not be used: it is requester-pays and
no AWS credentials were available. More importantly, archived books store the
20-level full-precision feed: in Tardis's record of that feed for BTC on
2025-11-01, 0 of 157,225 snapshots reached the 2% band (median span 1.8 bps),
and even thin JELLY's levels spanned only 0.7% on 2025-03-01. The thresholds
were therefore calibrated on data recorded for the purpose and committed in
`knowledge/calibration/data/`:

- 145 passes over every listed perp (178 validator-operated, 161 HIP-3), one
  every 10 minutes from 01:02 UTC on 2026-10-14 to 01:02 UTC on 2026-10-15,
  depth measured with escalating `nSigFigs`, no pass skipped
  (`passes_2026-10-14.jsonl.gz`). It replaces a two-hour recording (06:24-08:21
  UTC on 2026-10-13); a first 24-hour attempt ended after two hours on a
  dropped connection (fixed in v3.3.1), and a second died with its container.
- 17 days of 5-minute candles for the same markets (trade prices, a proxy for
  mark).

**Targets.** A threshold needs a target before it needs data. Precondition
rules rank markets: the 90th percentile of each market's median ratio, so
firing means "among the most exposed tenth". Alert and active-attack rules have
a budget: the lowest threshold at which it and every higher one give at most
one alert episode per day per surface (episode counts are not monotone in the
threshold, so the search walks down from the top).

**Results** (details in `docs/generated/calibration.md`; two-hour values in
brackets):

| Threshold | Validator-operated perps | HIP-3 |
|---|---|---|
| Open interest / thinner side's 2% depth | 68.87 [67.27] (median market 17.4) | 31.04 [39.35] (median 7.6) |
| HIP-3 open interest cap / thinner side's 2% depth | - | 420.78 [558.64] (median 93.6) |
| 5-minute move, bps (candles) | 832.1 (99.99th pct 477) | 725.3 (para:TREAD gives 8 of 17 episodes) |
| Last hour's new open interest / 2% depth | 9.64 (PYTH) | 133.65 (io:PRL) |

The validator-operated ranking barely moved. The HIP-3 ones fell because the
two-hour window sat outside US trading hours: HIP-3 markets are mostly equity
and index perps, whose books deepen while the underlying trades. The median HIP-3 market's
ratio is 8.7 between 06:00 and 08:00 UTC and 4.5 between 14:00 and 20:00.

**Checks against incidents** (never used to choose a value):

- JELLY's attack day: 5-minute trade moves up to 4,804 bps - fires. The day
  before also reached 1,083 bps and would have fired: an early sign or a false
  alarm, which the data cannot separate.
- xyz:SKHYNIX: the 1,790 bps mark fall fires against 725.3.
- JELLY 25 days before its attack: the archive bounds its ratio at a median 33.7
  at most, below 68.87 - the precondition rule would not have flagged it.
- POPCAT 11 days before: the bound's median (68.4) is 0.7% below 68.87. The
  calibration reports "would not have fired"; with the bound on the threshold,
  read it as inconclusive.
- The growth rule's anchors (JELLY, POPCAT, FARTCOIN) cannot be checked: no
  available source holds hourly open interest for their attack days.

`tests/test_calibration.py` recomputes every calibrated value from the committed
data, so a value, a rule's report expression or the data cannot change without
the others.

**Open-interest growth (v3.2.0, revised in v3.3.0, calibrated in v3.4.0).**
The JELLY check above shows a level-based exposure rule had no lead time: the
attacker created the exposure on the day. `open_interest_growth_exceeds_depth`
measures the last hour's new open interest (in asset units, valued at the
current mark, so a price move is not growth) against the thinner side's 2%
depth, and requires the growth to be material.

Materiality was first a share of the backstop's capital (1%; $330k against
HLP's liquidators, $33.0M on 2026-10-13). That works on validator-operated
perps and fails on HIP-3: every dex's backstop held $0-$104k, so any growth
counted as material, and dust markets dominated. v3.3.0 replaced it with an
absolute floor, `min_growth_usd` ($250k, placeholder): materiality is about the
cost of a person's attention, which does not shrink with the market.

The depth threshold is calibrated to the one-episode-a-day budget, holding the
floor fixed. Episodes per day on the full-day recording:

| Threshold (x depth) | 1 | 2 | 5 | 10 | 20 | budget |
|---|---|---|---|---|---|---|
| Validator-operated | 28 (13 markets) | 16 | 5 | 0 | 0 | 9.64 |
| HIP-3 | 52 (35 markets) | 21 | 13 | 4 | 3 | 133.65 |

On validator-operated perps the budget picks one real event: PYTH, 03:13-04:03
UTC, about $2.1M of new open interest an hour (+40%) against $220-275k of
depth. On HIP-3 it fails. io:PRL, listed at 17:57 UTC, still had $2.3k of depth
when $311k of positions arrived, and its 133.65 hides xyz:CRWV ($21-34M an hour
against $1.1-1.8M, 13-23x, 19:45-20:46 UTC) and xyz:SKHX ($72M against $4.5M,
16x, 23:56 UTC). The value is applied as computed, because changing the target
after seeing the data would be tuning; the target itself needs a decision
(§8, item 2). The rule stays in `report` mode, and with one day the budget's
single episode is simply the day's maximum.

**Recording on demand (v3.3.0).** `hyperliquid-security record --out-dir DIR
--hours 24` records a session that resumes when rerun (one file per pass and a
manifest), so a day survives restarts; `pack` merges it into one file to commit.
The `record` GitHub workflow (Actions -> record -> Run workflow) runs a session
as six-hour segments that resume one another and uploads the packed passes and
the `calibrate` output as an artifact, without writing to the repository.
