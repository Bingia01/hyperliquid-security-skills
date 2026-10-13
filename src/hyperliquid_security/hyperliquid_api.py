"""Read-only snapshot builder for features computable from Hyperliquid's public API.

Principle: a feature is either measured correctly or absent with a stated
reason. It is never filled with a guess, a default or a truncated value,
because the rule engine treats absence as "unknown" and a wrong number as fact.

Facts this module relies on (checked against the live API on 2026-10-12):

* ``l2Book`` returns at most 20 levels per side; ``nSigFigs`` (2-5) coarsens
  price buckets so 20 levels span a wider band.
* ``openInterest`` in asset contexts is in coin units.
* HLP's parent vault lists child vaults; liquidator children are named
  "HLP Liquidator", "HLP Liquidator 2", and so on.
* HIP-3 dexes appear in ``perpDexs`` (index 0 is the validator-operated dex,
  reported as null). A dex's backstop liquidator is the address
  ``0x4000...0000 + dex index``.
"""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

HLP_PARENT = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"
HIP3_BACKSTOP_BASE = 0x4000000000000000000000000000000000000000
HIP3_MINIMUM_STAKE_HYPE = 500_000.0
DEPTH_BAND = 0.02
BOOK_LEVEL_LIMIT = 20
SIG_FIG_LADDER: tuple[int | None, ...] = (None, 5, 4, 3, 2)
MARK_HISTORY_WINDOW_SECONDS = (240.0, 360.0)

Transport = Callable[[dict[str, Any]], Any]


class ApiError(RuntimeError):
    pass


