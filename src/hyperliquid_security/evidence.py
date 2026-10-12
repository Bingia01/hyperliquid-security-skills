"""Evidence tiers are derived from sources, never asserted.

Support for one claim:

* ``strong``   - at least one primary source, or technical write-ups from at
  least two distinct publishers;
* ``moderate`` - one technical write-up, or news reports from at least two
  distinct publishers;
* ``weak``     - anything less (a single news report, social posts).

An incident's tier is the weakest support among its *core* claims (the claims
that establish the mechanism). A chain of reasoning is only as strong as its
weakest link, so one well-sourced claim cannot lift an unsupported mechanism.

A rule's evidence status is derived from its anchor incidents:
``observed`` (a confirmed anchor), ``reported`` (a credible-report anchor) or
``theoretical`` (only research leads, or no anchors). Research leads can never
raise a rule's status, which is how "leads must not anchor strong rules" is
enforced mechanically rather than by convention.

Limitation: "distinct publishers" approximates independence. Two outlets
repeating one analytics firm's thread are not independent; record the firm
itself as the source where possible.
"""

from __future__ import annotations

from enum import Enum, StrEnum

from .model import Claim, Incident, Source, SourceTier


class Support(int, Enum):
    weak = 0
    moderate = 1
    strong = 2


class Tier(StrEnum):
    confirmed = "confirmed"
    credible_report = "credible_report"
    research_lead = "research_lead"


class RuleStatus(StrEnum):
    observed = "observed"
    reported = "reported"
    theoretical = "theoretical"


_TIER_OF_SUPPORT = {
    Support.strong: Tier.confirmed,
    Support.moderate: Tier.credible_report,
    Support.weak: Tier.research_lead,
}


def claim_support(claim: Claim, sources: dict[str, Source]) -> Support:
    cited = [sources[s] for s in claim.sources if s in sources]
    publishers = {
        tier: {s.publisher.strip().lower() for s in cited if s.tier is tier} for tier in SourceTier
    }
    if publishers[SourceTier.primary] or len(publishers[SourceTier.technical_secondary]) >= 2:
        return Support.strong
    if publishers[SourceTier.technical_secondary] or len(publishers[SourceTier.news]) >= 2:
        return Support.moderate
    return Support.weak


def incident_tier(incident: Incident) -> Tier:
    sources = {s.id: s for s in incident.sources}
    core = [c for c in incident.claims if c.core]
    if not core:
        return Tier.research_lead
    weakest = min(claim_support(c, sources) for c in core)
    return _TIER_OF_SUPPORT[weakest]


def rule_status(anchor_tiers: list[Tier]) -> RuleStatus:
    if Tier.confirmed in anchor_tiers:
        return RuleStatus.observed
    if Tier.credible_report in anchor_tiers:
        return RuleStatus.reported
    return RuleStatus.theoretical


def inferred_step_count(incident: Incident) -> int:
    return sum(1 for step in incident.movie if not step.claims)
