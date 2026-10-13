import pytest

from hyperliquid_security.engine import CompileError, Outcome, compile_rule, evaluate_rule
from hyperliquid_security.knowledge_base import KnowledgeBase
from hyperliquid_security.model import Rule


def rule(kb: KnowledgeBase, rule_id: str, **changes: object) -> Rule:
    return kb.rules[rule_id].model_copy(update=changes)


def test_profile_overrides_threshold(repo_kb: KnowledgeBase) -> None:
    rule = repo_kb.rules["open_interest_exceeds_depth"]
    default_value = rule.thresholds["max_oi_to_depth"].value
    profile = repo_kb.profiles["hip3_perps"]
    profile_value = profile.overrides[rule.id]["max_oi_to_depth"]
    assert profile_value < default_value  # the HIP-3 profile is stricter
    between = (default_value + profile_value) / 2
    compiled = compile_rule(rule, repo_kb.features)
    values = {
        "market.open_interest_usd": between * 1.0e6,
        "market.bid_depth_usd_2pct": 1.0e6,
        "market.ask_depth_usd_2pct": 1.0e6,
    }
    default = evaluate_rule(compiled, values, "hip3_perps")
    tuned = evaluate_rule(compiled, values, "hip3_perps", profile)
    assert default.outcome is Outcome.silent  # below the rule's default
    assert tuned.outcome is Outcome.fires  # above the HIP-3 override
    assert tuned.thresholds == {"max_oi_to_depth": profile_value}
    assert tuned.profile == "hip3_perps"


def test_profile_for_another_surface_is_rejected(repo_kb: KnowledgeBase) -> None:
    compiled = compile_rule(repo_kb.rules["open_interest_exceeds_depth"], repo_kb.features)
    with pytest.raises(ValueError, match="is for hip3_perps"):
        evaluate_rule(compiled, {}, "core_perps", repo_kb.profiles["hip3_perps"])


def test_missing_inputs_are_listed(repo_kb: KnowledgeBase) -> None:
    compiled = compile_rule(repo_kb.rules["open_interest_exceeds_depth"], repo_kb.features)
    result = evaluate_rule(compiled, {"market.open_interest_usd": 1.0}, "core_perps")
    assert result.outcome is Outcome.unknown
    assert result.missing == ["market.ask_depth_usd_2pct", "market.bid_depth_usd_2pct"]


def test_not_applicable_surface(repo_kb: KnowledgeBase) -> None:
    compiled = compile_rule(repo_kb.rules["mark_diverges_from_oracle"], repo_kb.features)
    result = evaluate_rule(
        compiled, {"market.mark_price": 2.0, "market.oracle_price": 1.0}, "hyperps"
    )
    assert result.outcome is Outcome.not_applicable


def test_infinite_ratio_is_reported_as_text(repo_kb: KnowledgeBase) -> None:
    compiled = compile_rule(repo_kb.rules["open_interest_exceeds_depth"], repo_kb.features)
    result = evaluate_rule(
        compiled,
        {
            "market.open_interest_usd": 1.0,
            "market.bid_depth_usd_2pct": 0.0,
            "market.ask_depth_usd_2pct": 1.0,
        },
        "core_perps",
    )
    assert result.outcome is Outcome.fires
    assert result.report["oi_to_thinner_side_depth"] == "inf"


def test_out_of_scope_feature_does_not_compile(repo_kb: KnowledgeBase) -> None:
    # A market-scoped rule may not read the vault-wide backstop totals without declaring them.
    bad = rule(
        repo_kb,
        "open_interest_exceeds_depth",
        condition=(
            "backstop.liquidator_account_value_usd / market.bid_depth_usd_2pct"
            " >= threshold.max_oi_to_depth"
        ),
    )
    with pytest.raises(CompileError, match="outside the rule's scope"):
        compile_rule(bad, repo_kb.features)


def test_wrong_vocabulary_does_not_compile(repo_kb: KnowledgeBase) -> None:
    bad = rule(repo_kb, "large_order_pulled_before_move", condition="order.removal == 'cancelled'")
    with pytest.raises(CompileError, match="not an allowed value"):
        compile_rule(bad, repo_kb.features)


def test_unit_mismatch_does_not_compile(repo_kb: KnowledgeBase) -> None:
    bad = rule(
        repo_kb,
        "mark_diverges_from_oracle",
        condition="market.mark_price / market.oracle_price >= threshold.max_mark_oracle_bps",
    )
    with pytest.raises(CompileError, match="unit mismatch"):
        compile_rule(bad, repo_kb.features)


def test_original_arbitrary_call_blind_spot_is_closed(repo_kb: KnowledgeBase) -> None:
    """The v1 rule did not fire on a permissionless execute(target, data) with no allowlist
    if the contract had a post-call check. The rewritten rule fires on it."""
    compiled = compile_rule(repo_kb.rules["caller_controlled_external_call"], repo_kb.features)
    values = {
        "contract.holds_or_spends_user_assets": True,
        "contract.call_target_control": "caller_supplied",
        "contract.call_data_control": "caller_supplied",
        "contract.call_entrypoint_access": "anyone",
        "contract.post_call_balance_check": True,
    }
    assert evaluate_rule(compiled, values, "hyperevm_apps").outcome is Outcome.fires


def test_original_permission_count_blind_spot_is_closed(repo_kb: KnowledgeBase) -> None:
    """The v1 rule needed two or more extra actions; one excess power to move funds is enough."""
    compiled = compile_rule(repo_kb.rules["privileged_role_exceeds_function"], repo_kb.features)
    values = {
        "role.can_move_user_assets": True,
        "role.function_requires_moving_assets": False,
        "role.can_upgrade": False,
        "role.function_requires_upgrade": False,
        "role.can_call_arbitrary_targets": False,
        "role.function_requires_arbitrary_calls": False,
        "role.signer": "multisig",
    }
    assert evaluate_rule(compiled, values, "hyperevm_apps").outcome is Outcome.fires
