# Detailed breakdown

This repository is an open-source research framework for Hyperliquid-class security analysis.

## What we did
We started with the idea that serious detection work should not begin with a pile of headlines. It should begin with:
1. a clean attack taxonomy,
2. an evidence hierarchy,
3. a canonical incident schema,
4. attack-movie reconstruction,
5. primitive extraction,
6. invariant mapping,
7. heuristic drafting,
8. machine-readable rules,
9. threshold profiles by surface.

That sequence matters because Hyperliquid has seen more than one incident shape. Some events are best understood as economic or market-structure abuse, some as user-compromise, and some as ecosystem-app or trust-boundary failures.

## The mental model
The repository uses one central chain:

`incident -> attack movie -> primitive -> invariant -> heuristic -> rule -> threshold profile`

### Incident
A real-world event, public report, or credible research lead.

### Attack movie
A step-by-step explanation of what had to be true, what the attacker did, how the system reacted, and where losses were realized.

### Primitive
A reusable mechanism such as:
- toxic position inheritance,
- strategic margin withdrawal,
- spoof-wall support,
- arbitrary external call,
- wallet behavioral break.

### Invariant
The safety property that should have held:
- liquidation absorbability,
- fair-price integrity,
- margin integrity,
- permission-bounded execution,
- user-signing control.

### Heuristic
A reusable detection idea grounded in the primitive and invariant.

### Rule
A machine-readable expression of that heuristic.

### Threshold profile
The same rule tuned differently for:
- core perps,
- HIP-3 markets,
- HIP-4 style markets,
- HyperEVM apps.

## Evidence tiers
The repo is split into three evidence tiers:
- **confirmed** — strong enough to anchor heuristics,
- **credible_report** — useful and relevant, but still secondary-heavy,
- **research_lead** — documented for coverage and future investigation, but not allowed to anchor strong rules.

This is deliberate evidence hygiene. Weak evidence may be preserved without contaminating the main rule set.

## Why the repo is split by surface
The attack taxonomy separates:
- core protocol,
- market structure,
- user accounts,
- ecosystem apps,
- infrastructure / crisis path.

This prevents the common error of treating every loss on Hyperliquid as if it were a core code exploit.

## Open-source versus closed-source
This repository intentionally excludes:
- economic simulation modules,
- attack graphs and probabilistic scoring,
- runnable production detectors,
- proprietary Shepherd workflows.

Those are better kept closed-source. The public repo teaches the research framework, shows the reasoning surface, and creates a strong collaboration base without giving away the proprietary execution layer.

## What “production-ready” means here
In the open-source context, production-ready means:
- the layout is stable,
- evidence quality is explicit,
- docs and data agree,
- each major artifact has an obvious home,
- contributors can extend the corpus without breaking the methodology,
- the repo clearly marks what is and is not in scope.

It does not mean this repository is a live detector or exploit engine by itself.
