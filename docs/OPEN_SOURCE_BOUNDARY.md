# Open-source boundary

## Included

- The ontology, data dictionary, incident records and rules.
- A reference rule evaluator, the validator, and a read-only adapter for
  Hyperliquid's public API.
- Claude Code skills.

## Excluded

- Economic simulation of attacks, attack graphs and probabilistic scoring.
- Production orchestration, alert routing and analyst workflows.
- Anything that places orders, signs transactions, or exploits a system.

## Why the boundary moved

v1/v2 excluded every runnable component. A rule that cannot run cannot be
tested, so v1's rules carried defects no one could see (unused thresholds,
inverted logic, unit errors, inputs no API provides). v3 ships the minimum
executable layer needed to check the rules - a reference evaluator over
snapshot files and a read-only data adapter - while keeping simulation and
production systems out. Whether that boundary fits the project's commercial
plans is the maintainers' decision; this note records the reason for the
change.
