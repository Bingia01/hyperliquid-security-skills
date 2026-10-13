---
name: monitor-market
description: Take a live, read-only snapshot of a Hyperliquid market (validator-operated perp, hyperp, or HIP-3 market) from the public API and evaluate the rule set against it, explaining each outcome and what is unknown. Use when asked to check a market, a HIP-3 dex, HLP's liquidator exposure, or whether a market looks manipulable right now.
allowed-tools: Bash(hyperliquid-security *)
---

# Monitor a market

```bash
hyperliquid-security snapshot --coin ETH -o /tmp/eth.json
hyperliquid-security snapshot --coin xyz:NVDA --dex xyz -o /tmp/nvda.json
hyperliquid-security snapshot --coin SOMEHYPERP --surface hyperps -o /tmp/h.json
hyperliquid-security evaluate /tmp/eth.json
```

History features compare with earlier snapshots of the same market, passed
with `--previous` (repeatable): the five-minute mark move needs one taken four
to six minutes earlier, open interest growth one taken 55 to 65 minutes
earlier. Keep each snapshot file; each feature picks the one whose age fits.

```bash
hyperliquid-security snapshot --coin ETH --previous /tmp/eth-1h.json \
  --previous /tmp/eth-5m.json -o /tmp/eth.json
```

## Reading the results

- `fires` - the condition holds **against the rule's threshold**. Most
  thresholds are `placeholder` (see `docs/generated/rules.md`); a firing
  placeholder rule says "this is unusual by an uncalibrated yardstick", not
  "an attack is happening". Say which.
- `silent` - the condition is false on the data measured.
- `unknown` - inputs were missing; list them from `missing`. Most cluster,
  order and account features need node data or a named account. Never report
  `unknown` as safe.
- `not_applicable` - the rule does not cover this surface (hidden unless
  `--all`).

Always quote the `report` values (the actual ratios) and the snapshot's
`provenance` for anything surprising: it says how each value was measured
(for example which `nSigFigs` aggregation reached the 2% depth band) or why
it is absent.

## What the snapshot cannot see

- All positions in a market (no public endpoint); liquidation overhang.
- Order lifetimes and individual orders (the book is aggregated).
- External venues' prices and depth (oracle inputs).
- Positions held by a deployer through addresses not registered as price
  setters.

State these limits whenever they bear on the question asked. Do not place
orders or sign anything; the client is read-only by construction.
