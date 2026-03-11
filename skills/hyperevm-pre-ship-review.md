# Skill — HyperEVM Pre-Ship Review

## Purpose

Pre-deployment security review of HyperEVM smart contracts against known vulnerability patterns from the HyperEVM vulnerability taxonomy.

This skill reads Solidity source code directly and produces findings with severity, line-number evidence, and fix recommendations. It is designed for developers building on HyperEVM who want a structured security check before deploying.

## Reference taxonomy

`docs/architecture/hyperevm_vulnerability_taxonomy.md`

## Inputs

- Path to Solidity source files (single contract, directory, or Foundry/Hardhat project root)
- Optional: deployment context — what the contract does, what roles exist, what external systems it interacts with

## Step 0: Classify what you're reviewing

Before running any checks, classify each file:

**Code type:**
- `library` — a Solidity library (the `library` keyword). Libraries have no storage, no access control, and no direct external callers. Most checks about permissions and reentrancy don't apply to the library itself — they apply to contracts that consume it.
- `contract` — a deployable contract with its own storage and external functions. All checks apply fully.
- `abstract contract` / `interface` — definitions only. Skip unless reviewing the implementing contract.

**Deployment intent:**
- `production` — code intended for mainnet deployment
- `example / reference` — code in test/, examples/, or script/ directories, or labeled as example/demo in comments. Cap severity at informational.
- `test` — test harnesses. Skip entirely.

State the classification at the top of the review for each file. This classification determines how to interpret findings:
- For libraries: report issues as consumer advisories (see output format) unless the bug is in the library's own internal logic.
- For example code: report issues as informational with a note that the code is not intended for production.
- For production contracts: report findings at full severity.

## Review procedure

For each contract, walk through the following checks in order. For each check, cite specific file paths, line numbers, and code patterns as evidence. Do not skip a check — if a category has no findings, state that explicitly.

### 1. Arbitrary external call

Scan for:
- Functions that accept an `address` parameter and pass it to `.call()`, `.delegatecall()`, or `.staticcall()`
- Functions where calldata is constructed from user-supplied `bytes`
- Router or executor patterns where the call target is not hardcoded or restricted to an allowlist

Qualify before flagging:
- Is the call target derived from user input, or is it hardcoded / deterministic? If hardcoded or derived from protocol constants, this is not a finding.
- Is the calldata constructed from user-supplied bytes, or is it built internally from typed parameters? If built internally, this is not a finding.
- Only flag when the target OR the calldata can be influenced by an external caller.

Evaluate:
- Is the target restricted to a hardcoded allowlist?
- Is the calldata shape-constrained (function selector whitelist, parameter validation)?
- Are there post-call invariant checks (balance deltas, state consistency)?

### 2. Permission boundary failure

Scan for:
- Role and modifier definitions (`onlyOwner`, `onlyOperator`, custom access control)
- All functions gated by each role — list them
- Whether any role can move user funds, upgrade the contract, or invoke arbitrary external calls

Qualify before flagging:
- Is this a library? If yes, libraries don't have access control — skip this check or note it as a consumer advisory.
- Is this example/test code? If yes, missing access control is expected. Note as informational, not as a finding.
- Only flag when a production contract exposes sensitive functions without adequate access control.

Evaluate:
- Does any role have more power than its stated purpose requires?
- Can an operator do things beyond its business function (e.g., position management role that can also transfer arbitrary tokens)?
- Is the admin/owner key a single signer or multisig?

### 3. Approval abuse

Scan for:
- `approve()` and `transferFrom()` usage patterns
- Whether the contract requests `type(uint256).max` approvals
- Whether approved amounts match what the contract actually needs to spend

Evaluate:
- Could a compromised or upgraded version of this contract drain tokens that users have approved?
- Are approvals scoped to the minimum amount needed per transaction?

### 4. Reentrancy

