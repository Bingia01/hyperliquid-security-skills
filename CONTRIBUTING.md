# Contributing

Most valuable contributions, in order:

1. **Primary sources** for existing incidents (official statements,
   postmortems, explorer links) - they raise derived tiers.
2. **Citation checks** - read every source of an incident against its claims
   and set `citations_checked: true`.
3. **Calibration data** - distributions of rule ratios across markets from
   archived data, with the method stated, replacing `placeholder` thresholds.
4. **Reconstructed fixtures** - incident numbers (depth, positions) with
   cited claims, so rules can be shown to fire on real cases.
5. New incidents, rules and features.

## Requirements for every change

- `hyperliquid-security validate` reports no errors.
- `pytest`, `ruff check`, `ruff format --check` and `mypy` pass.
- `hyperliquid-security report` has been run; generated files are committed.
- New features state an honest `source.type`; `public_api` features name the
  request type and field and have been checked against the live API.
- No source is cited unread; no URL is written that was not fetched or seen
  verbatim.
- Nothing that places orders, signs transactions or exploits a system.
