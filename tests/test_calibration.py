import copy
import datetime as dt
import json
import math
import statistics
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from hyperliquid_security.calibration import (
    budget_threshold,
    calibrate_mark_moves,
    cross_sectional,
    episode_counter,
    episodes,
    quantile,
)
from hyperliquid_security.hyperliquid_api import InfoClient
from hyperliquid_security.knowledge_base import KnowledgeBase
from hyperliquid_security.model import CalibrationResult, Threshold, ThresholdBasis
from hyperliquid_security.recording import (
    MeteredClient,
    RateLimiter,
    candle_moves_bps,
    record_pass,
)
from hyperliquid_security.validate import validate

series_strategy = st.dictionaries(
    st.sampled_from(["a", "b", "c"]),
    st.lists(st.integers(min_value=0, max_value=20).map(float), max_size=30),
    min_size=1,
)


def test_quantile_matches_inclusive_definition() -> None:
    data = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0]
    expected = statistics.quantiles(data, n=10, method="inclusive")
    assert [round(quantile(data, k / 10), 9) for k in range(1, 10)] == [
        round(v, 9) for v in expected
    ]
    with pytest.raises(ValueError):
        quantile([], 0.5)
    assert quantile([1.0, math.inf, math.inf], 0.9) == math.inf
    assert quantile([1.0, 2.0, math.inf], 0.5) == 2.0


@given(series_strategy, st.integers(min_value=0, max_value=21).map(float))
def test_episode_counter_equals_brute_force(series: dict[str, list[float]], t: float) -> None:
    assert episode_counter(series)(t) == sum(episodes(s, t) for s in series.values())


@given(series_strategy, st.integers(min_value=1, max_value=6))
def test_budget_threshold_is_lowest_stable_threshold(
    series: dict[str, list[float]], allowed: int
) -> None:
    count = episode_counter(series)
    threshold, used = budget_threshold(series, allowed)
    candidates = sorted({v for s in series.values() for v in s})
    if not candidates:
        return
    assert used == count(threshold) <= allowed
    assert all(count(c) <= allowed for c in candidates if c >= threshold)
    lower = [c for c in candidates if c < threshold]
    if lower:
        assert count(lower[-1]) > allowed


def test_episodes_are_not_monotone_in_threshold() -> None:
    # Lowering the threshold can merge runs: the reason for the descending scan.
    assert episodes([5.0, 3.0, 5.0], 5.0) == 2
    assert episodes([5.0, 3.0, 5.0], 3.0) == 1


def test_candle_moves_skip_gaps() -> None:
    step = 300_000
    candles = [
        {"t": 0, "T": step - 1, "c": "100"},
        {"t": step, "T": 2 * step - 1, "c": "110"},
        {"t": 3 * step, "T": 4 * step - 1, "c": "50"},  # one candle missing before this
    ]
    assert candle_moves_bps(candles) == [pytest.approx(1000.0)]


def test_rate_limiter_waits_for_the_window() -> None:
    now = [0.0]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(10, clock=lambda: now[0], sleep=sleep)
    limiter.acquire(6)
    limiter.acquire(4)
    limiter.acquire(5)  # would exceed 10 within the minute
    assert slept and now[0] >= 60.0


