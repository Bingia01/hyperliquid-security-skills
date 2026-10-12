# Surface checklists

Questions to answer from evidence before writing the attack movie. An
unanswerable question becomes an `open_questions` entry, not a guess.

## HyperCore markets (control owner `hypercore`)

- Which price moved first: external venues (oracle inputs), Hyperliquid's book
  (part of mark), or both? The oracle for validator-operated perps is a
  stake-weighted median of validators' weighted medians of external spot
  prices; mark is the median of oracle-plus-basis, Hyperliquid's book, and
  external perp mids.
- Was the position liquidated on the book, or taken over by the backstop?
  Backstop takeover happens when equity falls below two thirds of maintenance
  margin. Since March 2025 the liquidator vaults are capped; losses beyond
  their capacity trigger auto-deleveraging of profitable traders.
- Who bore the loss: HLP depositors, auto-deleveraged traders, the Foundation
  (compensation), or the attacker? Peak unrealized or realized?
- Did one actor control several accounts? Same side (sharding) or opposite
  sides (self-opposed positions)? What links them - funding source, timing?
- Was there a discretionary intervention (delisting, settlement price,
  compensation)? Under which published rule, if any? Current docs settle a
  delisted market at the one-hour time-weighted oracle price before the vote.
- Did an exit path change the economics: margin withdrawal before liquidation?
  (Transfers now require max(initial margin, 10% of position value).)
- Hyperps: the oracle is an average of the market's own mark, so there is no
  external anchor; a book push moves both.

## Market deployers (HIP-3 perps, HIP-4 outcomes)

- Who can set the oracle and mark: deployer, `oracleUpdater`, sub-deployers
  with `setOracle` (`perpDexs`)? Who can halt (`haltTrading` settles every
  position at mark)?
- What does the oracle consume, and does it reject outliers or check other
  venues? (xyz:SKHYNIX: one erroneous one-share print fed the oracle.)
- What is the dex's open interest cap relative to depth, and its total
  deposits relative to the deployer's slashable stake?
- Did any price-setting address hold a position?
- HIP-4: who submitted the settlement fraction, from what source, and did the
  submitter hold outcome tokens?

## Account holders

- How was signing authority obtained: key leak, phishing approval, malicious
  API (agent) wallet, compromised device? If unknown, say unknown.
- What left, to where, how fast? Were the destinations new? Bridged where?
- Were other accounts sharing the key or seed exposed?

## HyperEVM applications

- Which contract, which function, which role? Is there verified source?
- Did the app hold assets, or act through allowances/operator rights users
  granted it?
- Could callers choose call targets or calldata? Were targets allowlisted but
  calldata free?
- Did the app use CoreWriter or read precompiles, and did it assume an action
  completed in the same transaction?
- Admin keys: single key, multisig, timelock? Was a privileged power used
  (insider or stolen key)?

## Infrastructure

- Was on-chain state affected, or only access (API, front end, RPC)?
- Could users cancel, close and withdraw during the event?
- Was there compensation, and under what rule?
