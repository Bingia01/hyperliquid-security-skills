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
from hyperliquid_security.hyperliquid_api import HLP_PARENT, ApiError, InfoClient
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


def fake_market_api(payload: dict[str, Any]) -> Any:
    """Two markets (one validator-operated, one on HIP-3 dex "dx"), two backstops."""
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
    if kind == "vaultDetails":
        if payload["vaultAddress"] == HLP_PARENT:
            children = ["0x01", "0x02"]
            return {"relationship": {"type": "parent", "data": {"childAddresses": children}}}
        return {"name": "HLP Liquidator" if payload["vaultAddress"] == "0x01" else "HLP Strategy"}
    if kind == "clearinghouseState":
        value = "250.0" if payload.get("dex") == "dx" else "33000000.0"
        return {"marginSummary": {"accountValue": value}, "assetPositions": []}
    raise AssertionError(payload)


def test_record_pass_rows(repo_kb: KnowledgeBase) -> None:
    client = MeteredClient(InfoClient(transport=fake_market_api), RateLimiter(10_000))
    rows = list(record_pass(client, now=lambda: dt.datetime(2026, 10, 13, tzinfo=dt.UTC)))
    assert [(r["coin"], r["surface"], r["oi_cap_usd"]) for r in rows] == [
        ("BBB", "core_perps", None),
        ("dx:AAA", "hip3_perps", 5_000_000.0),
    ]
    assert rows[0]["open_interest_usd"] == 1000.0
    assert rows[0]["bid_depth_usd_2pct"] == pytest.approx(99.0)
    # Each market carries the capital of the backstop that would inherit its liquidations.
    assert [r["backstop_account_value_usd"] for r in rows] == [33_000_000.0, 250.0]


def test_unmeasured_backstop_is_absent_not_zero() -> None:
    def broken(payload: dict[str, Any]) -> Any:
        if payload["type"] == "clearinghouseState" and payload.get("dex") == "dx":
            raise ApiError("clearinghouseState failed: 503")
        return fake_market_api(payload)

    client = MeteredClient(InfoClient(transport=broken), RateLimiter(10_000))
    rows = list(record_pass(client))
    assert [r["backstop_account_value_usd"] for r in rows] == [33_000_000.0, None]


class FakeClock:
    def __init__(self) -> None:
        self.time = dt.datetime(2026, 10, 13, 12, 0, tzinfo=dt.UTC)

    def now(self) -> dt.datetime:
        self.time += dt.timedelta(seconds=30)  # each reading costs time, like a real pass
        return self.time

    def sleep(self, seconds: float) -> None:
        self.time += dt.timedelta(seconds=seconds)


def test_recording_session_resumes_and_packs(tmp_path: Path) -> None:
    import gzip

    from hyperliquid_security.calibration import load_passes
    from hyperliquid_security.recording import pack, record_session

    clock = FakeClock()
    client = MeteredClient(InfoClient(transport=fake_market_api), RateLimiter(10_000))
    session = tmp_path / "session"

    def run(stop_after_hours: float | None) -> bool:
        return record_session(
            client,
            session,
            hours=1.0,
            interval_seconds=600,
            stop_after_hours=stop_after_hours,
            now=clock.now,
            sleep=clock.sleep,
            log=lambda _: None,
        )

    assert run(stop_after_hours=0.3) is False  # stopped early; the session continues
    first = sorted(p.name for p in session.glob("pass-*.jsonl.gz"))
    assert len(first) == 2
    assert run(stop_after_hours=None) is True  # same command resumes and completes
    files = sorted(session.glob("pass-*.jsonl.gz"))
    assert [p.name for p in files[:2]] == first
    assert len(files) == 6  # one pass every 10 minutes for an hour
    assert not list(session.glob("*.partial"))

    packed = tmp_path / "passes.jsonl.gz"
    assert pack(session, packed) == 12
    rows = load_passes(packed)
    assert [r["pass"] for r in rows] == [n for n in range(1, 7) for _ in range(2)]
    with gzip.open(files[0], "rt") as handle:
        assert len(handle.read().splitlines()) == 2
    assert run(stop_after_hours=None) is True  # rerunning a finished session records nothing
    assert len(list(session.glob("pass-*.jsonl.gz"))) == 6