def test_record_pass_rows(repo_kb: KnowledgeBase) -> None:
    def api(payload: dict[str, Any]) -> Any:
        kind = payload["type"]
        if kind == "perpDexs":
            return [None, {"name": "dx", "assetToStreamingOiCap": [["dx:AAA", "5000000.0"]]}]
        if kind == "metaAndAssetCtxs":
            name = "dx:AAA" if payload.get("dex") == "dx" else "BBB"
            return [
                {
                    "universe": [
                        {"name": name, "maxLeverage": 5},
                        {"name": "OLD", "isDelisted": True},
                    ]
                },
                [
                    {"markPx": "10", "oraclePx": "10", "openInterest": "100", "dayNtlVlm": "1"},
                    {"markPx": "1", "oraclePx": "1", "openInterest": "0"},
                ],
            ]
        if kind == "l2Book":
            return {"levels": [[{"px": "9.9", "sz": "10"}], [{"px": "10.1", "sz": "10"}]]}
        raise AssertionError(payload)

    client = MeteredClient(InfoClient(transport=api), RateLimiter(10_000))
    rows = list(record_pass(client, now=lambda: dt.datetime(2026, 10, 13, tzinfo=dt.UTC)))
    assert [(r["coin"], r["surface"], r["oi_cap_usd"]) for r in rows] == [
        ("BBB", "core_perps", None),
        ("dx:AAA", "hip3_perps", 5_000_000.0),
    ]
    assert rows[0]["open_interest_usd"] == 1000.0
    assert rows[0]["bid_depth_usd_2pct"] == pytest.approx(99.0)


def test_cross_sectional_uses_the_rules_own_ratio(repo_kb: KnowledgeBase) -> None:
    rows = []
    for coin, oi in (("A", 10.0), ("B", 20.0), ("C", 30.0), ("D", 40.0)):
        for _ in range(3):
            rows.append(
                {
                    "coin": coin,
                    "surface": "core_perps",
                    "open_interest_usd": oi,
                    "bid_depth_usd_2pct": 1.0,
                    "ask_depth_usd_2pct": 2.0,
                }
            )
    rows.append(
        {
            "coin": "E",
            "surface": "core_perps",
            "open_interest_usd": 99.0,
            "bid_depth_usd_2pct": None,
            "ask_depth_usd_2pct": 1.0,
        }
    )
    # No depth inside the band: an infinite ratio ranks as the most exposed market.
    rows.append(
        {
            "coin": "F",
            "surface": "core_perps",
            "open_interest_usd": 5.0,
            "bid_depth_usd_2pct": 0.0,
            "ask_depth_usd_2pct": 0.0,
        }
    )
    result = cross_sectional(
        repo_kb, "open_interest_exceeds_depth", "oi_to_thinner_side_depth", rows, "core_perps", 0.5
    )
    assert result["markets"] == 5  # E had no measurable depth; F is infinitely thin
    assert result["value"] == 30.0
    assert [m["market"] for m in result["above_threshold"]] == ["F", "D", "C"]


def test_mark_move_calibration_checks_anchors(tmp_path: Path) -> None:
    moves = {f"M{i}": [10.0] * 200 + [float(100 * i)] + [10.0] * 200 for i in range(1, 6)}
    data = {
        "interval": "5m",
        "markets": {
            coin: {"surface": "core_perps", "first": 0, "last": 86_400_000, "moves_bps": m}
            for coin, m in moves.items()
        },
    }
    data["markets"]["H1"] = {
        "surface": "hip3_perps",
        "first": 0,
        "last": 86_400_000,
        "moves_bps": [5.0, 900.0, 5.0],
    }
    path = tmp_path / "candles.json"
    path.write_text(json.dumps(data))
    anchors = {
        "big": {"surface": "core_perps", "basis": "test", "moves_bps": [2000.0]},
        "small": {"surface": "core_perps", "basis": "test", "moves_bps": [50.0]},
    }
    result = calibrate_mark_moves(path, dt.date(2026, 10, 13), anchors)
    core = result["results"]["core_perps"]
    assert core["episodes_allowed"] == 1 and core["value"] == 500.0
    assert [c["outcome"].split()[0] for c in result["checks"]] == ["fires", "does"]