Scan for:
- External calls (`.call()`, `.transfer()`, `.send()`, calls to other contracts) that occur before state updates
- Functions that send ETH or tokens before updating internal balances or flags
- Presence or absence of reentrancy guards (`ReentrancyGuard`, `nonReentrant` modifier)

Qualify before flagging:
- Can the target of the external call be influenced by a user? If the target is a hardcoded system contract or protocol address, reentrancy is not possible — this is not a finding.
- Does the external call forward enough gas for a reentrant call? `.transfer()` and `.send()` forward 2300 gas, which prevents reentrancy.
- Only flag when the target is user-influenced AND the call forwards arbitrary gas AND state updates happen after the call.

Evaluate:
- Can any external call re-enter a state-changing function before that function's state updates complete?
- Are all state changes made before external calls (checks-effects-interactions pattern)?

### 5. Storage collision and upgrade bugs

Scan for:
- Proxy patterns (ERC-1967, transparent proxy, UUPS, custom)
- Storage layout compatibility between proxy and implementation contracts
- Storage gap reservations (`uint256[50] private __gap`) in base contracts
- Whether the implementation contract is initialized or can be called directly

Evaluate:
- Could a future upgrade corrupt existing storage by inserting new variables before existing ones?
- Can an attacker call `initialize()` on the implementation contract directly?

### 6. HyperEVM-specific interactions

Scan for:
- Calls to Hyperliquid precompiles or system contracts
- Oracle or price data consumption — where does the contract get price data? Is it from a manipulable source?
- Interactions with HLP, margin, liquidation, or bridge systems
- Assumptions about Hyperliquid-specific behavior (e.g., transaction ordering, gas model)

Qualify before flagging:
- Is this a library that exposes raw precompile data? If yes, the library is doing its job correctly. Report price manipulation risk as a consumer advisory, not as a finding against the library.
- Is the async execution model a property of the platform, not a bug in the code? If yes, report as a consumer advisory.
- Only flag as a finding when the reviewed contract itself makes an unsafe assumption (e.g., using spot price for collateral valuation without staleness checks, or assuming sequential sendRawAction calls execute atomically).

Evaluate:
- Does the contract trust external price or state data that an attacker could influence by manipulating a thin market?
- Could a flash-loan or same-block manipulation affect the data this contract relies on?
- Are there assumptions about Hyperliquid's execution model that may not hold?

## Output format

Classify each result as either a **finding** or a **consumer advisory**.

**Findings** are bugs or vulnerabilities in the reviewed code itself. For each finding:
- **Vulnerability class** — which taxonomy category
- **Severity** — critical / high / medium / low / informational
- **Location** — file path and line number(s)
- **Evidence** — the specific code pattern found
- **Why it matters** — what an attacker could do with this
- **Recommended fix** — concrete change to make

**Consumer advisories** are risks that apply to code that uses or builds on the reviewed code. They are not bugs in the reviewed code. Common in library reviews. For each advisory:
- **Risk category** — what type of risk (price manipulation, async execution, surface exposure, etc.)
- **What a consuming contract should do** — concrete guidance
- **What could go wrong if ignored** — the failure scenario
- **Reference** — link to taxonomy entry or incident if applicable

Summary section at the end:
- Total findings by severity
- Total consumer advisories
- Which taxonomy classes had no findings (clean)
- Recommended next steps before deployment

## Relationship to other skills

This skill is for **pre-deployment review** — you have source code and want to find issues before shipping.

The `ecosystem-exploit-analyzer` skill is for **post-incident analysis** — an incident already happened and you are investigating a HyperEVM contract involved in it.

## Limitations

This is not a replacement for a professional security audit. It catches known pattern-level issues documented in the taxonomy. It does not:
- Analyze business logic correctness
- Detect issues that require understanding the full protocol design
- Run static analysis tools (Slither, Mythril, etc.)
- Test against live or forked chain state

For production deployments handling significant value, use this as a first pass and follow up with a professional audit.
