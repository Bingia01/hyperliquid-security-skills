# Invariants and breakers

This file defines the system invariants the open-source repo cares about. An invariant is a safety property the protocol or ecosystem is expected to preserve.

## 1. Liquidation absorbability
**Invariant:** forced unwinds should be executable without pushing unacceptable loss into HLP or another shared backstop.

**Breakers:**
- toxic_position_inheritance
- liquidation_depth_mismatch
- strategic_margin_withdrawal

**Representative incidents:** ETH margin drain, JELLY, POPCAT

## 2. Fair-price integrity
**Invariant:** mark or accounting price should remain reasonably anchored to a real and hard-to-manipulate reference.

**Breakers:**
- thin_market_mark_distortion
- cross_exchange_price_anchor_abuse
- spoof_wall_support

**Representative incidents:** SNX research lead, JELLY, POPCAT

## 3. Margin integrity
**Invariant:** collateral and liquidation thresholds should not be steerable into a profitable forced-unwind path.

**Breakers:**
- strategic_margin_withdrawal
- portfolio_offset_blind_spot

**Representative incidents:** ETH margin drain

## 4. Crisis-path consistency
**Invariant:** the system should have a predictable and precommitted response under stress.

**Breakers:**
- crisis_path_governance_override
- validator_put_dynamics
- trust-shock withdrawal runs

**Representative incidents:** JELLY, Lazarus-linked stress lead

## 5. Permission-bounded execution
**Invariant:** contracts and routers should only be able to do the minimum needed for their function.

**Breakers:**
- arbitrary_external_call
- operator_permission_scope_creep
- missing_post_call_invariant

**Representative incidents:** Hyperdrive

## 6. User-signing control
**Invariant:** only the legitimate user should be able to authorize transfers and account changes.

**Breakers:**
- stolen signing authority
- wallet behavioral break
- bridge-out after compromise

**Representative incidents:** key compromise

## 7. Ecosystem trust-boundary separation
**Invariant:** ecosystem application risk should not be silently mistaken for core protocol safety.

**Breakers:**
- ecosystem_trust_failure
- overbroad delegated custody
- shutdown-after-outflow pattern

**Representative incidents:** HyperVault research lead
