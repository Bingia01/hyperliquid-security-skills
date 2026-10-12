# HyperEVM review checks

Facts below were taken from Hyperliquid's developer documentation and checked
against mainnet where marked; re-verify against current docs before relying
on exact numbers.

## A. HyperCore interaction (the HyperEVM-specific layer)

### A1. CoreWriter actions are asynchronous and can fail silently

- CoreWriter (`0x3333333333333333333333333333333333333333`,
  `sendRawAction(bytes)`) emits an event; HyperCore executes the action after
  the EVM block. Orders and vault transfers are deliberately delayed by a few
  seconds.
- A HyperCore action that fails does **not** revert the EVM transaction.
- **Check:** does the contract credit, debit, mint shares or release funds as
  if the action succeeded in the same transaction? Is there a pending state
  and a later reconciliation against HyperCore state? Can a user withdraw or
  act on the optimistic state before reconciliation?
- Feature: `contract.accounting_assumes_core_success`.

### A2. Read precompiles see a snapshot

- Precompiles at `0x...0800`-`0x...0814` (positions, spot balances, vault
  equity, withdrawable, mark, oracle and spot prices, block number, asset and
  token info, best bid/offer, margin summary) return HyperCore state as of the
  EVM block's construction. A contract cannot observe its own CoreWriter
  effects in the same block.
- Invalid input consumes all gas passed to the call.
- **Check:** price reads used for collateral or liquidation - which price
  (mark, oracle, spot), what manipulation cost, any staleness bound? Are
  precompile calls made with bounded gas? Is a same-block read assumed to
  reflect a just-sent action?

### A3. Prices and units

- Perp prices from precompiles are scaled by `10^(6 - szDecimals)`; spot by
  `10^(8 - base szDecimals)`.
- Linked tokens differ in decimals between HyperCore (`weiDecimals`) and the
  EVM (`evm_extra_wei_decimals`, range -2 to 18); non-round amounts are burned
  on transfer.
- **Check:** every conversion between HyperCore and EVM amounts and prices;
  rounding direction (who absorbs dust); tests with tokens whose extra decimals
  are negative (USDC was -2 on 2026-10-12) and large positive.

### A4. Token linking and system addresses

- A linked token moves to HyperCore by transfer to its system address
  (`0x20` followed by the token index); HYPE uses
  `0x2222222222222222222222222222222222222222`. HyperCore-to-EVM credits arrive
  through a system transaction calling `transfer` on the linked ERC20.
- The protocol does not validate the linked ERC20's code; it can be arbitrary.
- **Check:** does the contract treat a transfer to a system address as an
  ordinary transfer (it leaves the EVM)? Does it assume a linked token is a
  standard ERC20 without hooks? Does it rely on the destination HyperCore
  account already existing (required before the EVM block)?

### A5. Blocks, gas and HYPE

- Fast blocks (about 1 s, small gas limit) and big blocks (about 1 min, 30M
  gas) share one block-number sequence; opting into big blocks is a per-user
  HyperCore flag.
- Only the next 8 nonces per address are accepted.
- HYPE is the native gas token; wrapped HYPE is at
  `0x5555555555555555555555555555555555555555`.
- **Check:** functions whose gas could exceed fast-block limits (unbounded
  loops) - would they be stuck? Any assumption that `block.number` advances at
  a fixed rate?

## B. Generic classes, with the unsound shortcuts named

### B1. Caller-controlled calls

- Flag any call whose **target or calldata** a caller chooses, when the
  contract holds assets or is approved/operator for users' assets. An
  allowlist of targets does not make free calldata safe if an allowlisted
  target holds user positions (Hyperdrive, 2025-09).
- Post-call balance checks reduce but do not remove the risk.
- Features: `contract.call_target_control`, `contract.call_data_control`,
  `contract.call_entrypoint_access`, `contract.holds_or_spends_user_assets`,
  `contract.post_call_balance_check`.

### B2. Reentrancy

Unsound shortcuts to avoid:
- "The target is hardcoded, so no reentrancy" - a hardcoded token with hooks
  (ERC-777, ERC-1155/721 `safeTransfer` callbacks to user addresses) or an
  upgradeable target can call back.
- "`.transfer`/`.send` forward 2300 gas, so no reentrancy" - gas costs have
  been repriced before; do not rely on stipends as a security boundary.
- "State is updated after the call only in this function" - check
  cross-function reentrancy (another function reading the stale state) and
  read-only reentrancy (a view used by another protocol during the callback).
- Feature: primitive `reentrant_state_update`.

### B3. Privileged roles

- List every role and every function it gates. One excess power over user
  assets, upgrades or arbitrary calls is a finding; do not wait for two.
- Who holds the role: single key, multisig (threshold), timelock (delay vs
  users' ability to exit)?
- Features: `role.*`.

### B4. Approvals and allowances

- Does the contract ask for unlimited approvals? If it is upgradeable or has
  an arbitrary-call path, every approval is at risk from one defect.

### B5. Upgrades and initialization

- Can anyone call `initialize` on the proxy or the implementation? Are
  storage layouts compatible across versions (no reordering; gaps in base
  contracts)? Who can upgrade, behind what delay?

### B6. Price and oracle reads

- Any price used for collateral, liquidation or minting: what does it cost to
  move it for one block, and what can be extracted by moving it? Thin HIP-3
  or spot markets read through precompiles are cheap to move.
