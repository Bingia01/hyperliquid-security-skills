import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from hyperliquid_security.expressions import (
    BOOL,
    UNKNOWN,
    ExpressionError,
    Kind,
    Type,
    check,
    evaluate,
    kleene_and,
    kleene_not,
    kleene_or,
    number,
    parse,
)
from hyperliquid_security.units import DIMENSIONLESS, Unit, UnitError

USD = Unit.parse("usd")
BPS = Unit.parse("bps")
TYPES = {
    "market.oi": number(USD),
    "market.depth": number(USD),
    "market.mark": number(USD),
    "market.oracle": number(USD),
    "market.spread": number(BPS),
    "market.halted": BOOL,
    "market.kind": Type(Kind.STRING, values=frozenset({"core", "hip3"})),
    "market.flags": Type(Kind.LIST, element=BOOL),
    "threshold.max_ratio": number(DIMENSIONLESS),
    "threshold.max_bps": number(BPS),
}


def typed(source: str) -> Type:
    return check(parse(source), TYPES.get)


def run(source: str, values: dict[str, object]) -> object:
    return evaluate(parse(source), lambda name: values.get(name, UNKNOWN))  # type: ignore[arg-type,return-value]


class TestParsing:
    @pytest.mark.parametrize(
        "source",
        [
            "__import__('os').system('true')",
            "market.oi.__class__",
            "lambda: 1",
            "[x for x in market.flags]",
            "market.oi if true else market.depth",
            "open('/etc/passwd')",
            "market.oi(1)",
            "max(market.oi, key=market.depth)",
            "oi > 1",
            "market.oi[0]",
            "b'bytes' == b'bytes'",
        ],
    )
    def test_rejects_unsafe_or_unsupported_syntax(self, source: str) -> None:
        with pytest.raises(ExpressionError):
            parse(source)

    def test_collects_namespaced_references(self) -> None:
        expression = parse("market.oi / market.depth >= threshold.max_ratio and not market.halted")
        assert expression.references == {
            "market.oi",
            "market.depth",
            "threshold.max_ratio",
            "market.halted",
        }


class TestTypeChecking:
    def test_ratio_of_like_units_is_dimensionless(self) -> None:
        assert typed("market.oi / market.depth >= threshold.max_ratio") == BOOL

    def test_rejects_ratio_compared_to_bps(self) -> None:
        with pytest.raises(ExpressionError, match="unit mismatch"):
            typed("market.oi / market.depth >= threshold.max_bps")

    def test_bps_diff_produces_bps(self) -> None:
        assert typed("bps_diff(market.mark, market.oracle) >= threshold.max_bps") == BOOL

    def test_to_bps_requires_ratio(self) -> None:
        assert typed("to_bps(market.oi / market.depth) > market.spread") == BOOL
        with pytest.raises(ExpressionError):
            typed("to_bps(market.oi) > market.spread")

    def test_rejects_adding_usd_and_bps(self) -> None:
        with pytest.raises(ExpressionError, match="unit mismatch"):
            typed("market.oi + market.spread > 0")

    def test_zero_literal_matches_any_unit(self) -> None:
        assert typed("market.oi > 0") == BOOL

    def test_nonzero_literal_is_dimensionless(self) -> None:
        with pytest.raises(ExpressionError, match="unit mismatch"):
            typed("market.oi > 5")

    def test_rejects_unknown_reference(self) -> None:
        with pytest.raises(ExpressionError, match="unknown reference"):
            typed("market.missing > 0")

    def test_rejects_value_outside_vocabulary(self) -> None:
        with pytest.raises(ExpressionError, match="not an allowed value"):
            typed("market.kind == 'core_perp'")
        with pytest.raises(ExpressionError, match="not an allowed value"):
            typed("market.kind in ['hip3', 'hip4']")
        assert typed("market.kind in ['hip3']") == BOOL

    def test_rejects_boolean_arithmetic(self) -> None:
        with pytest.raises(ExpressionError):
            typed("market.halted + 1 > 0")

    def test_count_true_returns_count(self) -> None:
        with pytest.raises(ExpressionError, match="unit mismatch"):
            typed("count_true(market.flags) >= threshold.max_ratio")


class TestEvaluation:
    def test_missing_value_is_unknown_not_false(self) -> None:
        assert run("market.oi / market.depth >= 2", {"market.oi": 10.0}) is UNKNOWN

    def test_kleene_or_true_dominates_unknown(self) -> None:
        assert run("market.halted or market.oi > 0", {"market.oi": 1.0}) is True

    def test_kleene_and_false_dominates_unknown(self) -> None:
        assert run("market.halted and market.oi > 0", {"market.oi": 0.0}) is False

    def test_division_by_zero_depth_is_infinite(self) -> None:
        assert run("market.oi / market.depth", {"market.oi": 5.0, "market.depth": 0.0}) == math.inf
        assert run("market.oi / market.depth", {"market.oi": 0.0, "market.depth": 0.0}) is UNKNOWN

    def test_nan_is_unknown(self) -> None:
        assert run("market.oi > 0", {"market.oi": math.nan}) is UNKNOWN

    def test_bps_diff(self) -> None:
        assert run(
            "bps_diff(market.mark, market.oracle)", {"market.mark": 0.51, "market.oracle": 0.47}
        ) == pytest.approx(851.0638, rel=1e-6)

    def test_in_and_difference(self) -> None:
        values = {"market.a": ["x", "y", "z"], "market.b": ["y"]}
        assert run("size(difference(market.a, market.b)) == 2", values) is True
        assert run("'x' in market.a", values) is True

    def test_chained_comparison(self) -> None:
        assert run("0 < market.oi < market.depth", {"market.oi": 1.0, "market.depth": 2.0}) is True


@given(st.lists(st.sampled_from([True, False, UNKNOWN]), min_size=1, max_size=5))
def test_kleene_laws(values: list[object]) -> None:
    conj, disj = kleene_and(values), kleene_or(values)  # type: ignore[arg-type]
    # De Morgan holds in Kleene logic.
    assert kleene_not(conj) == kleene_or([kleene_not(v) for v in values])  # type: ignore[arg-type]
    assert kleene_not(disj) == kleene_and([kleene_not(v) for v in values])  # type: ignore[arg-type]
    # Without unknowns, Kleene logic is classical logic.
    if UNKNOWN not in values:
        assert conj is all(values)
        assert disj is any(values)


class TestUnits:
    def test_parse_and_algebra(self) -> None:
        assert Unit.parse("usd") / Unit.parse("usd") == DIMENSIONLESS
        assert str(Unit.parse("usd/seconds")) == "usd/seconds"
        assert Unit.parse("usd") * Unit.parse("ratio") == Unit.parse("usd")

    @pytest.mark.parametrize("text", ["dollars", "usd/seconds/count", "usd**2"])
    def test_rejects_bad_units(self, text: str) -> None:
        with pytest.raises(UnitError):
            Unit.parse(text)
