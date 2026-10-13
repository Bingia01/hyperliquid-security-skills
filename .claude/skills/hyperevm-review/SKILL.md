---
name: hyperevm-review
description: Pre-deployment security review of Solidity contracts for HyperEVM - generic EVM risks plus HyperEVM/HyperCore interaction risks (CoreWriter, read precompiles, token linking, decimals, dual blocks) - producing findings with file and line evidence and rule-engine feature values. Use when asked to review, audit or check HyperEVM contracts before shipping.
---

# HyperEVM pre-deployment review

This is a first pass, not an audit. Its value over generic tools is the
HyperEVM-specific layer; its risk is false confidence. In pre-deployment
review a missed critical issue costs far more than a false alarm, so **never
drop a candidate finding because a heuristic says it is "probably not
reachable" - drop it only when you can show why it is unreachable.**

## 1. Run deterministic tools first (if available)

```bash
forge build && forge test          # or the project's own test command
slither . --exclude-dependencies   # if installed
aderyn .                           # if installed
```

Tools find generic patterns more reliably than reading. Triage their output;
do not re-derive what they already cover. If none are installed, say so in
the report - the review is then weaker, not equivalent.

## 2. Inventory before judging

For each contract: deployable / library / interface / test-only; who can call
each external function; which roles exist and who holds them (EOA, multisig
threshold, timelock delay); which tokens it holds and which allowances or
operator rights users grant it; every external call site; every CoreWriter
call and precompile read.

Locate the HyperCore integration points mechanically:

```bash
rg -n -i "0x3333333333333333333333333333333333333333|sendRawAction|CoreWriter" src
rg -n -i "0x00000000000000000000000000000000000008[0-1][0-9a-f]|L1Read|precompile" src
rg -n -i "0x2222222222222222222222222222222222222222|0x20000000000000000000000000000000000000|0x5555555555555555555555555555555555555555" src
```

## 3. Checks

Work through [reference/hyperevm_checks.md](reference/hyperevm_checks.md).
It covers HyperCore interaction first, then the generic classes with their
common unsound shortcuts called out.

## 4. Score with the rule engine

For the contract's most permissive external call path, and for each
privileged role, write a snapshot and evaluate it - the engine, not prose,
decides whether `caller_controlled_external_call`,
`privileged_role_exceeds_function` and `core_action_assumed_complete` fire:

```json
{"surface": "hyperevm_apps", "subject": "Router.execute",
 "values": {"contract.holds_or_spends_user_assets": true,
            "contract.call_target_control": "allowlisted",
            "contract.call_data_control": "caller_supplied",
            "contract.call_entrypoint_access": "anyone",
            "contract.post_call_balance_check": false,
            "contract.uses_core_writer": false}}
```

```bash
hyperliquid-security evaluate router.json
```

Each value must be justified by a file and line in the report. Leave a
feature out (it becomes `unknown`) rather than guess.

## 5. Report

For each finding: class, severity (impact if exploited x who can trigger
it), file:line evidence, exploit sketch in words (no runnable exploit code),
and a concrete fix. Separate **findings** (defects in this code) from
**consumer advisories** (risks for code that integrates this code). End with:
which checks found nothing, which tools ran, and what was out of scope
(economic design, off-chain components, deployment configuration).