def test_recording_session_refuses_another_api(tmp_path: Path) -> None:
    from hyperliquid_security.recording import record_session

    clock = FakeClock()
    client = MeteredClient(InfoClient(transport=fake_market_api), RateLimiter(10_000))
    record_session(client, tmp_path, 0.1, 600, now=clock.now, sleep=clock.sleep, log=print)
    other = MeteredClient(
        InfoClient(base_url="https://api.hyperliquid-testnet.xyz/info", transport=fake_market_api),
        RateLimiter(10_000),
    )
    with pytest.raises(ValueError, match="hyperliquid-testnet"):
        record_session(other, tmp_path, 0.1, 600, now=clock.now, sleep=clock.sleep)


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


def pass_row(
    coin: str,
    minute: int,
    open_interest_usd: float,
    mark: float,
    depth: float = 1.0e6,
    surface: str = "core_perps",
) -> dict[str, Any]:
    start = dt.datetime(2026, 10, 13, 6, 0, tzinfo=dt.UTC)
    return {
        "observed_at": (start + dt.timedelta(minutes=minute)).isoformat(),
        "dex": "dx" if surface == "hip3_perps" else None,
        "coin": coin,
        "surface": surface,
        "pass": minute // 10 + 1,
        "mark_price": mark,
        "open_interest_usd": open_interest_usd,
        "bid_depth_usd_2pct": depth,
        "ask_depth_usd_2pct": depth,
    }


def test_growth_samples_count_positions_not_price() -> None:
    from hyperliquid_security.calibration import open_interest_growth_samples

    rows = [
        pass_row("A", 0, 1.0e6, 1.0),
        pass_row("A", 30, 1.5e6, 1.5),  # 30 minutes before the last pass: outside the window
        pass_row("A", 60, 2.0e6, 2.0),  # same coins, price doubled
        pass_row("B", 0, 1.0e6, 1.0),
        pass_row("B", 4, 1.0e6, 1.0),  # 61 and 57 minutes before: the nearer to 60 is used
        pass_row("B", 61, 3.0e6, 1.0),  # two million new coins
    ]
    samples = open_interest_growth_samples(rows)
    changes = {s.market: s.values["market.open_interest_change_usd_1h"] for s in samples}
    assert changes == {"A": 0.0, "B": 2.0e6}
    assert len(samples) == 2  # one sample per later pass, not one per pair


def test_growth_calibration_spends_the_budget_on_material_growth(repo_kb: KnowledgeBase) -> None:
    from hyperliquid_security.calibration import calibrate_open_interest_growth

    def build(coin: str, growth: float, depth: float, surface: str = "core_perps") -> list[Any]:
        return [
            pass_row(coin, 0, 10.0e6, 1.0, depth, surface),
            pass_row(coin, 60, 10.0e6 + growth, 1.0, depth, surface),
        ]

    rows = [
        *build("BIG", 900.0e3, 300.0e3),  # 3x depth, material
        *build("MID", 600.0e3, 300.0e3),  # 2x depth, material
        *build("DUST", 16.0e3, 286.0),  # 56x depth, below min_growth_usd
        *build("dx:CALM", 300.0e3, 1.0e6, "hip3_perps"),  # 0.3x depth
    ]
    result = calibrate_open_interest_growth(repo_kb, rows, dt.date(2026, 10, 13))
    core, hip3 = result["results"]["core_perps"], result["results"]["hip3_perps"]
    assert core["episodes_allowed"] == 1
    assert core["value"] == 3.0  # only BIG within a budget of one; DUST never counts
    assert core["windows_below_min_growth"] == 1
    assert [e["market"] for e in core["episodes_by_market"]] == ["BIG"]
    assert hip3["value"] == 1.0  # the budget allows lower; the definitional floor holds
    assert [t["value"] for t in result["targets"]] == [3.0, 1.0]
    CalibrationResult.model_validate(result)
