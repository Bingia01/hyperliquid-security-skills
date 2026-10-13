"""Every consistency rule of the methodology, checked mechanically.

A check belongs here if a human reviewer would otherwise have to remember it.
Errors fail CI; warnings are printed but do not.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable

from .engine import (
    THRESHOLD_PREFIX,
    CompiledRule,
    CompileError,
    Outcome,
    check_value,
    compile_rule,
    evaluate_rule,
)
from .evidence import Tier, incident_tier, rule_status
from .expressions import EvaluationError, parse
from .knowledge_base import KnowledgeBase, Problem
from .model import (
    CodeDefect,
    Expectation,
    FixtureProvenance,
    Mode,
    MoviePhase,
    SourceType,
    condition_leaves,
)

CORE_PROTOCOL_OWNER = "hypercore"


class _Collector:
    def __init__(self) -> None:
        self.problems: list[Problem] = []

    def error(self, location: str, message: str) -> None:
        self.problems.append(Problem("error", location, message))

    def warning(self, location: str, message: str) -> None:
        self.problems.append(Problem("warning", location, message))

    def missing(self, location: str, what: str, names: Iterable[str], known: Iterable[str]) -> None:
        known_set = set(known)
        unknown = [n for n in names if n not in known_set]
        if unknown:
            self.error(location, f"unknown {what}: {unknown}")


def validate(kb: KnowledgeBase) -> list[Problem]:
    out = _Collector()
    _check_ontology(kb, out)
    _check_features(kb, out)
    tiers = {incident_id: incident_tier(i) for incident_id, i in kb.incidents.items()}
    _check_incidents(kb, out, tiers)
    compiled = _check_rules(kb, out, tiers)
    _check_profiles(kb, out, compiled)
    return out.problems


def compile_all(kb: KnowledgeBase) -> dict[str, CompiledRule]:
    compiled: dict[str, CompiledRule] = {}
    for rule_id, rule in kb.rules.items():
        try:
            compiled[rule_id] = compile_rule(rule, kb.features)
        except CompileError:
            continue
    return compiled


def _loc(kb: KnowledgeBase, kind: str, key: str) -> str:
    path = kb.files.get(f"{kind}:{key}")
    return f"{path} ({key})" if path else f"{kind}:{key}"


def _check_ontology(kb: KnowledgeBase, out: _Collector) -> None:
    for primitive in kb.primitives.values():
        out.missing(
            _loc(kb, "primitives", primitive.id), "invariants", primitive.threatens, kb.invariants
        )
    for surface in kb.surfaces.values():
        out.missing(
            _loc(kb, "surfaces", surface.id),
            "control owner",
            [surface.control_owner],
            kb.control_owners,
        )


def _check_features(kb: KnowledgeBase, out: _Collector) -> None:
    for feature in kb.features.values():
        if feature.entity not in kb.entities:
            out.error(_loc(kb, "feature", feature.id), f"unknown entity {feature.entity!r}")


def _check_incidents(kb: KnowledgeBase, out: _Collector, tiers: dict[str, Tier]) -> None:
    for incident in kb.incidents.values():
        where = _loc(kb, "incidents", incident.id)
        out.missing(where, "control owner", [incident.control_owner], kb.control_owners)
        out.missing(where, "mechanisms", incident.mechanisms, kb.mechanisms)
        out.missing(where, "surfaces", incident.surfaces, kb.surfaces)
        out.missing(where, "primitives", incident.primitives, kb.primitives)
        out.missing(where, "invariants", incident.invariants_violated, kb.invariants)

        source_ids = [s.id for s in incident.sources]
        claim_ids = [c.id for c in incident.claims]
        for label, ids in (("source", source_ids), ("claim", claim_ids)):
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            if duplicates:
                out.error(where, f"duplicate {label} ids {duplicates}")
        for claim in incident.claims:
            out.missing(where, f"sources in claim {claim.id}", claim.sources, source_ids)
        for index, step in enumerate(incident.movie):
            out.missing(where, f"claims in movie step {index + 1}", step.claims, claim_ids)
        for loss in incident.losses:
            out.missing(where, f"claims in loss ({loss.bearer})", loss.claims, claim_ids)

        cited = {s for c in incident.claims for s in c.sources}
        uncited = [s for s in source_ids if s not in cited]
        if uncited:
            out.warning(where, f"sources not cited by any claim: {uncited}")
        if not any(c.core for c in incident.claims):
            out.warning(where, "no core claims; the incident defaults to research_lead")
        if not any(step.phase is MoviePhase.trigger for step in incident.movie):
            out.warning(where, "attack movie has no trigger step")

        if (
            incident.control_owner == CORE_PROTOCOL_OWNER
            and incident.code_defect is CodeDefect.present
            and tiers[incident.id] is not Tier.confirmed
        ):
            out.error(
                where,
                "claims a core-protocol code defect on evidence below 'confirmed' "
                f"(derived tier: {tiers[incident.id].value}); strengthen sources or "
                "set code_defect: undetermined",
            )

        threatened = {
            inv
            for p in incident.primitives
            if p in kb.primitives
            for inv in kb.primitives[p].threatens
        }
        unexplained = [i for i in incident.invariants_violated if i not in threatened]
        if unexplained:
            out.warning(
                where,
                f"invariants {unexplained} are violated but no listed primitive threatens them",
            )


def _check_rules(
    kb: KnowledgeBase, out: _Collector, tiers: dict[str, Tier]
) -> dict[str, CompiledRule]:
    compiled_rules: dict[str, CompiledRule] = {}
    for rule in kb.rules.values():
        where = _loc(kb, "rules", rule.id)
        out.missing(where, "surfaces", rule.applies_to, kb.surfaces)
        out.missing(where, "entities", rule.scope, kb.entities)
        out.missing(where, "primitives", rule.detects, kb.primitives)
        out.missing(where, "invariants", rule.protects, kb.invariants)
        out.missing(where, "anchor incidents", rule.anchors, kb.incidents)

        # Evidence policy: research leads can never justify paging a human, and
        # a rule may page only after it has been shown to fire on a real case.
        status = rule_status([tiers[a] for a in rule.anchors if a in tiers])
        if rule.mode is Mode.alert and status.value == "theoretical":
            out.error(
                where,
                "mode 'alert' needs an anchor incident at credible_report or better; "
                "this rule's derived status is 'theoretical' - use mode 'report'",
            )
        if rule.mode is Mode.alert and not any(
            f.expect is Expectation.fires
            and f.provenance is not FixtureProvenance.synthetic
            and f.incident in rule.anchors
            for f in rule.fixtures
        ):
            out.error(
                where,
                "mode 'alert' needs a reconstructed or recorded fixture from an anchor "
                "incident that fires; synthetic fixtures test logic, not detection",
            )
        minimum_false_positives = 2 if rule.mode is Mode.alert else 1
        if len(rule.false_positives) < minimum_false_positives:
            out.error(
                where,
                f"document at least {minimum_false_positives} false-positive scenario(s)",
            )

        # Anchors must actually exhibit what the rule detects.
        for anchor in rule.anchors:
            incident = kb.incidents.get(anchor)
            if incident and not set(rule.detects) & set(incident.primitives):
                out.error(
                    where,
                    f"anchor {anchor} exhibits none of the detected primitives {rule.detects}",
                )
        for primitive_id in rule.detects:
            primitive = kb.primitives.get(primitive_id)
            if primitive and not set(primitive.threatens) & set(rule.protects):
                out.warning(
                    where,
                    f"detected primitive {primitive_id} threatens none of the protected invariants",
                )

        try:
            compiled = compile_rule(rule, kb.features)
        except CompileError as exc:
            out.error(where, f"does not compile: {exc}")
            continue
        compiled_rules[rule.id] = compiled

        unused = sorted(set(rule.thresholds) - compiled.thresholds_used)
        if unused:
            out.error(where, f"thresholds declared but never used: {unused}")
        for leaf in condition_leaves(rule.condition):
            for node in ast.walk(parse(leaf).tree):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, (int, float))
                    and not isinstance(node.value, bool)
                    and node.value != 0
                ):
                    out.error(
                        where,
                        f"numeric literal {node.value} in condition {leaf!r}; "
                        "declare a named threshold so profiles can tune it",
                    )
        for name in compiled.features:
            feature = kb.features[name]
            if rule.mode is Mode.alert and feature.source.type is SourceType.analyst:
                out.warning(
                    where,
                    f"alert-mode rule reads analyst-only feature {name}; it cannot run unattended",
                )
        _check_fixtures(kb, out, compiled)
    return compiled_rules


def _check_fixtures(kb: KnowledgeBase, out: _Collector, compiled: CompiledRule) -> None:
    rule = compiled.rule
    where = _loc(kb, "rules", rule.id)
    seen: set[Expectation] = set()
    for fixture in rule.fixtures:
        label = f"{where} fixture {fixture.name!r}"
        if fixture.surface not in kb.surfaces:
            out.error(label, f"unknown surface {fixture.surface!r}")
            continue
        if fixture.provenance is not FixtureProvenance.synthetic and fixture.incident:
            if fixture.incident not in rule.anchors:
                out.error(label, f"reconstructs {fixture.incident}, which is not an anchor")
            incident = kb.incidents.get(fixture.incident)
            claim_ids = {c.id for c in incident.claims} if incident else set()
            for name in sorted(set(fixture.values) & compiled.features):
                claim = fixture.evidence.get(name)
                if fixture.provenance is FixtureProvenance.reconstructed and claim is None:
                    out.error(label, f"reconstructed value {name} cites no incident claim")
                elif claim is not None and claim not in claim_ids:
                    out.error(label, f"{name} cites unknown claim {claim!r}")
        bad = False
        for name, value in fixture.values.items():
            feature = kb.features.get(name)
            if feature is None:
                out.error(label, f"unknown feature {name!r}")
                bad = True
                continue
            if name not in compiled.features:
                out.warning(label, f"value for {name} is never read by the rule")
            problem = check_value(feature, value)
            if problem:
                out.error(label, f"{name}: {problem}")
                bad = True
        if bad:
            continue
        try:
            result = evaluate_rule(compiled, fixture.values, fixture.surface)
        except EvaluationError as exc:
            out.error(label, f"evaluation error: {exc}")
            continue
        if result.outcome.value != fixture.expect.value:
            detail = f" (missing: {result.missing})" if result.outcome is Outcome.unknown else ""
            out.error(
                label,
                f"expected {fixture.expect.value}, got {result.outcome.value}{detail}",
            )
        seen.add(fixture.expect)
    for needed in (Expectation.fires, Expectation.silent):
        if needed not in seen:
            out.error(where, f"needs at least one fixture expecting {needed.value!r}")
    if Expectation.unknown not in seen:
        out.warning(where, "no fixture exercises missing data (expect: unknown)")


def _check_profiles(kb: KnowledgeBase, out: _Collector, compiled: dict[str, CompiledRule]) -> None:
    by_surface: dict[str, str] = {}
    for profile in kb.profiles.values():
        where = _loc(kb, "profiles", profile.id)
        out.missing(where, "surface", [profile.surface], kb.surfaces)
        if profile.surface in by_surface:
            out.error(
                where,
                f"surface {profile.surface} already has profile {by_surface[profile.surface]}",
            )
        by_surface[profile.surface] = profile.id
        for rule_id, overrides in profile.overrides.items():
            rule = kb.rules.get(rule_id)
            if rule is None:
                out.error(where, f"overrides unknown rule {rule_id!r}")
                continue
            if profile.surface not in rule.applies_to:
                out.error(where, f"rule {rule_id} never runs on surface {profile.surface}")
            unknown = sorted(set(overrides) - set(rule.thresholds))
            if unknown:
                out.error(where, f"rule {rule_id} has no thresholds named {unknown}")


def validate_snapshot_values(kb: KnowledgeBase, values: dict[str, object]) -> list[str]:
    problems = []
    for name, value in values.items():
        if name.startswith(THRESHOLD_PREFIX):
            problems.append(f"{name}: thresholds come from rules and profiles, not snapshots")
            continue
        feature = kb.features.get(name)
        if feature is None:
            problems.append(f"{name}: unknown feature")
            continue
        problem = check_value(feature, value)
        if problem:
            problems.append(f"{name}: {problem}")
    return problems