def _with_calibration(kb: KnowledgeBase, value_in_rule: float, value_in_result: float) -> list[str]:
    mutated = copy.copy(kb)
    rule = kb.rules["oi_cap_exceeds_depth"]
    threshold = Threshold(
        value=value_in_rule, unit="ratio", basis=ThresholdBasis.calibrated, calibration="test_cal"
    )
    mutated.rules = {
        **kb.rules,
        rule.id: rule.model_copy(update={"thresholds": {"max_cap_to_depth": threshold}}),
    }
    mutated.calibrations = {
        **kb.calibrations,
        "test_cal": CalibrationResult(
            id="test_cal",
            computed=dt.date(2026, 10, 13),
            method="m",
            data="d",
            targets=[
                {
                    "rule": rule.id,
                    "threshold": "max_cap_to_depth",
                    "surface": "hip3_perps",
                    "applies_as": "rule_default",
                    "value": value_in_result,
                }
            ],
        ),
    }
    return [p.message for p in validate(mutated) if p.level == "error"]


def test_calibrated_threshold_must_match_its_result(repo_kb: KnowledgeBase) -> None:
    # Only the test calibration's own consistency matters here; the real result for
    # this rule now has a target the mutated rule no longer cites.
    assert not [e for e in _with_calibration(repo_kb, 144.0, 144.0) if "test_cal" in e]
    assert any(
        "computed 150.0" in e and "test_cal" in e for e in _with_calibration(repo_kb, 144.0, 150.0)
    )


def test_calibrated_basis_requires_a_result_id() -> None:
    with pytest.raises(ValueError, match="names its calibration"):
        Threshold(value=1.0, unit="ratio", basis=ThresholdBasis.calibrated)
    with pytest.raises(ValueError, match="names its calibration"):
        Threshold(value=1.0, unit="ratio", basis=ThresholdBasis.placeholder, calibration="x")


def _tardis_book(
    path: Path, snapshots: list[tuple[int, list[tuple[float, float]], list[tuple[float, float]]]]
) -> None:
    header = ["exchange", "symbol", "timestamp", "local_timestamp"]
    for i in range(25):
        header += [f"asks[{i}].price", f"asks[{i}].amount", f"bids[{i}].price", f"bids[{i}].amount"]
    lines = [",".join(header)]
    for ts, bids, asks in snapshots:
        cells = ["hyperliquid", "X", str(ts), str(ts)]
        for i in range(25):
            ask = asks[i] if i < len(asks) else ("", "")
            bid = bids[i] if i < len(bids) else ("", "")
            cells += [str(ask[0]), str(ask[1]), str(bid[0]), str(bid[1])]
        lines.append(",".join(cells))
    path.write_text("\n".join(lines) + "\n")


def test_archive_upper_bounds(repo_kb: KnowledgeBase, tmp_path: Path) -> None:
    from hyperliquid_security.calibration import archive_upper_bounds

    minute = 60_000_000
    _tardis_book(
        tmp_path / "book.csv",
        [
            # All levels inside 2%: thinner side 99.5*1 + 99.0*1 = 198.5 -> bound 1000/198.5.
            (minute, [(99.5, 1.0), (99.0, 1.0)], [(100.5, 2.0), (101.0, 2.0)]),
            # A bid level beyond 2%: the sum is no lower bound of in-band depth; skipped.
            (2 * minute, [(99.5, 1.0), (97.0, 1.0)], [(100.5, 2.0)]),
        ],
    )
    (tmp_path / "ticker.csv").write_text(
        "exchange,symbol,timestamp,local_timestamp,funding_timestamp,funding_rate,"
        "predicted_funding_rate,open_interest,last_price,index_price,mark_price\n"
        f"hyperliquid,X,{minute + 5},{minute + 5},,0,,10,,100,100\n"
        f"hyperliquid,X,{2 * minute + 5},{2 * minute + 5},,0,,10,,100,100\n"
    )
    bound = archive_upper_bounds(repo_kb, tmp_path / "book.csv", tmp_path / "ticker.csv")
    assert bound["snapshots"] == 2
    assert bound["bounded_snapshots"] == 1
    assert bound["upper_bound_median"] == round(1000 / 198.5, 1)


