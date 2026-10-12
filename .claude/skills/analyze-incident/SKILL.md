---
name: analyze-incident
description: Turn a Hyperliquid-ecosystem incident (exploit, manipulation, drain, outage, oracle failure) into a validated incident record with sourced claims, two-axis classification, attack movie, primitives and violated invariants. Use when given a postmortem, article, thread, wallet trace or incident name to analyze or add to the knowledge base.
---

# Analyze an incident

The output is one file, `knowledge/incidents/<id>.yaml`, that passes
`hyperliquid-security validate`. Prose without a validated record is not done.

## Rules that are never relaxed

- **Never cite a source you have not read.** Never write a URL you did not
  fetch or see verbatim. If a page will not load, say so in `open_questions`
  and leave `citations_checked: false`.
- **A claim cites only sources that state it.** If three write-ups agree on
  the mechanism but disagree on sizes, write one core claim for what all three
  say and a separate, non-core claim recording the disagreement. Do not pick a
  side silently. (JELLY: three technical sources disagree on position sizes
  and on whether margin withdrawal or the price rise triggered liquidation.)
- **Peak unrealized is not realized.** Record each loss with its `basis`.
  JELLY's widely quoted "$12M loss" was peak unrealized; HLP ended about $703K
  in profit.
- **`code_defect: present` needs evidence of software doing something its own
  specification does not intend.** Economic design that worked as specified is
  `design_exploit`. The validator rejects a claimed core-protocol code defect
  below the confirmed tier.

## Procedure

1. **Collect sources.** For each, record `publisher`, `url`, `published` (only
   if you saw the date) and `tier`:
   - `primary` - the affected party (official statement, postmortem, docs) or
     on-chain data you can point to (explorer, API output);
   - `technical_secondary` - a security or chain-analytics firm's own analysis;
   - `news` - journalism, including articles quoting firms or the team;
   - `social` - individual posts.
   An article quoting Hyperliquid's statement is `news`; the statement itself
   is `primary` only if you cite it directly.

2. **Write claims.** Atomic statements, each with the sources that support it.
   Mark `core: true` on the claims that establish the mechanism - the claims
   that, if false, would change the classification. The incident's tier is
   derived from the weakest core claim (see `src/hyperliquid_security/evidence.py`);
   you never set it.

3. **Classify on two independent axes** (`knowledge/ontology/`):
   - `control_owner` - whose control failed or was exploited
     (`hypercore`, `market_deployer`, `hyperevm_application`,
     `account_holder`, `infrastructure_operator`);
   - `mechanisms` - how (`code_defect`, `design_exploit`,
     `market_manipulation`, `credential_compromise`, `insider_abuse`,
     `operational_failure`, `market_stress`, `reconnaissance`).
   A loss on Hyperliquid is not a core-protocol bug unless the evidence says so.

4. **Build the attack movie.** Steps with `phase` (`preconditions`, `setup`,
   `trigger`, `protocol_reaction`, `amplification`, `loss`, `response`), each
   citing claims. A step with no claims is inferred; that is allowed and counted
   in the generated report. Omit phases that did not happen.

5. **Map primitives and invariants** from `knowledge/ontology/primitives.yaml`
   and `invariants.yaml`. Only list a primitive the claims support. A new
   primitive goes into the ontology file with `kind`, `description` and
   `threatens`; say why no existing one fits.

6. **Write the file and validate.**
   ```bash
   hyperliquid-security validate
   hyperliquid-security report   # regenerate docs/generated/
   ```
   Fix every error. Read every warning.

7. **Check coverage.** Open `docs/generated/coverage.md`. If the incident
   exhibits a primitive no rule detects, say so and suggest the `author-rule`
   skill. If a rule should now cite this incident as an anchor, add it - the
   validator checks the incident exhibits a primitive the rule detects.

8. **Set `citations_checked: true` only after reading every cited source
   against every claim that cites it.**

## Surface checklists

Read the one that matches the control owner before writing the movie:
[reference/checklists.md](reference/checklists.md).

## Output to the user

Report the derived tier and why (which core claim is weakest), every
disagreement between sources, the open questions, and what would raise the
tier (usually a primary source or a second independent technical analysis).
