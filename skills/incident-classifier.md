# Skill — Incident Classifier

## Purpose
Classify a Hyperliquid-related event into the correct bucket and attack class.

## Inputs
- incident text
- postmortem excerpts
- code snippets
- trade / order-book traces
- wallet flow traces

## Outputs
- primary bucket
- secondary bucket
- attack type
- confidence
- evidence gaps

## Decision tree
1. Is the loss caused by code execution in an app contract?
   - yes → Bucket D
2. Is the loss caused by stolen signing authority?
   - yes → Bucket C
3. Is the issue driven by pricing, liquidation, or market-structure abuse?
   - yes → Bucket B
4. Is the issue a core infra / matching / bridge / validator / protocol logic issue?
   - yes → Bucket A

## Caveat
A single incident can touch multiple buckets, but pick one primary bucket.
