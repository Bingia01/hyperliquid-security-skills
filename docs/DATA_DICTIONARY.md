# Data Dictionary

## Purpose

This dictionary defines every input referenced in `rules/heuristics.v1.yaml`. It tells contributors where each data point comes from, how it is computed, and which heuristics use it.

## How to read this dictionary

Each entry includes:
- **Input name** — the namespaced identifier used in heuristic rules (e.g., `market.open_interest_usd`)
- **Description** — what the data point represents
- **Source type** — how the data is obtained
- **Source detail** — the specific API endpoint, computation method, or analysis step
- **Used by** — which heuristic IDs reference this input

## Source types

| Source type | Definition |
|---|---|
| `api_direct` | Retrieved directly from a Hyperliquid API endpoint with minimal transformation |
| `derived` | Computed from one or more `api_direct` inputs using arithmetic, aggregation, or windowing |
| `static_analysis` | Determined by reading contract source code or bytecode — not a runtime value |
| `hypothetical` | Represents a system property that is not currently queryable via API; included for completeness and future instrumentation |

---

## market.* (17 inputs)

| Input name | Description | Source type | Source detail | Used by |
|---|---|---|---|---|
| `market.open_interest_usd` | Total open interest in USD for a given market | `api_direct` | Info API `metaAndAssetCtxs` → `openInterest` × `markPx` | `thin_market_squeeze_risk` |
| `market.executable_depth_usd_1pct` | Total USD value of orders within 1% of mid price on both sides | `derived` | Info API `l2Book` → sum order sizes × prices within 1% of mid | `thin_market_squeeze_risk`, `toxic_inventory_transfer`, `spoofing_wall_reversal` |
| `market.executable_depth_usd_2pct` | Total USD value of orders within 2% of mid price on both sides | `derived` | Info API `l2Book` → sum order sizes × prices within 2% of mid | `thin_market_squeeze_risk`, `toxic_inventory_transfer` |
| `market.top_positions` | List of largest positions by notional USD in a given market | `derived` | Info API `clearinghouseState` → enumerate accounts, rank by `positionValue` | `thin_market_squeeze_risk` |
| `market.liquidation_notional_usd_5pct_band` | Total notional of positions that would be liquidated if price moved 5% | `derived` | Info API `clearinghouseState` → filter positions where `liquidationPx` is within 5% of `markPx`, sum notional | `thin_market_squeeze_risk` |
| `market.price_move_sigma_15m` | Price move over 15 minutes expressed in standard deviations of recent volatility | `derived` | Info API `candleSnapshot` → compute 15m return / rolling σ of 15m returns | `thin_market_squeeze_risk` |
| `market.external_anchor_divergence_bps` | Basis-point spread between Hyperliquid mark price and external reference price | `derived` | Info API `allMids` vs external CEX API (e.g., Binance spot) → `abs(hl_mid - ext_mid) / ext_mid × 10000` | `thin_market_squeeze_risk` |
| `market.mark_price` | Current mark price on Hyperliquid for the market | `api_direct` | Info API `allMids` or `l2Book` → `markPx` | `settlement_cliff` |
| `market.oracle_price` | Oracle price used by the risk engine for margin calculations | `api_direct` | Info API `metaAndAssetCtxs` → `oraclePrice` | `settlement_cliff` |
| `market.external_anchor_price` | External reference price from off-platform source (e.g., CEX spot) | `derived` | External CEX API aggregation (e.g., median of Binance, OKX, Bybit spot) | `settlement_cliff` |
| `market.settlement_reference_price` | The price used for settlement in hyperps, HIP-3, or HIP-4 markets | `api_direct` | Info API market metadata → settlement reference configuration | `settlement_cliff` |
| `market.settlement_window_minutes` | Duration of the settlement window in minutes | `api_direct` | Info API market metadata → settlement window parameter | `settlement_cliff` |
| `market.market_type` | Market classification: core perps, hyperps, HIP-3, HIP-4 | `api_direct` | Info API `meta` → market type field | `settlement_cliff` |
| `market.halt_state` | Whether the market is currently halted or in restricted mode | `api_direct` | Info API market status endpoint | `crisis_centralization_trigger` |
| `market.delisting_risk_flags` | Array of boolean flags indicating delisting risk conditions (e.g., extreme HLP loss, zero depth, oracle failure) | `derived` | Composite of multiple API checks: HLP PnL threshold, depth below minimum, oracle staleness | `crisis_centralization_trigger` |
| `market.price_change_bps_2m` | Price change in basis points over the last 2 minutes | `derived` | Info API `candleSnapshot` or WebSocket `trades` → `(price_now - price_2m_ago) / price_2m_ago × 10000` | `spoofing_wall_reversal` |
| `market.follow_on_liquidations_usd_5m` | Total USD value of liquidations in the 5 minutes following a price event | `derived` | WebSocket `liquidations` or Info API `userFills` filtered by liquidation flag → sum notional over 5m window | `spoofing_wall_reversal` |

