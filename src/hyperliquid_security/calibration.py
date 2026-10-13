"""Calibrate rule thresholds on recorded data.

A calibrated threshold must say what it is calibrated *to*. Two targets are
supported, matching the two kinds of rule:

* **Cross-sectional rank** (precondition rules measuring structural exposure):
  take each market's median of the rule's own ratio over the recording, and
  set the threshold at a stated percentile across markets. "Fires" then means
  "this market is in the most exposed X% of markets", a statement that stays
  meaningful as markets change.
* **Alert budget** (active-attack rules): set the threshold to the smallest
  value whose number of alert *episodes* (consecutive exceedances in one
  market merged into one) stays within a stated budget per day across the
  whole surface. A pager tolerates a fixed number of interruptions, so the
  budget, not a percentile, is the right target.

The quantity calibrated is always the rule's own ``report`` expression,
evaluated by the rule engine on recorded values, so the calibration and the
rule cannot drift apart.

Results are written to ``knowledge/calibration/<id>.yaml``; a rule threshold
with basis ``calibrated`` must point at that file, and the validator checks
the values agree.
"""

from __future__ import annotations

import bisect
import csv
import datetime as dt
import gzip
import json
import math
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .engine import CompiledRule, Outcome, compile_rule, evaluate_rule
from .expressions import UNKNOWN, evaluate
from .hyperliquid_api import HISTORY_WINDOWS_SECONDS
from .knowledge_base import KnowledgeBase
from .validate import profile_for

PASS_FIELDS = {
    "open_interest_usd": "market.open_interest_usd",
    "mark_price": "market.mark_price",
    "oracle_price": "market.oracle_price",
    "bid_depth_usd_2pct": "market.bid_depth_usd_2pct",
    "ask_depth_usd_2pct": "market.ask_depth_usd_2pct",
    "oi_cap_usd": "market.oi_cap_usd",
}


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------


