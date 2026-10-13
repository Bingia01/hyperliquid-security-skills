"""Command-line interface: validate, report, evaluate, snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .engine import compile_rule, evaluate_rule
from .knowledge_base import KnowledgeBase, load
from .validate import validate, validate_snapshot_values


def _default_root() -> Path:
    """./knowledge when run inside a checkout, else the checkout this package came from."""
    local = Path.cwd() / "knowledge"
    return local if local.is_dir() else Path(__file__).resolve().parents[2] / "knowledge"


DEFAULT_ROOT = _default_root()


def _load_or_exit(root: Path) -> KnowledgeBase:
    kb, problems = load(root)
    if any(p.level == "error" for p in problems):
        for problem in problems:
            print(problem, file=sys.stderr)
        sys.exit(1)
    return kb


def command_validate(args: argparse.Namespace) -> int:
    kb, problems = load(args.root)
    problems += validate(kb)
    errors = [p for p in problems if p.level == "error"]
    warnings = [p for p in problems if p.level == "warning"]
    for problem in errors + (warnings if not args.quiet else []):
        print(problem)
    print(
        f"{len(kb.incidents)} incidents, {len(kb.rules)} rules, {len(kb.features)} features, "
        f"{len(kb.primitives)} primitives: {len(errors)} errors, {len(warnings)} warnings"
    )
    return 1 if errors else 0


def command_report(args: argparse.Namespace) -> int:
    from .reports import render_all

    kb = _load_or_exit(args.root)
    problems = [p for p in validate(kb) if p.level == "error"]
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    out_dir: Path = args.out
    stale = []
    for name, text in render_all(kb).items():
        path = out_dir / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    if stale:
        print("generated files are out of date; run `hyperliquid-security report`:")
        for path_text in stale:
            print(f"  {path_text}")
        return 1
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    kb = _load_or_exit(args.root)
    snapshot: dict[str, Any] = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    surface = snapshot.get("surface")
    values = snapshot.get("values", {})
    if surface not in kb.surfaces:
        print(f"snapshot surface {surface!r} is not one of {sorted(kb.surfaces)}", file=sys.stderr)
        return 1
    problems = validate_snapshot_values(kb, values)
    if problems:
        for problem in problems:
            print(f"snapshot: {problem}", file=sys.stderr)
        return 1
    profile = None
    if args.profile:
        profile = kb.profiles.get(args.profile)
        if profile is None:
            print(f"unknown profile {args.profile!r}", file=sys.stderr)
            return 1
    else:
        profile = next((p for p in kb.profiles.values() if p.surface == surface), None)
    rule_ids = args.rule or sorted(kb.rules)
    results = []
    for rule_id in rule_ids:
        rule = kb.rules.get(rule_id)
        if rule is None:
            print(f"unknown rule {rule_id!r}", file=sys.stderr)
            return 1
        compiled = compile_rule(rule, kb.features)
        use_profile = profile if profile and profile.surface == surface else None
        results.append(evaluate_rule(compiled, values, surface, use_profile).as_dict())
    if not args.all:
        results = [r for r in results if r["outcome"] != "not_applicable"]
    output = {
        "subject": snapshot.get("subject"),
        "surface": surface,
        "observed_at": snapshot.get("observed_at"),
        "results": results,
    }
    print(json.dumps(output, indent=2))
    return 0


def command_snapshot(args: argparse.Namespace) -> int:
    from .hyperliquid_api import ApiError, InfoClient, build_market_snapshot

    previous = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.previous or []]
    client = InfoClient(base_url=args.api)
    try:
        snapshot = build_market_snapshot(
            client, args.coin, dex=args.dex, previous=previous, surface=args.surface
        )
    except ApiError as exc:
        print(f"snapshot failed: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(snapshot, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


RECORDING_UNFINISHED = 3


def command_record(args: argparse.Namespace) -> int:
    from .hyperliquid_api import InfoClient
    from .recording import MeteredClient, RateLimiter, record_candle_moves, record_session

    client = MeteredClient(InfoClient(base_url=args.api), RateLimiter(args.weight_per_minute))
    if args.candles:
        if not args.out:
            print("--candles needs --out FILE", file=sys.stderr)
            return 2
        record_candle_moves(client, Path(args.out), interval=args.candle_interval)
        return 0
    if not args.out_dir:
        print("recording passes needs --out-dir DIR", file=sys.stderr)
        return 2
    complete = record_session(
        client,
        Path(args.out_dir),
        hours=args.hours,
        interval_seconds=args.interval_seconds,
        stop_after_hours=args.stop_after_hours,
    )
    return 0 if complete else RECORDING_UNFINISHED


def command_pack(args: argparse.Namespace) -> int:
    from .recording import pack

    count = pack(Path(args.directory), Path(args.output))
    print(f"wrote {count} rows to {args.output}")
    return 0 if count else 1


def command_calibrate(args: argparse.Namespace) -> int:
    import datetime as dt

    import yaml

    from .calibration import (
        calibrate_cross_sections,
        calibrate_mark_moves,
        calibrate_open_interest_growth,
        load_passes,
    )

    kb = _load_or_exit(args.root)
    computed = dt.date.fromisoformat(args.computed) if args.computed else dt.date.today()
    results = []
    if args.passes:
        archive = (
            json.loads(Path(args.archive_checks).read_text(encoding="utf-8"))
            if args.archive_checks
            else None
        )
        rows = load_passes(Path(args.passes))
        results += calibrate_cross_sections(kb, rows, computed, archive)
        results.append(calibrate_open_interest_growth(kb, rows, computed))
    if args.candles:
        anchors = (
            json.loads(Path(args.anchors).read_text(encoding="utf-8")) if args.anchors else None
        )
        results.append(calibrate_mark_moves(Path(args.candles), computed, anchors))
    out_dir = args.root / "calibration"
    out_dir.mkdir(exist_ok=True)
    for result in results:
        path = out_dir / f"{result['id']}.yaml"
        path.write_text(yaml.safe_dump(result, sort_keys=False, width=100), encoding="utf-8")
        targets = ", ".join(
            f"{t['rule']}.{t['threshold']}[{t['surface']}]={t['value']}" for t in result["targets"]
        )
        print(f"wrote {path}: {targets}")
    print("Apply the values to rules (basis: calibrated, calibration: <id>) and profiles,")
    print("then run `hyperliquid-security validate`, which checks they match.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hyperliquid-security", description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="knowledge base directory")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("validate", help="check the knowledge base; exit 1 on errors")
    p.add_argument("--quiet", action="store_true", help="hide warnings")
    p.set_defaults(func=command_validate)

    p = commands.add_parser("report", help="write generated documentation")
    p.add_argument("--out", type=Path, default=DEFAULT_ROOT.parent / "docs" / "generated")
    p.add_argument("--check", action="store_true", help="fail if generated files are stale")
    p.set_defaults(func=command_report)

    p = commands.add_parser("evaluate", help="evaluate rules against a snapshot JSON file")
    p.add_argument("snapshot")
    p.add_argument("--rule", action="append", help="rule id (repeatable); default all")
    p.add_argument("--profile", help="profile id; default: the profile for the snapshot's surface")
    p.add_argument("--all", action="store_true", help="include not_applicable results")
    p.set_defaults(func=command_evaluate)

    p = commands.add_parser("snapshot", help="build a market snapshot from the live public API")
    p.add_argument("--coin", required=True, help="e.g. ETH, or xyz:NVDA with --dex xyz")
    p.add_argument("--dex", help="HIP-3 dex name")
    p.add_argument(
        "--previous",
        action="append",
        help="earlier snapshot file (repeatable): about 5 minutes old for the mark move, "
        "about 1 hour old for open interest growth",
    )
    p.add_argument(
        "--surface",
        help="override the surface (the API does not flag hyperps; pass --surface hyperps)",
    )
    p.add_argument("--api", default="https://api.hyperliquid.xyz/info")
    p.add_argument("-o", "--output")
    p.set_defaults(func=command_snapshot)

    p = commands.add_parser(
        "record",
        help="record calibration samples from the live public API (read-only)",
        description=(
            "Record one pass over every listed perp each interval into --out-dir, for --hours. "
            "Rerunning with the same directory resumes the session. Exit status 0 means the "
            f"session is complete, {RECORDING_UNFINISHED} that it stopped early (rerun to resume)."
        ),
    )
    p.add_argument("--out-dir", help="session directory (one file per pass, plus a manifest)")
    p.add_argument("--hours", type=float, default=24.0, help="session length (new sessions)")
    p.add_argument("--interval-seconds", type=float, default=600.0)
    p.add_argument(
        "--stop-after-hours",
        type=float,
        help="end this run early, e.g. under a job time limit; the session resumes on rerun",
    )
    p.add_argument("--candles", action="store_true", help="record candle moves instead of passes")
    p.add_argument("--out", help="output JSON file for --candles")
    p.add_argument("--candle-interval", default="5m")
    p.add_argument("--weight-per-minute", type=int, default=600, help="of the 1200 per-IP budget")
    p.add_argument("--api", default="https://api.hyperliquid.xyz/info")
    p.set_defaults(func=command_record)

    p = commands.add_parser(
        "pack", help="merge a recording session's pass files into one .jsonl.gz to commit"
    )
    p.add_argument("directory")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=command_pack)

    p = commands.add_parser("calibrate", help="compute thresholds from recorded data")
    p.add_argument("--passes", help="packed passes (.jsonl.gz) or a `record` session directory")
    p.add_argument("--candles", help="JSON from `record --candles`")
    p.add_argument("--anchors", help="JSON {name: {surface, basis, moves_bps}} to check")
    p.add_argument(
        "--archive-checks",
        help="JSON {name: {surface, source, book, ticker}}: archived 20-level books to bound",
    )
    p.add_argument("--computed", help="date to stamp on results (default today)")
    p.set_defaults(func=command_calibrate)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
