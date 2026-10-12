"""Each methodology rule is enforced: inject one defect, expect one specific error."""

import copy

from hyperliquid_security.knowledge_base import KnowledgeBase
from hyperliquid_security.model import (
    CodeDefect,
    Fixture,
    FixtureProvenance,
    Mode,
    Profile,
    Threshold,
    ThresholdBasis,
)
from hyperliquid_security.validate import validate


def errors_after(kb: KnowledgeBase, **replace: dict[str, object]) -> list[str]:
    mutated = copy.copy(kb)
    for attribute, records in replace.items():
        merged = dict(getattr(kb, attribute))
        merged.update(records)
        setattr(mutated, attribute, merged)
    return [p.message for p in validate(mutated) if p.level == "error"]


def test_alert_mode_needs_evidence_backed_anchor(repo_kb: KnowledgeBase) -> None:
    rule = repo_kb.rules["mark_diverges_from_oracle"].model_copy(update={"mode": Mode.alert})
    errors = errors_after(repo_kb, rules={rule.id: rule})
    assert any("needs an anchor incident at credible_report or better" in e for e in errors)
    assert any("synthetic fixtures test logic, not detection" in e for e in errors)


def test_research_leads_cannot_justify_alerts(repo_kb: KnowledgeBase) -> None:
    rule = repo_kb.rules["oracle_setter_holds_position"].model_copy(
        update={"mode": Mode.alert, "anchors": ["hl-2023-snx-lead"]}
    )
    errors = errors_after(repo_kb, rules={rule.id: rule})
    assert any("derived status is 'theoretical'" in e for e in errors)


def test_anchor_must_exhibit_detected_primitive(repo_kb: KnowledgeBase) -> None:
    rule = repo_kb.rules["account_sweep_to_new_destinations"].model_copy(
        update={"anchors": ["hl-2025-03-jelly"]}
    )
    errors = errors_after(repo_kb, rules={rule.id: rule})
    assert any("exhibits none of the detected primitives" in e for e in errors)


def test_numeric_literals_are_rejected(repo_kb: KnowledgeBase) -> None:
    rule = repo_kb.rules["mark_diverges_from_oracle"].model_copy(
        update={"condition": "bps_diff(market.mark_price, market.oracle_price) >= to_bps(0.015)"}
    )
    errors = errors_after(repo_kb, rules={rule.id: rule})
    assert any("numeric literal 0.015" in e for e in errors)
    assert any("thresholds declared but never used" in e for e in errors)


def test_fixture_expectation_mismatch_is_an_error(repo_kb: KnowledgeBase) -> None:
    original = repo_kb.rules["mark_diverges_from_oracle"]
    wrong = Fixture(
        name="claims to fire",
        expect="fires",
        provenance=FixtureProvenance.synthetic,
        surface="core_perps",
        values={"market.mark_price": 100.0, "market.oracle_price": 100.0},
    )
    rule = original.model_copy(update={"fixtures": [*original.fixtures, wrong]})
    errors = errors_after(repo_kb, rules={rule.id: rule})
    assert any("expected fires, got silent" in e for e in errors)


def test_fixture_value_types_are_checked(repo_kb: KnowledgeBase) -> None:
    original = repo_kb.rules["mark_diverges_from_oracle"]
    wrong = Fixture(
        name="string price",
        expect="fires",
        provenance=FixtureProvenance.synthetic,
        surface="core_perps",
        values={"market.mark_price": "0.51", "market.oracle_price": 0.47},
    )
    rule = original.model_copy(update={"fixtures": [*original.fixtures, wrong]})
    errors = errors_after(repo_kb, rules={rule.id: rule})
    assert any("expected a number" in e for e in errors)


def test_reconstructed_values_must_cite_claims(repo_kb: KnowledgeBase) -> None:
    original = repo_kb.rules["mark_jump_short_window"]
    fixtures = [
        f.model_copy(update={"evidence": {}})
        if f.provenance is FixtureProvenance.reconstructed
        else f
        for f in original.fixtures
    ]
    rule = original.model_copy(update={"fixtures": fixtures})
    errors = errors_after(repo_kb, rules={rule.id: rule})
    assert any("cites no incident claim" in e for e in errors)


def test_core_code_defect_needs_confirmed_evidence(repo_kb: KnowledgeBase) -> None:
    incident = repo_kb.incidents["hl-2025-11-popcat"].model_copy(
        update={"code_defect": CodeDefect.present}
    )
    errors = errors_after(repo_kb, incidents={incident.id: incident})
    assert any("core-protocol code defect on evidence below 'confirmed'" in e for e in errors)


def test_unknown_references_are_errors(repo_kb: KnowledgeBase) -> None:
    incident = repo_kb.incidents["hl-2025-11-popcat"].model_copy(
        update={"primitives": ["spoofing_wall_reversal"], "mechanisms": ["market_abuse"]}
    )
    errors = errors_after(repo_kb, incidents={incident.id: incident})
    assert any("unknown primitives: ['spoofing_wall_reversal']" in e for e in errors)
    assert any("unknown mechanisms: ['market_abuse']" in e for e in errors)


def test_profiles_must_name_real_thresholds(repo_kb: KnowledgeBase) -> None:
    profile = Profile(
        id="hip3_perps",
        surface="hip3_perps",
        description="bad",
        overrides={
            "open_interest_exceeds_depth": {"oi_to_visible_depth_warn": 4.0},
            "liquidator_loss_near_capacity": {"max_unrealized_loss_share": 0.3},
        },
    )
    errors = errors_after(repo_kb, profiles={profile.id: profile})
    assert any("no thresholds named ['oi_to_visible_depth_warn']" in e for e in errors)
    assert any("never runs on surface hip3_perps" in e for e in errors)


def test_threshold_units_must_match_condition(repo_kb: KnowledgeBase) -> None:
    original = repo_kb.rules["mark_diverges_from_oracle"]
    thresholds = {
        "max_mark_oracle_bps": Threshold(
            value=0.015, unit="ratio", basis=ThresholdBasis.placeholder
        )
    }
    rule = original.model_copy(update={"thresholds": thresholds})
    errors = errors_after(repo_kb, rules={rule.id: rule})
    assert any("unit mismatch" in e for e in errors)
