"""The snapshot builder against a scripted fake API (no network in tests)."""

import datetime as dt
from typing import Any

import pytest

from hyperliquid_security.hyperliquid_api import (
    HLP_PARENT,
    ApiError,
    InfoClient,
    build_market_snapshot,
    hip3_backstop_address,
    side_depth,
)

NOW = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.UTC)


def levels(prices: list[float], size: float = 1.0) -> list[dict[str, Any]]:
    return [{"px": str(p), "sz": str(size), "n": 1} for p in prices]


def full_book(mid: float, count: int, step: float) -> list[list[dict[str, Any]]]:
    bids = levels([mid - step * (i + 1) for i in range(count)])
    asks = levels([mid + step * (i + 1) for i in range(count)])
    return [bids, asks]


class FakeApi:
    """Answers each request type from a table; records requests."""

    def __init__(self, books: dict[Any, Any], liquidator_names: list[str] | None = None) -> None:
        self.books = books
        self.requests: list[dict[str, Any]] = []
        self.liquidator_names = (
            liquidator_names if liquidator_names is not None else ["HLP Liquidator"]
        )

    def __call__(self, payload: dict[str, Any]) -> Any:
        self.requests.append(payload)
        kind = payload["type"]
        if kind == "metaAndAssetCtxs":
            return [
                {"universe": [{"name": "TEST"}]},
                [{"markPx": "100.0", "oraclePx": "99.0", "openInterest": "1000.0"}],
            ]
        if kind == "l2Book":
            return {"levels": self.books[payload.get("nSigFigs")]}
        if kind == "vaultDetails":
            if payload["vaultAddress"] == HLP_PARENT:
                children = [f"0x{i:040x}" for i in range(1, len(self.liquidator_names) + 1)]
                return {"relationship": {"type": "parent", "data": {"childAddresses": children}}}
            index = int(payload["vaultAddress"], 16) - 1
            return {"name": self.liquidator_names[index]}
        if kind == "clearinghouseState":
            return {
                "marginSummary": {"accountValue": "1000000.0"},
                "assetPositions": [
                    {
                        "position": {
                            "coin": "TEST",
                            "szi": "-50",
                            "positionValue": "5000.0",
                            "unrealizedPnl": "-200.0",
                        }
                    },
                    {
                        "position": {
                            "coin": "OTHER",
                            "szi": "10",
                            "positionValue": "999.0",
                            "unrealizedPnl": "5.0",
                        }
                    },
                ],
            }
        raise AssertionError(f"unexpected request {payload}")


def test_side_depth_coverage_rules() -> None:
    mid = 100.0
    depth, covered = side_depth(levels([99.5, 99.0, 97.0]), mid, "bid")
    assert covered  # fewer than 20 levels: the whole side was returned
    assert depth == pytest.approx(99.5 + 99.0)  # 97 is outside the 2% band
    twenty_inside = levels([99.9 - 0.01 * i for i in range(20)])
    assert side_depth(twenty_inside, mid, "bid")[1] is False


def test_depth_escalates_aggregation_until_band_is_covered() -> None:
    api = FakeApi(
        {
            None: full_book(100.0, 20, 0.01),  # spans 0.2%: not covered
            5: full_book(100.0, 20, 0.05),  # spans 1%: not covered
            4: full_book(100.0, 20, 0.5),  # spans 10%: covered
        }
    )
    snapshot = build_market_snapshot(InfoClient(transport=api), "TEST", now=lambda: NOW)
    assert [r.get("nSigFigs") for r in api.requests if r["type"] == "l2Book"] == [None, 5, 4]
    assert snapshot["values"]["market.bid_depth_usd_2pct"] == pytest.approx(
        sum(100 - 0.5 * i for i in range(1, 5))
    )
    assert "nSigFigs=4" in snapshot["provenance"]["market.bid_depth_usd_2pct"]


def test_depth_is_absent_when_never_covered() -> None:
    api = FakeApi({k: full_book(100.0, 20, 0.01) for k in (None, 5, 4, 3, 2)})
    snapshot = build_market_snapshot(InfoClient(transport=api), "TEST", now=lambda: NOW)
    assert "market.bid_depth_usd_2pct" not in snapshot["values"]
    assert snapshot["provenance"]["market.bid_depth_usd_2pct"].startswith("absent")


def test_open_interest_is_converted_from_coin_units() -> None:
    api = FakeApi({None: full_book(100.0, 5, 0.1)})
    snapshot = build_market_snapshot(InfoClient(transport=api), "TEST", now=lambda: NOW)
    assert snapshot["values"]["market.open_interest_usd"] == pytest.approx(100_000.0)


def test_backstop_uses_only_liquidator_children() -> None:
    api = FakeApi(
        {None: full_book(100.0, 5, 0.1)}, liquidator_names=["HLP Strategy A", "HLP Liquidator 2"]
    )
    snapshot = build_market_snapshot(InfoClient(transport=api), "TEST", now=lambda: NOW)
    values = snapshot["values"]
    assert values["market.backstop_short_usd"] == 5000.0  # one liquidator, not two vaults
    assert values["market.backstop_long_usd"] == 0.0
    assert values["backstop.liquidator_unrealized_pnl_usd"] == pytest.approx(-195.0)


def test_no_liquidator_found_means_absent_not_zero() -> None:
    api = FakeApi({None: full_book(100.0, 5, 0.1)}, liquidator_names=["HLP Strategy A"])
    snapshot = build_market_snapshot(InfoClient(transport=api), "TEST", now=lambda: NOW)
    assert "market.backstop_short_usd" not in snapshot["values"]


def test_failed_group_is_marked_absent() -> None:
    def broken(payload: dict[str, Any]) -> Any:
        if payload["type"] == "vaultDetails":
            raise ApiError("vaultDetails failed: 503")
        return FakeApi({None: full_book(100.0, 5, 0.1)})(payload)

    snapshot = build_market_snapshot(InfoClient(transport=broken), "TEST", now=lambda: NOW)
    assert "market.backstop_long_usd" not in snapshot["values"]
    assert "503" in snapshot["provenance"]["market.backstop_long_usd"]
    assert "market.bid_depth_usd_2pct" in snapshot["values"]


def test_mark_history_requires_a_window() -> None:
    api = FakeApi({None: full_book(100.0, 5, 0.1)})
    client = InfoClient(transport=api)
    earlier = {
        "subject": "TEST",
        "observed_at": (NOW - dt.timedelta(minutes=5)).isoformat(),
        "values": {"market.mark_price": 80.0},
    }
    stale = dict(earlier, observed_at=(NOW - dt.timedelta(hours=1)).isoformat())
    assert build_market_snapshot(client, "TEST", previous=earlier, now=lambda: NOW)["values"][
        "market.mark_move_bps_5m"
    ] == pytest.approx(2500.0)
    assert (
        "market.mark_move_bps_5m"
        not in build_market_snapshot(client, "TEST", previous=stale, now=lambda: NOW)["values"]
    )


def test_hip3_backstop_address() -> None:
    assert hip3_backstop_address(1) == "0x4000000000000000000000000000000000000001"


def test_client_requires_https() -> None:
    with pytest.raises(ValueError):
        InfoClient(base_url="http://api.hyperliquid.xyz/info")
