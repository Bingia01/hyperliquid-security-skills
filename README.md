# Hyperliquid Security for Claude Code

Open-source research framework for classifying, reconstructing, and analyzing Hyperliquid-class incidents across core protocol surfaces, market-structure abuse, user/account compromise, and HyperEVM ecosystem applications.

## What this is

A structured knowledge base and Claude Code skill pack for reasoning about Hyperliquid security incidents. You give it an incident (a hack, an exploit, a suspicious event). It helps you classify it, reconstruct what happened step by step, extract the reusable mechanics, identify which safety properties broke, and draft detection rules.

If you're building on HyperEVM and want a pre-ship security check, it walks through each vulnerability class from the HyperEVM taxonomy and checks your code for matching patterns, producing findings with line numbers and fix recommendations.

The core pipeline:

```
incident → attack movie → primitive → invariant → heuristic → rule → threshold profile
```

Each stage has a corresponding Claude Code skill, reference documents, and templates.

This repository teaches a research methodology and provides the structured data to apply it. Building production tools on top of it is a separate effort (see `docs/OPEN_SOURCE_BOUNDARY.md`).

## How to use this repo

### If you're analyzing a new incident

1. **Classify it.** Use the `incident-classifier` skill. Feed it whatever you have — a tweet thread, a postmortem, wallet traces, order book data. It will assign the incident to one of four buckets (core protocol, market abuse, user compromise, ecosystem app) and flag evidence gaps.

2. **Reconstruct the attack movie.** Use the `attack-movie-builder` skill. Write out every step as a causal chain: what had to be true, what the attacker did, how the system reacted, where losses were realized.

3. **Extract primitives.** Use the `primitive-extractor` skill. Pull out the reusable mechanics (e.g., "toxic position inheritance," "arbitrary external call"). Check them against the existing library in `docs/research/ATTACK_PRIMITIVES.md`.

4. **Map broken invariants.** Compare the extracted primitives against the seven system invariants in `docs/analysis/INVARIANTS_AND_BREAKERS.md`. Which safety properties failed?

5. **Draft heuristics.** Use the `heuristic-generator` skill. Turn each primitive into a detection idea with required data, logic, false positives, and follow-up tests.

6. **Encode as rules.** Add machine-readable entries to `rules/heuristics.v1.yaml` following the existing format.

7. **Tune thresholds.** Choose the right threshold profile in `rules/threshold_profiles/` based on the market surface (core perps, HIP-3, HIP-4, or HyperEVM apps).

For a concrete example of this pipeline applied to a real incident, read `case_studies/confirmed/jelly_attack.md` alongside `data/incidents/confirmed/jelly_attack.yaml`.

### If you're building on HyperEVM and want a pre-ship security check

Use the `hyperevm-pre-ship-review` skill. Point it at your Solidity source directory. It walks through each vulnerability class from the HyperEVM taxonomy and checks your code for matching patterns, producing findings with line numbers and fix recommendations.

We don't recommend this to be a replacement for a professional audit. It catches known pattern-level issues documented in the taxonomy — arbitrary calls, permission boundaries, approval abuse, reentrancy, upgrade bugs, and HyperEVM-specific interactions.

### If you're reviewing existing coverage

Start with the coverage matrix (`docs/research/COVERAGE_MATRIX.md`) to see which surfaces have observed incidents, written heuristics, and threshold profiles. Cross-check against the consistency matrix (`docs/CONSISTENCY_MATRIX.md`) to verify that every incident has matching data records, case studies, and primitive mappings.

### If you're using the Claude Code skills

See `skills/README.md` for the full skill index, pipeline flow, and what each skill expects as input and output.

## Skills overview

The `skills/` directory contains 11 Claude Code skill specifications. Ten are organized around the incident research pipeline (classify → reconstruct → extract → analyze → generate rules). One — `hyperevm-pre-ship-review` — is a pre-deployment review tool for developers building on HyperEVM.

See `skills/README.md` for the complete index.

## Evidence model

This repo uses three evidence tiers:
- **confirmed** — strong public documentation, suitable to anchor detection rules
- **credible_report** — useful but still leaning on secondary reporting
- **research_lead** — kept for coverage, must not drive strong rules nor primitives

The evidence tier was conceived because we believe a weak evidence is preserved for completeness but must not be allowed to contaminate the heuristic layer.

## Repository layout

```text
.
├── README.md
├── CLAUDE.md
├── docs/
│   ├── architecture/
│   │   ├── hyperliquid_attack_taxonomy.md
│   │   └── hyperevm_vulnerability_taxonomy.md
│   ├── analysis/
│   ├── research/
│   ├── assets/
│   └── case_studies/README.md
├── data/
│   └── incidents/
│       ├── confirmed/
│       ├── credible_reports/
│       └── research_leads/
├── case_studies/
│   ├── confirmed/
│   ├── credible_reports/
│   └── research_leads/
├── rules/
│   ├── heuristics.v1.yaml
│   └── threshold_profiles/
├── schemas/
├── skills/
└── templates/
```

## Start here

- Attack taxonomy: `docs/architecture/hyperliquid_attack_taxonomy.md`
- HyperEVM vulnerability taxonomy: `docs/architecture/hyperevm_vulnerability_taxonomy.md`
- Invariants: `docs/analysis/INVARIANTS_AND_BREAKERS.md`
- Heuristic library: `docs/research/HEURISTIC_LIBRARY.md`
- Skills index: `skills/README.md`
- Consistency and coverage: `docs/CONSISTENCY_MATRIX.md`, `docs/research/COVERAGE_MATRIX.md`
