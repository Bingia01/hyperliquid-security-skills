import datetime as dt

from hyperliquid_security.evidence import (
    RuleStatus,
    Support,
    Tier,
    claim_support,
    incident_tier,
    rule_status,
)
from hyperliquid_security.model import Claim, Incident, Source


def source(sid: str, tier: str, publisher: str) -> Source:
    return Source(
        id=sid, title=sid, publisher=publisher, url=f"https://example.org/{sid}", tier=tier
    )


SOURCES = {
    s.id: s
    for s in [
        source("docs", "primary", "Hyperliquid Docs"),
        source("firm_a", "technical_secondary", "Firm A"),
        source("firm_a_again", "technical_secondary", "firm a "),
        source("firm_b", "technical_secondary", "Firm B"),
        source("news_a", "news", "Outlet A"),
        source("news_b", "news", "Outlet B"),
        source("post", "social", "Someone"),
    ]
}


def support(*ids: str) -> Support:
    return claim_support(Claim(id="c", statement="s", sources=list(ids)), SOURCES)


def test_claim_support_ladder() -> None:
    assert support("docs") is Support.strong
    assert support("firm_a", "firm_b") is Support.strong
    assert support("firm_a") is Support.moderate
    assert support("news_a", "news_b") is Support.moderate
    assert support("news_a") is Support.weak
    assert support("post", "news_a") is Support.weak


def test_same_publisher_counts_once() -> None:
    # Two write-ups from one firm are not independent corroboration.
    assert support("firm_a", "firm_a_again") is Support.moderate


def incident(claims: list[Claim]) -> Incident:
    return Incident(
        id="x",
        title="x",
        period={"start": dt.date(2025, 1, 1), "end": dt.date(2025, 1, 1)},
        summary="x",
        control_owner="hypercore",
        mechanisms=["code_defect"],
        code_defect="undetermined",
        surfaces=["core_perps"],
        sources=list(SOURCES.values()),
        claims=claims,
        movie=[{"phase": "trigger", "description": "x"}],
    )


def test_incident_tier_is_weakest_core_claim() -> None:
    strong = Claim(id="a", statement="s", sources=["docs"], core=True)
    weak = Claim(id="b", statement="s", sources=["news_a"], core=True)
    side = Claim(id="c", statement="s", sources=["post"], core=False)
    assert incident_tier(incident([strong, side])) is Tier.confirmed
    assert incident_tier(incident([strong, weak])) is Tier.research_lead


def test_incident_without_core_claims_is_a_lead() -> None:
    assert (
        incident_tier(incident([Claim(id="a", statement="s", sources=["docs"])]))
        is Tier.research_lead
    )


def test_rule_status_never_raised_by_leads() -> None:
    assert rule_status([Tier.research_lead, Tier.research_lead]) is RuleStatus.theoretical
    assert rule_status([Tier.research_lead, Tier.credible_report]) is RuleStatus.reported
    assert rule_status([Tier.credible_report, Tier.confirmed]) is RuleStatus.observed
    assert rule_status([]) is RuleStatus.theoretical