def quantile(values: Iterable[float], q: float) -> float:
    """Linear-interpolation quantile (the common "type 7" definition)."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile of an empty sample")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0, 1]")
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    fraction = position - low
    if fraction == 0 or ordered[low] == ordered[high]:
        return ordered[low]  # also avoids inf - inf when both neighbours are infinite
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def episodes(series: list[float], threshold: float) -> int:
    """Count runs of consecutive values at or above ``threshold``."""
    count, inside = 0, False
    for value in series:
        if value >= threshold and not inside:
            count += 1
        inside = value >= threshold
    return count


def episode_counter(series_by_market: Mapping[str, list[float]]) -> Any:
    """Return f(threshold) -> total episodes, in O(log n) per call.

    Window i starts an episode at threshold t exactly when
    previous_i < t <= value_i (previous of the first window is -inf). So the
    count is #{value_i >= t} - #{previous_i >= t} over windows that rise.
    """
    rises, previous = [], []
    for series in series_by_market.values():
        last = -math.inf
        for value in series:
            if value > last:
                rises.append(value)
                previous.append(last)
            last = value
    rises.sort()
    previous.sort()

    def count(threshold: float) -> int:
        above = len(rises) - bisect.bisect_left(rises, threshold)
        return above - (len(previous) - bisect.bisect_left(previous, threshold))

    return count


def budget_threshold(
    series_by_market: Mapping[str, list[float]], episodes_allowed: int
) -> tuple[float, int]:
    """Lowest threshold such that it, and every higher threshold, is within budget.

    Episode counts are not monotone in the threshold (lowering it can merge two
    runs into one), so the scan walks down from the largest observed value and
    stops at the first threshold over budget. Returns (threshold, episodes).
    """
    count = episode_counter(series_by_market)
    candidates = sorted({v for s in series_by_market.values() for v in s}, reverse=True)
    best: tuple[float, int] = (math.inf, 0)
    for threshold in candidates:
        used = count(threshold)
        if used > episodes_allowed:
            break
        best = (threshold, used)
    return best


# --------------------------------------------------------------------------
# Evaluating a rule's report expression on recorded rows
# --------------------------------------------------------------------------


def report_value(compiled: CompiledRule, name: str, values: Mapping[str, Any]) -> float | None:
    expression = compiled.report[name]

    def lookup(reference: str) -> Any:
        value = values.get(reference)
        return UNKNOWN if value is None else value

    result = evaluate(expression, lookup)
    if result is UNKNOWN or not isinstance(result, (int, float)) or math.isnan(result):
        return None
    return float(result)


def _open_text(path: Path) -> Any:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def load_passes(path: Path) -> list[dict[str, Any]]:
    rows = []
    with _open_text(path) as handle:
        for line in handle:
            row = json.loads(line)
            if "coin" in row:
                rows.append(row)
    return rows


def pass_values(row: Mapping[str, Any]) -> dict[str, Any]:
    return {feature: row.get(column) for column, feature in PASS_FIELDS.items()}


def open_interest_growth_samples(
    rows: list[dict[str, Any]], backstop_capital: Mapping[str, float]
) -> list[tuple[str, str, dict[str, Any]]]:
    """(surface, market, values) for every pair of passes of one market whose
    distance fits the open interest growth window: the values a snapshot taken
    at the later pass, with the earlier one as ``--previous``, would hold.

    Passes store open interest in USD and the mark, so coin units are recovered
    as their quotient. ``backstop_capital`` maps a dex name ("core" for
    validator-operated perps) to its backstop's account value.
    """
    low, high = HISTORY_WINDOWS_SECONDS["market.open_interest_change_usd_1h"]
    by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_market[row["coin"]].append(row)
    samples = []
    for market, series in sorted(by_market.items()):
        series.sort(key=lambda r: r["observed_at"])
        for i, earlier in enumerate(series):
            start = dt.datetime.fromisoformat(earlier["observed_at"])
            for later in series[i + 1 :]:
                age = (dt.datetime.fromisoformat(later["observed_at"]) - start).total_seconds()
                if not low <= age <= high or not earlier["mark_price"] or not later["mark_price"]:
                    continue
                before = earlier["open_interest_usd"] / earlier["mark_price"]
                after = later["open_interest_usd"] / later["mark_price"]
                values = pass_values(later)
                values["market.open_interest_change_usd_1h"] = (after - before) * later[
                    "mark_price"
                ]
                values["backstop.liquidator_account_value_usd"] = backstop_capital.get(
                    later["dex"] or "core"
                )
                samples.append((later["surface"], market, values))
    return samples


def base_rate(
    kb: KnowledgeBase, rule_id: str, samples: list[tuple[str, str, dict[str, Any]]]
) -> dict[str, dict[str, Any]]:
    """Per surface: how many samples the rule saw, fired on or could not decide, and
    which markets fired at least once - evaluated by the engine with the surface's
    profile, so the count is of the rule exactly as written."""
    compiled = compile_rule(kb.rules[rule_id], kb.features)
    out: dict[str, dict[str, Any]] = {}
    for surface, market, values in samples:
        present = {k: v for k, v in values.items() if v is not None}
        result = evaluate_rule(compiled, present, surface, profile_for(kb, surface))
        if result.outcome is Outcome.not_applicable:
            continue
        entry = out.setdefault(
            surface, {"samples": 0, "fires": 0, "unknown": 0, "markets": set(), "firing": set()}
        )
        entry["samples"] += 1
        entry["markets"].add(market)
        if result.outcome is Outcome.fires:
            entry["fires"] += 1
            entry["firing"].add(market)
        elif result.outcome is Outcome.unknown:
            entry["unknown"] += 1
    for entry in out.values():
        entry["markets"] = len(entry["markets"])
        entry["firing"] = sorted(entry["firing"])
    return out


def cross_sectional(
    kb: KnowledgeBase,
    rule_id: str,
    report_name: str,
    rows: list[dict[str, Any]],
    surface: str,
    percentile: float,
) -> dict[str, Any]:
    """Per-market medians of a rule's report expression, ranked across markets."""
    compiled = compile_rule(kb.rules[rule_id], kb.features)
    per_market: dict[str, list[float]] = defaultdict(list)
    measured = attempted = 0
    for row in rows:
        if row.get("surface") != surface:
            continue
        attempted += 1
        # An infinite ratio (no depth at all inside the band) is the most exposed
        # value, not an error; dropping it would bias the ranking toward safety.
        value = report_value(compiled, report_name, pass_values(row))
        if value is not None:
            measured += 1
            per_market[row["coin"]].append(value)
    medians = {coin: statistics.median(v) for coin, v in per_market.items()}
    if not medians:
        raise ValueError(f"no measurable rows for {rule_id} on {surface}")
    threshold = quantile(medians.values(), percentile)
    ranked = sorted(medians.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "surface": surface,
        "markets": len(medians),
        "rows_attempted": attempted,
        "rows_measured": measured,
        "percentile": percentile,
        "value": round(threshold, 2),
        "quantiles": {
            f"p{int(q * 100)}": round(quantile(medians.values(), q), 2)
            for q in (0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99)
        },
        "above_threshold": [
            {"market": coin, "median": round(v, 2)} for coin, v in ranked if v >= threshold
        ],
    }