def test_committed_calibrations_reproduce_from_committed_data(repo_kb: KnowledgeBase) -> None:
    """Every committed calibrated value follows from the committed recordings.

    Changing a rule's report expression, or the data, without recalibrating
    fails here. (Archive checks need third-party files and are not re-run.)
    """
    from hyperliquid_security.calibration import calibrate_cross_sections, load_passes
    from tests.conftest import KNOWLEDGE

    data = KNOWLEDGE / "calibration" / "data"
    computed = dt.date(2026, 10, 13)
    fresh = calibrate_cross_sections(
        repo_kb, load_passes(data / "passes_2026-10-13.jsonl.gz"), computed
    )
    fresh.append(calibrate_mark_moves(data / "candles_5m_2026-10-13.json.gz", computed))
    for result in fresh:
        committed = repo_kb.calibrations[result["id"]]
        assert [t.model_dump() for t in committed.targets] == result["targets"], result["id"]


def pass_row(coin: str, minute: int, open_interest_usd: float, mark: float) -> dict[str, Any]:
    return {
        "observed_at": (
            dt.datetime(2026, 10, 13, 6, 0, tzinfo=dt.UTC) + dt.timedelta(minutes=minute)
        ).isoformat(),
        "dex": None,
        "coin": coin,
        "surface": "core_perps",
        "mark_price": mark,
        "open_interest_usd": open_interest_usd,
        "bid_depth_usd_2pct": 1.0e6,
        "ask_depth_usd_2pct": 1.0e6,
    }


def test_growth_samples_count_positions_not_price() -> None:
    from hyperliquid_security.calibration import open_interest_growth_samples

    rows = [
        pass_row("A", 0, 1.0e6, 1.0),
        pass_row("A", 30, 1.5e6, 1.5),  # 30 minutes apart: outside the window
        pass_row("A", 60, 2.0e6, 2.0),  # same coins, price doubled
        pass_row("B", 0, 1.0e6, 1.0),
        pass_row("B", 61, 3.0e6, 1.0),  # two million new coins
    ]
    samples = open_interest_growth_samples(rows, {"core": 33.0e6})
    changes = {market: v["market.open_interest_change_usd_1h"] for _, market, v in samples}
    assert changes == {"A": 0.0, "B": 2.0e6}
    assert all(v["backstop.liquidator_account_value_usd"] == 33.0e6 for _, _, v in samples)


def test_growth_rule_base_rate_matches_its_notes(repo_kb: KnowledgeBase) -> None:
    """The base rate quoted in the rule's threshold note follows from committed data."""
    from hyperliquid_security.calibration import (
        base_rate,
        load_passes,
        open_interest_growth_samples,
    )
    from tests.conftest import KNOWLEDGE

    data = KNOWLEDGE / "calibration" / "data"
    rows = load_passes(data / "passes_2026-10-13.jsonl.gz")
    capital = json.loads((data / "backstop_capital_2026-10-13.json").read_text())
    rule_id = "open_interest_growth_exceeds_depth"
    rates = base_rate(
        repo_kb, rule_id, open_interest_growth_samples(rows, capital["account_value_usd"])
    )
    core, hip3 = rates["core_perps"], rates["hip3_perps"]
    assert core["firing"] == ["GRASS", "PONS", "TIA"]
    assert len(hip3["firing"]) == 5
    assert core["unknown"] == hip3["unknown"] == 0

    # An empty backstop makes the capital condition hold for any growth, leaving depth alone.
    depth_only = base_rate(repo_kb, rule_id, open_interest_growth_samples(rows, {"core": 0.0}))[
        "core_perps"
    ]
    assert len(depth_only["firing"]) == 6
    assert "PURR" in depth_only["firing"]

    note = repo_kb.rules[rule_id].thresholds["max_growth_to_depth"].note
    assert f"3 of {core['markets']} validator-operated markets (GRASS, PONS, TIA)" in note
    assert f"5 of {hip3['markets']} HIP-3 markets" in note
    assert "6\nvalidator-operated" in note or "6 validator-operated" in note