## hlp.* (4 inputs)

| Input name | Description | Source type | Source detail | Used by |
|---|---|---|---|---|
| `hlp.inventory_delta_usd_5m` | Change in HLP's position inventory in USD over the last 5 minutes | `derived` | Info API `clearinghouseState` for HLP vault address → `position_now - position_5m_ago` | `toxic_inventory_transfer` |
| `hlp.total_inventory_usd` | Total USD value of HLP's current position inventory | `api_direct` | Info API `clearinghouseState` for HLP vault address → sum of `positionValue` across all markets | `toxic_inventory_transfer` |
| `hlp.unwind_velocity_usd_5m` | Rate at which HLP is reducing inventory, in USD over 5 minutes | `derived` | Info API `clearinghouseState` for HLP vault address → track inventory reduction over 5m rolling window | `toxic_inventory_transfer` |
| `hlp.unrealized_pnl_delta_usd_15m` | Change in HLP's unrealized PnL in USD over the last 15 minutes | `derived` | Info API `clearinghouseState` for HLP vault address → `unrealizedPnl_now - unrealizedPnl_15m_ago` | `toxic_inventory_transfer`, `crisis_centralization_trigger` |

## account.* (12 inputs)

| Input name | Description | Source type | Source detail | Used by |
|---|---|---|---|---|
| `account.collateral_delta_usd_30m` | Change in account collateral in USD over the last 30 minutes | `derived` | Info API `clearinghouseState` per user → `accountValue_now - accountValue_30m_ago` adjusted for PnL | `strategic_margin_drain` |
| `account.position_notional_usd` | Total notional value of the account's open positions in USD | `api_direct` | Info API `clearinghouseState` per user → sum of `positionValue` | `strategic_margin_drain` |
| `account.maintenance_margin_ratio_before` | Maintenance margin ratio before the collateral change | `derived` | Info API `clearinghouseState` → `maintenanceMargin / accountValue` at prior snapshot | `strategic_margin_drain` |
| `account.maintenance_margin_ratio_after` | Maintenance margin ratio after the collateral change | `derived` | Info API `clearinghouseState` → `maintenanceMargin / accountValue` at current snapshot | `strategic_margin_drain` |
| `account.liquidation_price_distance_bps_before` | Distance from mark price to liquidation price in basis points, before collateral change | `derived` | Info API `clearinghouseState` → `abs(markPx - liquidationPx) / markPx × 10000` at prior snapshot | `strategic_margin_drain` |
| `account.liquidation_price_distance_bps_after` | Distance from mark price to liquidation price in basis points, after collateral change | `derived` | Info API `clearinghouseState` → `abs(markPx - liquidationPx) / markPx × 10000` at current snapshot | `strategic_margin_drain` |
| `account.baseline.destinations_entropy` | Shannon entropy of transfer destination distribution over the account's history | `derived` | Info API `userTransfers` → compute frequency distribution of destination addresses → Shannon entropy | `account_behavioral_break` |
| `account.current.destinations_entropy` | Shannon entropy of transfer destination distribution over the last 24 hours | `derived` | Info API `userTransfers` → filter to last 24h → compute frequency distribution → Shannon entropy | `account_behavioral_break` |
| `account.new_destinations_count_24h` | Number of transfer destinations in the last 24 hours that the account has never used before | `derived` | Info API `userTransfers` → compare last 24h destinations to full history → count new | `account_behavioral_break` |
| `account.bridge_count_24h` | Number of bridge-out transactions in the last 24 hours | `api_direct` | Info API `userTransfers` filtered by bridge type → count in last 24h | `account_behavioral_break` |
| `account.asset_mix_shift_score` | Score (0-1) measuring how much the account's asset allocation changed in the last 24 hours | `hypothetical` | Computed as cosine distance between current asset weight vector and 30-day average asset weight vector | `account_behavioral_break` |
| `account.transfer_urgency_score` | Score (0-1) measuring how rapidly and completely assets were moved | `hypothetical` | Composite of: fraction of total balance moved, time window of moves, number of simultaneous transfers | `account_behavioral_break` |