class InfoClient:
    """Minimal client for POST /info with bounded retries."""

    def __init__(
        self,
        base_url: str = "https://api.hyperliquid.xyz/info",
        timeout: float = 15.0,
        retries: int = 3,
        transport: Transport | None = None,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("the info API must be reached over https")
        self.base_url = base_url
        self.timeout = timeout
        self.retries = retries
        self._transport = transport

    def post(self, payload: dict[str, Any]) -> Any:
        if self._transport is not None:
            return self._transport(payload)
        body = json.dumps(payload).encode()
        last_error: Exception | None = None
        for attempt in range(self.retries):
            request = urllib.request.Request(  # noqa: S310 - https enforced in __init__
                self.base_url, data=body, headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                    return json.loads(response.read())
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in (429, 500, 502, 503, 504):
                    break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
            time.sleep(2**attempt)
        raise ApiError(f"{payload.get('type')} failed: {last_error}")


class _Snapshot:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.provenance: dict[str, str] = {}

    def put(self, feature: str, value: float, how: str) -> None:
        self.values[feature] = value
        self.provenance[feature] = how

    def absent(self, feature: str, why: str) -> None:
        self.provenance[feature] = f"absent: {why}"


def _f(text: Any) -> float:
    return float(text)


# --------------------------------------------------------------------------
# Order book depth
# --------------------------------------------------------------------------


def side_depth(levels: list[dict[str, Any]], mid: float, side: str) -> tuple[float, bool]:
    """Notional within DEPTH_BAND of mid on one side, and whether the band was covered.

    The band is covered if the side has fewer levels than the API limit (the
    whole side was returned) or the last level lies beyond the band edge.
    Bucketed levels report a price at or beyond every order they contain, so a
    bucket inside the band is wholly inside it; the edge bucket may be
    dropped, which errs toward less depth.
    """
    if side == "bid":
        edge = mid * (1 - DEPTH_BAND)
        inside = [lv for lv in levels if _f(lv["px"]) >= edge]
        covered = len(levels) < BOOK_LEVEL_LIMIT or _f(levels[-1]["px"]) < edge
    else:
        edge = mid * (1 + DEPTH_BAND)
        inside = [lv for lv in levels if _f(lv["px"]) <= edge]
        covered = len(levels) < BOOK_LEVEL_LIMIT or _f(levels[-1]["px"]) > edge
    return sum(_f(lv["px"]) * _f(lv["sz"]) for lv in inside), covered


def measure_depth(client: InfoClient, coin: str, snapshot: _Snapshot) -> None:
    bids_needed, asks_needed = True, True
    mid: float | None = None
    for sig_figs in SIG_FIG_LADDER:
        payload: dict[str, Any] = {"type": "l2Book", "coin": coin}
        if sig_figs is not None:
            payload["nSigFigs"] = sig_figs
        book = client.post(payload)
        bids, asks = book["levels"]
        if mid is None:
            if not bids or not asks:
                # A one-sided book has no mid; depth relative to mid is undefined.
                for side in ("bid", "ask"):
                    snapshot.absent(
                        f"market.{side}_depth_usd_2pct", "one side of the book is empty"
                    )
                return
            mid = (_f(bids[0]["px"]) + _f(asks[0]["px"])) / 2
        label = "full precision" if sig_figs is None else f"nSigFigs={sig_figs}"
        for side, levels, needed in (("bid", bids, bids_needed), ("ask", asks, asks_needed)):
            if not needed:
                continue
            depth, covered = side_depth(levels, mid, side)
            if covered:
                snapshot.put(
                    f"market.{side}_depth_usd_2pct",
                    depth,
                    f"l2Book {label}; mid {mid:.8g}; band +/-2%",
                )
                if side == "bid":
                    bids_needed = False
                else:
                    asks_needed = False
        if not bids_needed and not asks_needed:
            return
    for side, needed in (("bid", bids_needed), ("ask", asks_needed)):
        if needed:
            snapshot.absent(
                f"market.{side}_depth_usd_2pct", "20 levels never reached the 2% band edge"
            )


# --------------------------------------------------------------------------
# Positions held by specific addresses
# --------------------------------------------------------------------------


def positions_by_side(state: dict[str, Any], coin: str) -> tuple[float, float, float]:
    """(long notional, short notional, unrealized PnL) for one coin in a clearinghouse state."""
    long_usd = short_usd = pnl = 0.0
    for item in state.get("assetPositions", []):
        position = item["position"]
        if position["coin"] != coin:
            continue
        value = abs(_f(position["positionValue"]))
        if _f(position["szi"]) > 0:
            long_usd += value
        else:
            short_usd += value
        pnl += _f(position.get("unrealizedPnl", 0))
    return long_usd, short_usd, pnl


def total_unrealized_pnl(state: dict[str, Any]) -> float:
    return sum(_f(i["position"].get("unrealizedPnl", 0)) for i in state.get("assetPositions", []))


def hlp_liquidators(client: InfoClient) -> list[str]:
    parent = client.post({"type": "vaultDetails", "vaultAddress": HLP_PARENT})
    children = parent.get("relationship", {}).get("data", {}).get("childAddresses", [])
    found = []
    for child in children:
        details = client.post({"type": "vaultDetails", "vaultAddress": child})
        if str(details.get("name", "")).startswith("HLP Liquidator"):
            found.append(child)
    return found


def hip3_backstop_address(dex_index: int) -> str:
    return f"0x{HIP3_BACKSTOP_BASE + dex_index:040x}"


# --------------------------------------------------------------------------
# Snapshot assembly
# --------------------------------------------------------------------------


def _asset_context(client: InfoClient, coin: str, dex: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "metaAndAssetCtxs"}
    if dex:
        payload["dex"] = dex
    meta, contexts = client.post(payload)
    for asset, context in zip(meta["universe"], contexts, strict=False):
        if asset["name"] == coin:
            return {"asset": asset, "context": context}
    raise ApiError(f"{coin!r} not found in metaAndAssetCtxs (dex={dex!r})")


def build_market_snapshot(
    client: InfoClient,
    coin: str,
    dex: str | None = None,
    previous: dict[str, Any] | None = None,
    surface: str | None = None,
    now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
) -> dict[str, Any]:
    snapshot = _Snapshot()
    observed_at = now()
    if surface is None:
        surface = "hip3_perps" if dex else "core_perps"

    found = _asset_context(client, coin, dex)
    context = found["context"]
    mark = _f(context["markPx"])
    snapshot.put("market.mark_price", mark, "metaAndAssetCtxs markPx")
    snapshot.put("market.oracle_price", _f(context["oraclePx"]), "metaAndAssetCtxs oraclePx")
    snapshot.put(
        "market.open_interest_usd",
        _f(context["openInterest"]) * mark,
        "metaAndAssetCtxs openInterest (coin units) x markPx",
    )
    _guarded(snapshot, DEPTH_FEATURES, lambda: measure_depth(client, coin, snapshot))
    _mark_history(snapshot, coin, mark, observed_at, previous)

    if dex:
        _guarded(snapshot, HIP3_FEATURES, lambda: _hip3_features(client, coin, dex, snapshot))
    else:
        _guarded(
            snapshot, BACKSTOP_FEATURES, lambda: _core_backstop_features(client, coin, snapshot)
        )
        for feature in ("market.oi_cap_usd", "market.oracle_setter_position_usd"):
            snapshot.absent(feature, "applies to HIP-3 markets only")

    return {
        "surface": surface,
        "subject": coin,
        "observed_at": observed_at.isoformat(),
        "source": client.base_url,
        "values": dict(sorted(snapshot.values.items())),
        "provenance": dict(sorted(snapshot.provenance.items())),
    }


DEPTH_FEATURES = ("market.bid_depth_usd_2pct", "market.ask_depth_usd_2pct")
BACKSTOP_FEATURES = (
    "market.backstop_long_usd",
    "market.backstop_short_usd",
    "backstop.liquidator_account_value_usd",
    "backstop.liquidator_unrealized_pnl_usd",
)
HIP3_FEATURES = (
    "market.oi_cap_usd",
    "market.oracle_setter_position_usd",
    "dex.total_net_deposit_usd",
    "dex.slashable_stake_usd",
    *BACKSTOP_FEATURES,
)


def _guarded(snapshot: _Snapshot, features: tuple[str, ...], step: Callable[[], None]) -> None:
    """Run one group of measurements; on failure mark whatever it had not measured as absent."""
    try:
        step()
    except (ApiError, KeyError, TypeError, ValueError, IndexError) as exc:
        for feature in features:
            if feature not in snapshot.values:
                snapshot.absent(feature, f"request failed: {exc}")


def _mark_history(
    snapshot: _Snapshot,
    coin: str,
    mark: float,
    observed_at: dt.datetime,
    previous: dict[str, Any] | None,
) -> None:
    feature = "market.mark_move_bps_5m"
    if previous is None:
        snapshot.absent(feature, "no earlier snapshot supplied (--previous)")
        return
    if previous.get("subject") != coin:
        snapshot.absent(feature, "earlier snapshot is for a different market")
        return
    earlier = previous.get("values", {}).get("market.mark_price")
    when = dt.datetime.fromisoformat(previous["observed_at"])
    age = (observed_at - when).total_seconds()
    low, high = MARK_HISTORY_WINDOW_SECONDS
    if earlier is None or not low <= age <= high:
        snapshot.absent(feature, f"earlier snapshot is {age:.0f}s old; need {low:.0f}-{high:.0f}s")
        return
    if earlier == 0:
        snapshot.absent(feature, "earlier mark price was zero")
        return
    snapshot.put(feature, abs(mark - earlier) / earlier * 10_000, f"vs snapshot {age:.0f}s earlier")


def _core_backstop_features(client: InfoClient, coin: str, snapshot: _Snapshot) -> None:
    liquidators = hlp_liquidators(client)
    if not liquidators:
        for feature in BACKSTOP_FEATURES:
            snapshot.absent(feature, "no child vault of HLP is named 'HLP Liquidator*'")
        return
    long_usd = short_usd = equity = pnl = 0.0
    for address in liquidators:
        state = client.post({"type": "clearinghouseState", "user": address})
        side_long, side_short, _ = positions_by_side(state, coin)
        long_usd += side_long
        short_usd += side_short
        equity += _f(state["marginSummary"]["accountValue"])
        pnl += total_unrealized_pnl(state)
    how = f"sum over {len(liquidators)} HLP liquidator vaults"
    snapshot.put("market.backstop_long_usd", long_usd, how)
    snapshot.put("market.backstop_short_usd", short_usd, how)
    snapshot.put("backstop.liquidator_account_value_usd", equity, how)
    snapshot.put("backstop.liquidator_unrealized_pnl_usd", pnl, how)


def _hip3_features(client: InfoClient, coin: str, dex: str, snapshot: _Snapshot) -> None:
    dexes = client.post({"type": "perpDexs"})
    index = next((i for i, d in enumerate(dexes) if d and d.get("name") == dex), None)
    if index is None:
        raise ApiError(f"dex {dex!r} not found in perpDexs")
    info = dexes[index]

    caps = dict(info.get("assetToStreamingOiCap") or [])
    if coin in caps:
        snapshot.put("market.oi_cap_usd", _f(caps[coin]), "perpDexs assetToStreamingOiCap")
    else:
        snapshot.absent("market.oi_cap_usd", "no cap listed for this asset")

    backstop = hip3_backstop_address(index)
    state = client.post({"type": "clearinghouseState", "user": backstop, "dex": dex})
    long_usd, short_usd, _ = positions_by_side(state, coin)
    how = f"dex backstop liquidator {backstop}"
    snapshot.put("market.backstop_long_usd", long_usd, how)
    snapshot.put("market.backstop_short_usd", short_usd, how)
    snapshot.put(
        "backstop.liquidator_account_value_usd", _f(state["marginSummary"]["accountValue"]), how
    )
    snapshot.put("backstop.liquidator_unrealized_pnl_usd", total_unrealized_pnl(state), how)

    setters = {info["deployer"]}
    if info.get("oracleUpdater"):
        setters.add(info["oracleUpdater"])
    for action, addresses in info.get("subDeployers") or []:
        if action == "setOracle":
            setters.update(addresses)
    conflicted = 0.0
    for address in sorted(setters):
        held = client.post({"type": "clearinghouseState", "user": address, "dex": dex})
        side_long, side_short, _ = positions_by_side(held, coin)
        conflicted += side_long + side_short
    snapshot.put(
        "market.oracle_setter_position_usd",
        conflicted,
        f"{len(setters)} addresses (deployer, oracleUpdater, setOracle sub-deployers)",
    )

    status = client.post({"type": "perpDexStatus", "dex": dex})
    snapshot.put("dex.total_net_deposit_usd", _f(status["totalNetDeposit"]), "perpDexStatus")
    hype = _hype_spot_price(client)
    if hype is None:
        snapshot.absent("dex.slashable_stake_usd", "HYPE/USDC spot price not found")
    else:
        snapshot.put(
            "dex.slashable_stake_usd",
            HIP3_MINIMUM_STAKE_HYPE * hype,
            f"documented minimum 500,000 HYPE x spot {hype:.6g} (lower bound)",
        )


def _hype_spot_price(client: InfoClient) -> float | None:
    meta = client.post({"type": "spotMeta"})
    names = {t["index"]: t["name"] for t in meta["tokens"]}
    pair = next(
        (
            u["name"]
            for u in meta["universe"]
            if [names.get(t) for t in u["tokens"]] == ["HYPE", "USDC"]
        ),
        None,
    )
    if pair is None:
        return None
    mids = client.post({"type": "allMids"})
    price = mids.get(pair)
    return _f(price) if price is not None else None
