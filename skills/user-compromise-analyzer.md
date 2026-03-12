# Skill — User Compromise Analyzer

## Purpose

Investigate Bucket C incidents — private key compromise, operator misuse, and abnormal account behavior. This skill evaluates 5 behavioral signals against an account's historical baseline to determine compromise likelihood and produce a containment checklist.

## Reference documents

- `docs/architecture/hyperliquid_attack_taxonomy.md` — User Accounts surface (Private Keys, Account Permissions, Bridge-Out Behavior)
- `docs/research/ATTACK_PRIMITIVES.md` — operational primitives (`wallet_behavioral_break`, `bridge_out_after_compromise`)
- `docs/analysis/INVARIANTS_AND_BREAKERS.md` — Invariant 6 (User-signing control)
- Related heuristic ID: `account_behavioral_break`

## Inputs

- Account transaction history: transfers, trades, bridge activity, operator delegations
- Bridge activity: destinations, frequency, asset types, amounts
- Transfer destinations: new vs previously-used addresses
- Timing: time-of-day patterns, activity burst analysis
- Optional: incident classifier output with `primary_bucket: C`

## Qualify before proceeding

Liquidation is not compromise. A user being liquidated — even if they consider it unfair — does not indicate stolen signing authority. Require at least 2 of the following 5 signals to escalate beyond informational:

1. New destinations that the account has never transferred to before
2. Sudden bridge-out activity exceeding the account's historical bridge frequency
3. Rapid liquidation combined with immediate withdrawal of remaining collateral
4. Unusual multi-asset sweep (moving all assets within a short window)
5. Signer profile break (new signing key, changed permissions, unfamiliar gas patterns)

If fewer than 2 signals are present, the behavior may be normal account management. State that assessment.

## Procedure

### Signal 1: New destinations

Compare current transfer destinations against the account's historical destination set.

**Metric:** `account.new_destinations_count_24h`

**Define "abnormal":** 3 or more new destinations in 24 hours that the account has never interacted with, especially if the destinations themselves are new or low-activity wallets.

**False positives:** User setting up new wallets for legitimate portfolio reorganization. User moving to a new CEX deposit address. Distinguisher: legitimate reorganization usually involves 1-2 new destinations, not 3+, and the destinations typically have prior activity.

### Signal 2: Sudden bridge-out

Check for a spike in bridge-out activity relative to the account's baseline.

**Metric:** `account.bridge_count_24h`

**Define "abnormal":** 2 or more bridge-out transactions in 24 hours when the account's 30-day average is less than 1 per week. Especially concerning if bridge-outs go to different chains.

**False positives:** User moving funds to a different chain for yield farming. Distinguisher: legitimate bridge-outs typically go to 1 destination on 1 chain, not multiple destinations across chains.

### Signal 3: Rapid liquidation plus withdrawal

Check whether the account experienced a liquidation event followed by immediate withdrawal of remaining collateral.

**Metric:** Time between liquidation event and withdrawal of remaining funds.

**Define "abnormal":** Withdrawal within 30 minutes of a liquidation event, clearing the account to near-zero balance. This pattern suggests the attacker opened a position to trigger liquidation (destroying evidence of the original balance) then swept the remainder.

**False positives:** Frustrated user closing their account after a bad liquidation. Distinguisher: legitimate users typically leave some balance or return later; compromise cases go to zero across all assets.

### Signal 4: Multi-asset sweep

Check whether multiple assets were moved within a short window.

**Metric:** `account.asset_mix_shift_score`

**Define "abnormal":** All or nearly all assets transferred out within a 1-hour window, especially if different assets go to different destinations. Normal users rarely move everything at once.

**False positives:** User migrating to a new wallet. Distinguisher: migration typically sends all assets to one new address; compromise distributes across multiple.

### Signal 5: Signer profile break

Check for changes to the account's signing behavior — new signing key, changed operator permissions, unfamiliar transaction patterns.

**Metric:** `account.transfer_urgency_score`, signing key analysis (if available)

**Define "abnormal":** Transactions signed by a key not previously associated with the account, or operator permissions changed immediately before fund movement.

**False positives:** User rotating keys for security. Distinguisher: key rotation is typically followed by normal activity from the new key, not immediate sweep behavior.

## Output format

```yaml
compromise_assessment:
  compromise_likelihood: <none | low | medium | high>
  signals_triggered: <count out of 5>
  signals:
    - signal_name: <name>
      triggered: <true | false>
      evidence: <specific data>
      confidence: <high | medium | low>
  affected_assets:
    - asset: <name>
      amount: <value>
      destination: <address or unknown>
  spread_pattern: <single_destination | multi_destination | multi_chain | unknown>
  timeline:
    - event: <description>
      timestamp: <time>
  containment_checklist:
    - <action item>
```

**Containment checklist items** (include all that apply):
- Revoke operator permissions if any are active
- Flag destination addresses for monitoring
- Check if the same signing key is used on other accounts
- Alert bridge operators if funds are in transit
- Preserve transaction logs for forensic analysis

## Worked example reference

- **Private key compromise case** — Signals 1, 2, 4 triggered. 5 new destinations in 12 hours (signal 1). 3 bridge-outs in 6 hours vs baseline of 0.2/week (signal 2). All USDC, ETH, and HYPE swept within 45 minutes (signal 4). Compromise likelihood: high. Spread pattern: multi-chain (Arbitrum + Ethereum mainnet).

## Relationship to other skills

- **Upstream:** `incident-classifier` with Bucket C classification.
- **Downstream:** Results may inform `governance-override-analyzer` if the compromise is large enough to trigger system-level response. Primitives feed into `primitive-extractor` for pattern cataloging.
- **Related:** `market-manipulation-analyzer` — some compromise cases involve market manipulation as the extraction method (e.g., opening a losing position against the attacker's other account).

## Anti-patterns

- Do not confuse liquidation with compromise. A user losing money through normal market mechanics is not a security incident.
- Do not treat a single signal as conclusive. Require 2+ signals for medium confidence, 3+ for high.
- Do not assume all unusual behavior is malicious. Users have legitimate reasons for changing behavior — the analysis must consider benign explanations.
- Do not skip the baseline comparison. "3 new destinations" is meaningless without knowing the account's normal pattern.

## Limitations

- Behavioral baseline requires sufficient account history. New accounts have no baseline to compare against.
- Signing key analysis depends on data availability — not all signing metadata may be accessible.
- This skill identifies behavioral anomalies, not root cause. It cannot determine how the key was compromised (phishing, malware, social engineering, insider).
- False negative risk: sophisticated attackers who study the account's behavior before acting may mimic normal patterns.