def alert_budget(
    moves_by_market: Mapping[str, list[float]],
    days: float,
    episodes_per_day: float,
) -> dict[str, Any]:
    allowed = max(1, math.floor(episodes_per_day * days))
    threshold, used = budget_threshold(moves_by_market, allowed)
    contributors = sorted(
        ((coin, episodes(s, threshold)) for coin, s in moves_by_market.items()),
        key=lambda kv: kv[1],
        reverse=True,
    )
    windows = sum(len(s) for s in moves_by_market.values())
    pooled = [v for s in moves_by_market.values() for v in s]
    return {
        "markets": len(moves_by_market),
        "windows": windows,
        "days": round(days, 2),
        "episodes_per_day_budget": episodes_per_day,
        "episodes_allowed": allowed,
        "episodes_at_threshold": used,
        "value": round(threshold, 1),
        "quantiles": {
            name: round(quantile(pooled, q), 1)
            for name, q in (("p50", 0.5), ("p99", 0.99), ("p99.9", 0.999), ("p99.99", 0.9999))
        },
        "episodes_by_market": [
            {"market": coin, "episodes": n} for coin, n in contributors if n > 0
        ],
    }


def load_json(path: Path) -> Any:
    with _open_text(path) as handle:
        return json.load(handle)


def load_candle_moves(path: Path, surface: str) -> tuple[dict[str, list[float]], float]:
    data = load_json(path)
    markets = {
        coin: entry["moves_bps"]
        for coin, entry in data["markets"].items()
        if entry["surface"] == surface and entry["moves_bps"]
    }
    first = min(e["first"] for e in data["markets"].values())
    last = max(e["last"] for e in data["markets"].values())
    return markets, (last - first) / 86_400_000


def utc(ms: float) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).strftime("%Y-%m-%d %H:%M UTC")


def _levels(row: Mapping[str, str], side: str) -> list[tuple[float, float]]:
    return [
        (float(row[f"{side}[{i}].price"]), float(row[f"{side}[{i}].amount"]))
        for i in range(25)
        if row.get(f"{side}[{i}].price")
    ]


def archive_upper_bounds(
    kb: KnowledgeBase, book_csv: Path, ticker_csv: Path, band: float = 0.02
) -> dict[str, Any]:
    """Upper bounds on open interest / thinner side's 2% depth from a 20-level archive.

    Archived books (Tardis ``book_snapshot_25`` of Hyperliquid's 20-level feed)
    cannot measure depth within the band when the 20 levels end inside it.
    When every level lies within the band, their notional sum is a *lower*
    bound on in-band depth, so the rule's ratio computed from it is an *upper*
    bound. Snapshots whose levels extend past the band are skipped (their sum
    is no bound). Open interest is the same minute's value from the ticker
    file (``open_interest`` in coins x ``mark_price``).
    """
    compiled = compile_rule(kb.rules["open_interest_exceeds_depth"], kb.features)
    oi_by_minute: dict[int, float] = {}
    with _open_text(ticker_csv) as handle:
        for row in csv.DictReader(handle):
            if row["open_interest"] and row["mark_price"]:
                minute = int(row["timestamp"]) // 60_000_000
                oi_by_minute[minute] = float(row["open_interest"]) * float(row["mark_price"])
    bounds: list[float] = []
    spans: list[float] = []
    snapshots = 0
    with _open_text(book_csv) as handle:
        for row in csv.DictReader(handle):
            bids, asks = _levels(row, "bids"), _levels(row, "asks")
            if not bids or not asks:
                continue
            snapshots += 1
            mid = (bids[0][0] + asks[0][0]) / 2
            if bids[-1][0] < mid * (1 - band) or asks[-1][0] > mid * (1 + band):
                continue
            spans.append(max(mid - bids[-1][0], asks[-1][0] - mid) / mid)
            minute = int(row["timestamp"]) // 60_000_000
            if minute not in oi_by_minute:
                continue
            value = report_value(
                compiled,
                "oi_to_thinner_side_depth",
                {
                    "market.open_interest_usd": oi_by_minute[minute],
                    "market.bid_depth_usd_2pct": sum(p * q for p, q in bids),
                    "market.ask_depth_usd_2pct": sum(p * q for p, q in asks),
                },
            )
            if value is not None and math.isfinite(value):
                bounds.append(value)
    if not bounds:
        raise ValueError(f"{book_csv}: no snapshot yields a bound")
    return {
        "snapshots": snapshots,
        "bounded_snapshots": len(bounds),
        "median_level_span_pct": round(statistics.median(spans) * 100, 2),
        "median_open_interest_usd": round(statistics.median(oi_by_minute.values()), 0),
        "upper_bound_median": round(statistics.median(bounds), 1),
        "upper_bound_p90": round(quantile(bounds, 0.9), 1),
    }


