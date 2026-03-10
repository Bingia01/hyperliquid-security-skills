# Attack primitive library

This file defines reusable attack primitives extracted from Hyperliquid-class incidents.

## Pricing and market primitives
- **thin_market_mark_distortion** — a low-depth market can be moved enough to change mark-to-market outcomes.
- **cross_exchange_price_anchor_abuse** — attacker moves or influences an external price anchor used directly or indirectly by the venue.
- **weak_anchor_settlement** — the market has no strong external anchor, so settlement can be gamed near cutover points.
- **spoof_wall_support** — a large visible order creates false confidence and is later withdrawn.

## Risk-engine primitives
- **toxic_position_inheritance** — liquidation or transfer logic pushes already-dangerous exposure into HLP or another shared backstop.
- **liquidation_depth_mismatch** — the inherited or forced-close position is too large for executable depth.
- **strategic_margin_withdrawal** — a trader uses collateral withdrawal to steer a position into liquidation at favorable economics.
- **portfolio_offset_blind_spot** — cross-asset margin or offsets hide a real tail-risk concentration.

## Governance and crisis primitives
- **crisis_path_governance_override** — emergency intervention changes the normal rules of the market.
- **validator_put_dynamics** — users begin to price in rescue behavior and may game it.

## Operational primitives
- **wallet_behavioral_break** — a wallet suddenly behaves unlike its historical baseline.
- **bridge_out_after_compromise** — assets are swept and immediately bridged or dispersed.

## Smart-contract / app primitives
- **arbitrary_external_call** — a contract can call destinations too broadly.
- **operator_permission_scope_creep** — a router or operator is granted more power than needed.
- **missing_post_call_invariant** — no accounting or safety check is enforced after a privileged call.
- **ecosystem_trust_failure** — user funds depend on project-operator honesty rather than protocol safety.
