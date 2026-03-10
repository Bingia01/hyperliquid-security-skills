# Threshold profiles

These profiles tune the same heuristic library for different Hyperliquid surfaces.

- `core_perps.yaml`: core exchange markets with stronger anchors and deeper liquidity.
- `hip3_markets.yaml`: builder-deployed perpetuals with stricter pricing and settlement assumptions.
- `hip4_style_markets.yaml`: bounded-outcome / prediction-style markets where settlement cliffs matter more than leverage cascades.
- `hyperevm_apps.yaml`: app-layer permission and router risk. See `docs/architecture/hyperevm_vulnerability_taxonomy.md` for the full taxonomy of HyperEVM smart contract vulnerabilities.

This repository intentionally stops at **declarative thresholds**. It does **not** ship closed-source simulation, attack-graph scoring, or executable detection engines.