## cluster.* (7 inputs)

| Input name | Description | Source type | Source detail | Used by |
|---|---|---|---|---|
| `cluster.wallet_count` | Number of wallets in the identified cluster | `derived` | Funding-source analysis: group wallets by common funding origin within a time window | `coordinated_multi_wallet` |
| `cluster.common_funding_source` | Whether the wallets in the cluster share a common funding source | `derived` | Info API `userTransfers` → trace inbound transfers → check for shared origin address | `coordinated_multi_wallet` |
| `cluster.funding_window_minutes` | Time window in minutes over which the cluster wallets were funded | `derived` | Info API `userTransfers` → `max(funding_time) - min(funding_time)` across cluster | `coordinated_multi_wallet` |
| `cluster.combined_notional_usd` | Total combined position notional in USD across all cluster wallets | `derived` | Info API `clearinghouseState` per wallet in cluster → sum `positionValue` | `coordinated_multi_wallet` |
| `cluster.market_symbol` | The market symbol where the cluster is concentrated | `derived` | Info API `clearinghouseState` per wallet → identify common market | `coordinated_multi_wallet` |
| `cluster.same_direction_ratio` | Fraction of cluster wallets holding positions in the same direction (long or short) | `derived` | Info API `clearinghouseState` per wallet → count same-direction / total | `coordinated_multi_wallet` |
| `cluster.same_time_entry_ratio` | Fraction of cluster wallets that entered positions within a short time window of each other | `derived` | Info API `userFills` per wallet → check entry timestamps → fraction within 30m window | `coordinated_multi_wallet` |

## order.* (3 inputs)

| Input name | Description | Source type | Source detail | Used by |
|---|---|---|---|---|
| `order.large_order_notional_usd` | Notional USD value of a single large order on the book | `api_direct` | Info API `l2Book` or WebSocket `orderUpdates` → identify orders above threshold | `spoofing_wall_reversal` |
| `order.cancel_time_seconds` | Time in seconds between order placement and cancellation | `derived` | WebSocket `orderUpdates` → `cancel_timestamp - place_timestamp` | `spoofing_wall_reversal` |
| `order.distance_to_mid_bps` | Distance of the order price from the current mid price in basis points | `derived` | `abs(order_price - mid_price) / mid_price × 10000` | `spoofing_wall_reversal` |

## contract.* (6 inputs)

