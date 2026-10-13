"""Record calibration samples from Hyperliquid's public API (read-only).

Two datasets:

* **Market passes** - every listed perp (validator-operated and HIP-3) per pass:
  open interest, mark, oracle, HIP-3 open interest cap, and resting depth
  within 2% of mid measured with escalating ``nSigFigs`` aggregation. One
  JSON line per market per pass.
* **Candle moves** - the most recent 5,000 five-minute candles per market
  (about 17 days), reduced to close-to-close moves in basis points. Candles
  are trade prices, so this is a proxy for mark-price moves, never a
  substitute measured in the same units of evidence.

Request weights follow Hyperliquid's published limits (1200 per minute per IP;
l2Book 2, most info requests 20, candleSnapshot 20 plus 1 per 60 candles). The
recorder spends at most ``weight_per_minute`` of that budget.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import time
from collections import deque
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .hyperliquid_api import ApiError, InfoClient, _Snapshot, measure_depth

WEIGHTS = {"l2Book": 2, "allMids": 2, "clearinghouseState": 2}
DEFAULT_WEIGHT = 20
CANDLES_PER_EXTRA_WEIGHT = 60


class RateLimiter:
    """Sliding one-minute window over request weight."""

    def __init__(
        self,
        weight_per_minute: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.limit = weight_per_minute
        self.clock = clock
        self.sleep = sleep
        self.spent: deque[tuple[float, int]] = deque()

    def acquire(self, weight: int) -> None:
        while True:
            now = self.clock()
            while self.spent and now - self.spent[0][0] >= 60.0:
                self.spent.popleft()
            used = sum(w for _, w in self.spent)
            if used + weight <= self.limit or not self.spent:
                self.spent.append((now, weight))
                return
            self.sleep(60.0 - (now - self.spent[0][0]) + 0.01)


class MeteredClient:
    """Wrap an InfoClient so every request is charged to a RateLimiter."""

    def __init__(self, client: InfoClient, limiter: RateLimiter) -> None:
        self.client = client
        self.limiter = limiter
        self.base_url = client.base_url

    def post(self, payload: dict[str, Any]) -> Any:
        self.limiter.acquire(WEIGHTS.get(payload["type"], DEFAULT_WEIGHT))
        return self.client.post(payload)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def record_pass(
    client: MeteredClient, now: Callable[[], dt.datetime] = _now
) -> Iterator[dict[str, Any]]:
    """Yield one row per listed, non-delisted perp across all dexes."""
    dexes = client.post({"type": "perpDexs"})
    for index, info in enumerate(dexes):
        dex = info["name"] if info else None
        caps = dict(info.get("assetToStreamingOiCap") or []) if info else {}
        payload: dict[str, Any] = {"type": "metaAndAssetCtxs"}
        if dex:
            payload["dex"] = dex
        try:
            meta, contexts = client.post(payload)
        except (ApiError, ValueError, TypeError) as exc:
            yield {"observed_at": now().isoformat(), "dex": dex, "error": str(exc)}
            continue
        for asset, context in zip(meta["universe"], contexts, strict=False):
            if asset.get("isDelisted"):
                continue
            coin = asset["name"]
            mark = float(context["markPx"])
            row: dict[str, Any] = {
                "observed_at": now().isoformat(),
                "dex": dex,
                "dex_index": index,
                "coin": coin,
                "surface": "hip3_perps" if dex else "core_perps",
                "max_leverage": asset.get("maxLeverage"),
                "mark_price": mark,
                "oracle_price": float(context["oraclePx"]),
                "open_interest_usd": float(context["openInterest"]) * mark,
                "day_notional_volume_usd": float(context.get("dayNtlVlm") or 0.0),
                "oi_cap_usd": float(caps[coin]) if coin in caps else None,
            }
            depth = _Snapshot()
            try:
                measure_depth(client, coin, depth)
            except (ApiError, KeyError, TypeError, ValueError, IndexError) as exc:
                row["depth_error"] = str(exc)
            for side in ("bid", "ask"):
                feature = f"market.{side}_depth_usd_2pct"
                row[f"{side}_depth_usd_2pct"] = depth.values.get(feature)
                row[f"{side}_depth_how"] = depth.provenance.get(feature)
            yield row


def record(
    client: MeteredClient,
    out: Path,
    passes: int,
    interval_seconds: float,
    log: Callable[[str], None] = print,
) -> None:
    """Append ``passes`` passes to ``out`` (JSON lines), starting one every interval."""
    out.parent.mkdir(parents=True, exist_ok=True)
    for number in range(1, passes + 1):
        started = time.monotonic()
        count = 0
        with out.open("a", encoding="utf-8") as handle:
            for row in record_pass(client):
                row["pass"] = number
                handle.write(json.dumps(row) + "\n")
                count += 1
        elapsed = time.monotonic() - started
        log(f"pass {number}/{passes}: {count} rows in {elapsed:.0f}s")
        if number < passes:
            time.sleep(max(0.0, interval_seconds - elapsed))


def candle_moves_bps(candles: list[dict[str, Any]]) -> list[float]:
    """Absolute close-to-close moves between consecutive candles, in basis points.

    Gaps (a missing candle between two returned ones) are skipped so that every
    move spans exactly one interval.
    """
    ordered = sorted(candles, key=lambda c: c["t"])
    moves = []
    for previous, current in itertools.pairwise(ordered):
        if current["t"] - previous["t"] != current["T"] + 1 - current["t"]:
            continue
        before, after = float(previous["c"]), float(current["c"])
        if before > 0:
            moves.append(abs(after - before) / before * 10_000)
    return moves


def record_candle_moves(
    client: MeteredClient,
    out: Path,
    interval: str = "5m",
    now: Callable[[], dt.datetime] = _now,
    log: Callable[[str], None] = print,
) -> None:
    """Write {coin: {surface, moves_bps, first, last}} for every listed perp."""
    end = int(now().timestamp() * 1000)
    start = end - 5000 * 5 * 60 * 1000
    result: dict[str, Any] = {"interval": interval, "fetched_at": now().isoformat(), "markets": {}}
    dexes = client.post({"type": "perpDexs"})
    for info in dexes:
        dex = info["name"] if info else None
        payload: dict[str, Any] = {"type": "meta"}
        if dex:
            payload["dex"] = dex
        meta = client.post(payload)
        for asset in meta["universe"]:
            if asset.get("isDelisted"):
                continue
            coin = asset["name"]
            client.limiter.acquire(5000 // CANDLES_PER_EXTRA_WEIGHT)
            try:
                candles = client.post(
                    {
                        "type": "candleSnapshot",
                        "req": {
                            "coin": coin,
                            "interval": interval,
                            "startTime": start,
                            "endTime": end,
                        },
                    }
                )
            except ApiError as exc:
                log(f"{coin}: {exc}")
                continue
            if not candles:
                continue
            result["markets"][coin] = {
                "surface": "hip3_perps" if dex else "core_perps",
                "first": candles[0]["t"],
                "last": candles[-1]["t"],
                "moves_bps": [round(m, 3) for m in candle_moves_bps(candles)],
            }
        log(f"dex {dex or 'core'}: {len(result['markets'])} markets so far")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result), encoding="utf-8")
