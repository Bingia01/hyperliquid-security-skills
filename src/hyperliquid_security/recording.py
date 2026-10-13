"""Record calibration samples from Hyperliquid's public API (read-only).

Two datasets:

* **Market passes** - every listed perp (validator-operated and HIP-3) per pass:
  open interest, mark, oracle, HIP-3 open interest cap, resting depth within
  2% of mid measured with escalating ``nSigFigs`` aggregation, and the
  capital of the backstop that would inherit the market's liquidations. One
  JSON line per market per pass. A recording session writes one compressed
  file per pass into a directory with a manifest, so an interrupted session
  resumes by running the same command again.
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
import gzip
import itertools
import json
import os
import time
from collections import deque
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .hyperliquid_api import (
    ApiError,
    InfoClient,
    _Snapshot,
    hip3_backstop_address,
    hlp_liquidators,
    measure_depth,
)

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


REQUEST_ERRORS = (ApiError, KeyError, TypeError, ValueError, IndexError)


def backstop_capital(client: MeteredClient, dexes: list[Any]) -> dict[str, float | None]:
    """Account value of each backstop: HLP's liquidator vaults (key "core") and every
    HIP-3 dex's backstop liquidator. A backstop that could not be measured is None."""
    capital: dict[str, float | None] = {}
    try:
        liquidators = hlp_liquidators(client)
        capital["core"] = (
            sum(
                float(
                    client.post({"type": "clearinghouseState", "user": address})["marginSummary"][
                        "accountValue"
                    ]
                )
                for address in liquidators
            )
            if liquidators
            else None
        )
    except REQUEST_ERRORS:
        capital["core"] = None
    for index, info in enumerate(dexes):
        if not info:
            continue
        try:
            state = client.post(
                {
                    "type": "clearinghouseState",
                    "user": hip3_backstop_address(index),
                    "dex": info["name"],
                }
            )
            capital[info["name"]] = float(state["marginSummary"]["accountValue"])
        except REQUEST_ERRORS:
            capital[info["name"]] = None
    return capital


def record_pass(
    client: MeteredClient, now: Callable[[], dt.datetime] = _now
) -> Iterator[dict[str, Any]]:
    """Yield one row per listed, non-delisted perp across all dexes."""
    dexes = client.post({"type": "perpDexs"})
    capital = backstop_capital(client, dexes)
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
                "backstop_account_value_usd": capital.get(dex or "core"),
            }
            depth = _Snapshot()
            try:
                measure_depth(client, coin, depth)
            except REQUEST_ERRORS as exc:
                row["depth_error"] = str(exc)
            for side in ("bid", "ask"):
                feature = f"market.{side}_depth_usd_2pct"
                row[f"{side}_depth_usd_2pct"] = depth.values.get(feature)
                row[f"{side}_depth_how"] = depth.provenance.get(feature)
            yield row


MANIFEST = "manifest.json"
FILE_GLOB = "pass-*.jsonl.gz"
FILE_NAME_FORMAT = "pass-%Y%m%dT%H%M%S.jsonl.gz"


def _write_atomically(path: Path, data: bytes) -> None:
    """Write via a temporary file and rename, so an interruption never leaves half a file."""
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def recorded_passes(directory: Path) -> list[Path]:
    return sorted(directory.glob(FILE_GLOB))


def record_session(
    client: MeteredClient,
    directory: Path,
    hours: float,
    interval_seconds: float,
    stop_after_hours: float | None = None,
    now: Callable[[], dt.datetime] = _now,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> bool:
    """Record one pass every ``interval_seconds`` into ``directory`` for ``hours``.

    The first run writes a manifest fixing the session's start, end and
    interval; running again with the same directory resumes the session, so a
    recording can span machines, jobs or restarts. ``stop_after_hours`` ends
    this run early (for runners with a time limit) without ending the session.
    Returns True once the session's end has passed.
    """
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / MANIFEST
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["api"] != client.base_url:
            raise ValueError(f"{directory} records {manifest['api']}, not {client.base_url}")
        log(f"resuming session {manifest['started_at']} to {manifest['ends_at']}")
    else:
        started = now()
        manifest = {
            "started_at": started.isoformat(),
            "ends_at": (started + dt.timedelta(hours=hours)).isoformat(),
            "interval_seconds": interval_seconds,
            "api": client.base_url,
        }
        _write_atomically(manifest_path, (json.dumps(manifest, indent=2) + "\n").encode())
    ends_at = dt.datetime.fromisoformat(manifest["ends_at"])
    interval = dt.timedelta(seconds=manifest["interval_seconds"])
    stop_at = ends_at
    if stop_after_hours is not None:
        stop_at = min(ends_at, now() + dt.timedelta(hours=stop_after_hours))

    existing = recorded_passes(directory)
    number = len(existing)
    last_start = (
        dt.datetime.strptime(existing[-1].name, FILE_NAME_FORMAT).replace(tzinfo=dt.UTC)
        if existing
        else None
    )
    while True:
        due = now() if last_start is None else max(now(), last_start + interval)
        if due >= stop_at:
            break
        wait = (due - now()).total_seconds()
        if wait > 0:
            sleep(wait)
        started = now()
        number += 1
        lines = []
        for row in record_pass(client, now):
            row["pass"] = number
            lines.append(json.dumps(row))
        path = directory / started.strftime(FILE_NAME_FORMAT)
        _write_atomically(path, gzip.compress(("\n".join(lines) + "\n").encode()))
        elapsed = (now() - started).total_seconds()
        log(f"pass {number}: {len(lines)} rows in {elapsed:.0f}s -> {path.name}")
        last_start = started
    complete = now() >= ends_at or (last_start is not None and last_start + interval >= ends_at)
    log(f"{number} passes recorded; session {'complete' if complete else 'continues on rerun'}")
    return complete


def pack(directory: Path, out: Path) -> int:
    """Concatenate a session's pass files, in time order, into one gzipped JSON lines file."""
    count = 0
    with gzip.open(out, "wt", encoding="utf-8") as handle:
        for path in recorded_passes(directory):
            with gzip.open(path, "rt", encoding="utf-8") as part:
                for line in part:
                    handle.write(line)
                    count += 1
    return count


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