# --------------------------------------------------------------------------
# The calibrations this repository runs
# --------------------------------------------------------------------------

CROSS_SECTION_PERCENTILE = 0.90
ALERT_EPISODES_PER_DAY = 1.0


def _window(rows: list[dict[str, Any]]) -> str:
    times = sorted(r["observed_at"] for r in rows)
    passes = len({r.get("pass") for r in rows})
    return f"{times[0][:16]} to {times[-1][:16]} UTC, {passes} passes"


def calibrate_cross_sections(
    kb: KnowledgeBase,
    rows: list[dict[str, Any]],
    computed: dt.date,
    archive_checks: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    window = _window(rows)
    depth_method = (
        "resting depth within 2% of mid from l2Book, escalating nSigFigs until 20 levels "
        "reach the band edge (rows where no aggregation covered the band are excluded)"
    )
    results = []
    oi = {
        surface: cross_sectional(
            kb,
            "open_interest_exceeds_depth",
            "oi_to_thinner_side_depth",
            rows,
            surface,
            CROSS_SECTION_PERCENTILE,
        )
        for surface in ("core_perps", "hip3_perps")
    }
    checks = []
    for name, spec in (archive_checks or {}).items():
        bound = archive_upper_bounds(kb, Path(spec["book"]), Path(spec["ticker"]))
        threshold = oi[spec["surface"]]["value"]
        verdict = (
            "would not have fired (even the upper bound is below the threshold)"
            if bound["upper_bound_median"] < threshold
            else "inconclusive (the upper bound reaches the threshold; the true ratio is lower)"
        )
        checks.append(
            {
                "description": (
                    f"{name}: {spec['source']}; 20 levels spanned a median "
                    f"{bound['median_level_span_pct']}% of price, so 2% depth is only bounded; "
                    f"open interest median ${bound['median_open_interest_usd']:,.0f}; ratio "
                    f"upper bound median {bound['upper_bound_median']}, p90 "
                    f"{bound['upper_bound_p90']} over {bound['bounded_snapshots']} snapshots"
                ),
                "outcome": f"{verdict}; {spec['surface']} threshold {threshold}",
            }
        )
    results.append(
        {
            "id": "open_interest_to_depth_cross_section",
            "computed": computed.isoformat(),
            "method": (
                f"For every listed market, the median over the recording of the rule's own ratio "
                f"(open interest / thinner side's {depth_method}). Threshold = "
                f"{int(CROSS_SECTION_PERCENTILE * 100)}th percentile of those medians across "
                "markets of the surface, so the rule marks the most exposed tenth of markets. The "
                "percentile is a policy choice for an attention list, not a statistical optimum."
            ),
            "data": f"Live public API recording of every listed perp: {window}.",
            "limitations": [
                "One recording window in one market regime; stress regimes are absent.",
                "Hyperps cannot be told apart from validator-operated perps in the API and are "
                "pooled into core_perps.",
                "Archived order books (Hyperliquid S3, Tardis) store 20 levels at full precision; "
                "on 2025-11-01 BTC's 20 levels never reached the 2% band (0 of 157,225 "
                "snapshots), so historical depth cannot be measured this way for liquid markets.",
            ],
            "targets": [
                {
                    "rule": "open_interest_exceeds_depth",
                    "threshold": "max_oi_to_depth",
                    "surface": "core_perps",
                    "applies_as": "rule_default",
                    "value": oi["core_perps"]["value"],
                },
                {
                    "rule": "open_interest_exceeds_depth",
                    "threshold": "max_oi_to_depth",
                    "surface": "hip3_perps",
                    "applies_as": "profile_override",
                    "value": oi["hip3_perps"]["value"],
                },
            ],
            "checks": checks,
            "results": oi,
        }
    )
    cap = cross_sectional(
        kb,
        "oi_cap_exceeds_depth",
        "cap_to_thinner_side_depth",
        rows,
        "hip3_perps",
        CROSS_SECTION_PERCENTILE,
    )
    results.append(
        {
            "id": "oi_cap_to_depth_cross_section",
            "computed": computed.isoformat(),
            "method": (
                "For every HIP-3 market with a published cap, the median over the recording of the "
                f"cap / thinner side's {depth_method}. Threshold = "
                f"{int(CROSS_SECTION_PERCENTILE * 100)}th percentile across markets "
                "(policy choice: the most generously capped tenth relative to depth)."
            ),
            "data": f"Live public API recording of every listed HIP-3 perp: {window}.",
            "limitations": [
                "One recording window; caps are configuration and change by deployer action."
            ],
            "targets": [
                {
                    "rule": "oi_cap_exceeds_depth",
                    "threshold": "max_cap_to_depth",
                    "surface": "hip3_perps",
                    "applies_as": "rule_default",
                    "value": cap["value"],
                },
            ],
            "results": {"hip3_perps": cap},
        }
    )
    return results


def calibrate_mark_moves(
    candles_path: Path,
    computed: dt.date,
    anchors: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    per_surface = {}
    span = ""
    for surface in ("core_perps", "hip3_perps"):
        moves, days = load_candle_moves(candles_path, surface)
        per_surface[surface] = alert_budget(moves, days, ALERT_EPISODES_PER_DAY)
    data = load_json(candles_path)
    firsts = [e["first"] for e in data["markets"].values()]
    lasts = [e["last"] for e in data["markets"].values()]
    span = f"{utc(min(firsts))} to {utc(max(lasts))}"
    checks = []
    for name, anchor in (anchors or {}).items():
        surface = anchor["surface"]
        threshold = per_surface[surface]["value"]
        peak = max(anchor["moves_bps"])
        checks.append(
            {
                "description": f"{name}: largest 5-minute move {peak:.0f} bps ({anchor['basis']})",
                "outcome": (
                    f"{'fires' if peak >= threshold else 'does not fire'} against the calibrated "
                    f"{surface} threshold of {threshold:.0f} bps"
                ),
            }
        )
    return {
        "id": "mark_move_alert_budget",
        "computed": computed.isoformat(),
        "method": (
            "Absolute close-to-close moves between consecutive 5-minute candles for every listed "
            "perp (most recent 5,000 candles each). Threshold = the lowest value at which it, and "
            "every higher value, yields at most "
            f"{ALERT_EPISODES_PER_DAY:g} alert episode per day across the surface, where "
            "consecutive exceeding windows in one market count as one episode. The budget is a "
            "policy choice for a paging rule."
        ),
        "data": f"Hyperliquid candleSnapshot, 5m candles, {span}.",
        "limitations": [
            "Candles are trade prices; the rule reads mark price. Mark is a median including the "
            "oracle and is usually smoother than last trades, so trade-move tails are expected to "
            "upper-bound mark-move tails and the episode budget to hold or be undershot. This is "
            "an approximation, not a measurement of mark.",
            "About 17 days of one regime; market-wide crashes are absent from the window.",
            "The threshold is pooled across markets; a few volatile markets produce most episodes "
            "(see episodes_by_market). Volatility-normalized moves would spread alerts evenly.",
        ],
        "targets": [
            {
                "rule": "mark_jump_short_window",
                "threshold": "max_mark_move_bps_5m",
                "surface": "core_perps",
                "applies_as": "rule_default",
                "value": per_surface["core_perps"]["value"],
            },
            {
                "rule": "mark_jump_short_window",
                "threshold": "max_mark_move_bps_5m",
                "surface": "hip3_perps",
                "applies_as": "profile_override",
                "value": per_surface["hip3_perps"]["value"],
            },
        ],
        "checks": checks,
        "results": per_surface,
    }