| Input name | Description | Source type | Source detail | Used by |
|---|---|---|---|---|
| `contract.has_user_callable_execute` | Whether the contract has an externally callable execute/call function | `static_analysis` | Solidity source review: scan for `external` or `public` functions that invoke `.call()`, `.delegatecall()` | `arbitrary_call_surface` |
| `contract.target_is_user_supplied` | Whether the call target address is derived from user input | `static_analysis` | Trace function parameters → check if address parameter flows to `.call()` target | `arbitrary_call_surface` |
| `contract.calldata_is_user_supplied` | Whether the calldata is constructed from user-supplied bytes | `static_analysis` | Trace function parameters → check if `bytes` parameter flows to `.call()` data | `arbitrary_call_surface` |
| `contract.allowlist_scope` | Scope of the target allowlist: `none`, `narrow` (1-3 targets), `broad` (4+), or `unrestricted` | `static_analysis` | Source review: check for allowlist mapping/array, count entries | `arbitrary_call_surface` |
| `contract.post_call_invariant_checks` | Whether the contract enforces invariants after external calls | `static_analysis` | Source review: check for balance checks, state assertions, or return-value validation after `.call()` | `arbitrary_call_surface` |
| `contract.role_required` | The access-control role required to invoke the call function | `static_analysis` | Source review: identify modifier or require statement on the function | `arbitrary_call_surface` |

## permission.* (5 inputs)

| Input name | Description | Source type | Source detail | Used by |
|---|---|---|---|---|
| `permission.role_name` | Name of the role being evaluated (e.g., operator, owner, router) | `static_analysis` | Source review: identify role definitions in access-control contracts | `operator_permission_scope_creep` |
| `permission.allowed_actions` | List of actions the role can perform | `static_analysis` | Source review: enumerate functions gated by this role's modifier | `operator_permission_scope_creep` |
| `permission.expected_actions` | List of actions the role is intended to perform based on its stated purpose | `static_analysis` | Compare role name/documentation to actual gated functions | `operator_permission_scope_creep` |
| `permission.upgradeability` | Whether the role can upgrade or modify the contract | `static_analysis` | Source review: check for upgrade functions (UUPS, proxy admin) gated by this role | `operator_permission_scope_creep` |
| `permission.can_move_user_funds` | Whether the role can transfer user tokens or modify user balances | `static_analysis` | Source review: check for transfer/approve calls gated by this role | `operator_permission_scope_creep` |

## system.* (1 input)

| Input name | Description | Source type | Source detail | Used by |
|---|---|---|---|---|
| `system.circuit_breakers_present` | Whether automated circuit breakers exist for the market or system | `hypothetical` | Not currently queryable via API; represents whether the platform has automated halt/throttle mechanisms | `crisis_centralization_trigger` |

## governance.* (1 input)

| Input name | Description | Source type | Source detail | Used by |
|---|---|---|---|---|
| `governance.manual_override_capability` | Whether validators or governance can manually intervene (delist, reprice, settle) | `hypothetical` | Not currently queryable via API; inferred from protocol documentation and observed governance behavior | `crisis_centralization_trigger` |

---

## Notes

### API references

- **Info API** — Hyperliquid's read-only API for market data, account state, and order book data. Base endpoint: `https://api.hyperliquid.xyz/info`
- **WebSocket** — Real-time data feed for trades, order updates, and liquidations. Endpoint: `wss://api.hyperliquid.xyz/ws`
- **External CEX APIs** — Used for anchor price computation. Examples: Binance (`api.binance.com`), OKX, Bybit.

### Source type distribution

| Source type | Count | Notes |
|---|---|---|
| `api_direct` | 11 | Directly queryable from Hyperliquid Info API |
| `derived` | 30 | Computed from API data using arithmetic, aggregation, or windowing |
| `static_analysis` | 11 | Determined from contract source code review |
| `hypothetical` | 4 | Not currently queryable; included for completeness |
| **Total** | **56** | |

### Conventions

- All USD values are denominated in US dollars at current mark price unless otherwise noted.
- All time windows (e.g., `_5m`, `_15m`, `_30m`, `_24h`) refer to rolling windows ending at the current timestamp.
- Basis points (bps) = `abs(a - b) / b × 10000`.
- Namespace format: `<domain>.<metric_name>`. Always use the full namespaced name in heuristic rules.
