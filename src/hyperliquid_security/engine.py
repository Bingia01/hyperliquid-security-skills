"""Compile and evaluate rules against snapshots of feature values.

Outcomes are explicit and never collapsed:

* ``fires``          - the condition is true;
* ``silent``         - the condition is false on the data provided;
* ``unknown``        - required data was missing, so no conclusion is possible;
* ``not_applicable`` - the snapshot's surface is outside the rule's scope.

Treating missing data as "silent" is the most dangerous failure mode of a
detector (it reports safety it never measured), so ``unknown`` is reported
with the list of missing features.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Union

from .expressions import (
    BOOL,
    UNKNOWN,
    EvaluationError,
    Expression,
    Kind,
    Type,
    Value,
    check,
    evaluate,
    kleene_and,
    kleene_not,
    kleene_or,
    number,
    parse,
)
from .model import AllOf, AnyOf, Condition, Feature, FeatureKind, Profile, Rule
from .units import Unit

THRESHOLD_PREFIX = "threshold."


class Outcome(StrEnum):
    fires = "fires"
    silent = "silent"
    unknown = "unknown"
    not_applicable = "not_applicable"


# --------------------------------------------------------------------------
# Compilation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CompiledAll:
    children: tuple[CompiledCondition, ...]


@dataclass(frozen=True)
class CompiledAny:
    children: tuple[CompiledCondition, ...]


@dataclass(frozen=True)
class CompiledNot:
    child: CompiledCondition


CompiledCondition = Union[Expression, CompiledAll, CompiledAny, CompiledNot]


@dataclass(frozen=True)
class CompiledRule:
    rule: Rule
    condition: CompiledCondition
    report: dict[str, Expression]
    features: frozenset[str]
    thresholds_used: frozenset[str]


def feature_type(feature: Feature) -> Type:
    if feature.kind is FeatureKind.number:
        assert feature.unit is not None
        return number(Unit.parse(feature.unit))
    if feature.kind is FeatureKind.bool:
        return BOOL
    values = frozenset(feature.values) if feature.values else None
    if feature.kind is FeatureKind.string:
        return Type(Kind.STRING, values=values)
    assert feature.element_kind is not None
    if feature.element_kind is FeatureKind.number:
        assert feature.element_unit is not None
        element = number(Unit.parse(feature.element_unit))
    elif feature.element_kind is FeatureKind.bool:
        element = BOOL
    else:
        element = Type(Kind.STRING, values=values)
    return Type(Kind.LIST, element=element)


def make_resolver(rule: Rule, features: Mapping[str, Feature]) -> Any:
    def resolve(name: str) -> Type | None:
        if name.startswith(THRESHOLD_PREFIX):
            threshold = rule.thresholds.get(name[len(THRESHOLD_PREFIX) :])
            return number(Unit.parse(threshold.unit)) if threshold else None
        feature = features.get(name)
        if feature is None or feature.entity not in rule.scope:
            return None
        return feature_type(feature)

    return resolve


class CompileError(ValueError):
    pass


def compile_rule(rule: Rule, features: Mapping[str, Feature]) -> CompiledRule:
    """Parse and type-check every expression; raise CompileError on any defect."""
    resolve = make_resolver(rule, features)
    references: set[str] = set()

    def build(condition: Condition) -> CompiledCondition:
        if isinstance(condition, str):
            expression = parse(condition)
            out_of_scope = [
                r
                for r in expression.references
                if not r.startswith(THRESHOLD_PREFIX)
                and r in features
                and features[r].entity not in rule.scope
            ]
            if out_of_scope:
                raise CompileError(f"{out_of_scope} are outside the rule's scope {rule.scope}")
            found = check(expression, resolve)
            if found.kind is not Kind.BOOL:
                raise CompileError(f"condition {condition!r} is {found.describe()}, not bool")
            references.update(expression.references)
            return expression
        if isinstance(condition, AllOf):
            return CompiledAll(tuple(build(c) for c in condition.all))
        if isinstance(condition, AnyOf):
            return CompiledAny(tuple(build(c) for c in condition.any))
        return CompiledNot(build(condition.not_))

    try:
        compiled_condition = build(rule.condition)
        report: dict[str, Expression] = {}
        for name, source in rule.report.items():
            expression = parse(source)
            check(expression, resolve)
            references.update(expression.references)
            report[name] = expression
    except (ValueError, KeyError) as exc:
        raise CompileError(str(exc)) from None
    thresholds = {r[len(THRESHOLD_PREFIX) :] for r in references if r.startswith(THRESHOLD_PREFIX)}
    return CompiledRule(
        rule=rule,
        condition=compiled_condition,
        report=report,
        features=frozenset(r for r in references if not r.startswith(THRESHOLD_PREFIX)),
        thresholds_used=frozenset(thresholds),
    )


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------


@dataclass
class RuleResult:
    rule_id: str
    outcome: Outcome
    missing: list[str] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    profile: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule_id,
            "outcome": self.outcome.value,
            "missing": self.missing,
            "report": self.report,
            "thresholds": self.thresholds,
            "profile": self.profile,
        }


def check_value(feature: Feature, value: Any) -> str | None:
    """Return a description of a type error, or None if ``value`` fits ``feature``."""
    if value is None:
        return None
    kind = feature.kind
    if kind is FeatureKind.number:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"expected a number, got {value!r}"
    elif kind is FeatureKind.bool:
        if not isinstance(value, bool):
            return f"expected a boolean, got {value!r}"
    elif kind is FeatureKind.string:
        if not isinstance(value, str):
            return f"expected a string, got {value!r}"
        if feature.values is not None and value not in feature.values:
            return f"{value!r} is not one of {feature.values}"
    else:
        if not isinstance(value, list):
            return f"expected a list, got {value!r}"
        assert feature.element_kind is not None
        element_feature = Feature(
            id=feature.id,
            kind=feature.element_kind,
            unit=feature.element_unit,
            values=feature.values,
            description=feature.description,
            source=feature.source,
        )
        for item in value:
            problem = check_value(element_feature, item)
            if problem or item is None:
                return f"list element: {problem or 'null is not allowed'}"
    return None


def effective_thresholds(rule: Rule, profile: Profile | None) -> dict[str, float]:
    values = {name: t.value for name, t in rule.thresholds.items()}
    if profile is not None:
        values.update(profile.overrides.get(rule.id, {}))
    return values


def evaluate_rule(
    compiled: CompiledRule,
    values: Mapping[str, Any],
    surface: str,
    profile: Profile | None = None,
) -> RuleResult:
    rule = compiled.rule
    if surface not in rule.applies_to:
        return RuleResult(rule.id, Outcome.not_applicable)
    if profile is not None and profile.surface != surface:
        raise ValueError(f"profile {profile.id} is for {profile.surface}, not {surface}")
    thresholds = effective_thresholds(rule, profile)
    missing: set[str] = set()

    def lookup(name: str) -> Value:
        if name.startswith(THRESHOLD_PREFIX):
            return thresholds[name[len(THRESHOLD_PREFIX) :]]
        value = values.get(name)
        if value is None:
            missing.add(name)
            return UNKNOWN
        result: Value = value
        return result

    def run(condition: CompiledCondition) -> Value:
        if isinstance(condition, Expression):
            return evaluate(condition, lookup)
        if isinstance(condition, CompiledAll):
            return kleene_and([run(c) for c in condition.children])
        if isinstance(condition, CompiledAny):
            return kleene_or([run(c) for c in condition.children])
        return kleene_not(run(condition.child))

    verdict = run(compiled.condition)
    report_values: dict[str, Any] = {}
    for name, expression in compiled.report.items():
        report_values[name] = _jsonable(evaluate(expression, lookup))
    if verdict is UNKNOWN:
        outcome = Outcome.unknown
    elif verdict is True:
        outcome = Outcome.fires
    elif verdict is False:
        outcome = Outcome.silent
    else:  # pragma: no cover - type checker guarantees bool
        raise EvaluationError(f"rule {rule.id} produced non-boolean {verdict!r}")
    return RuleResult(
        rule_id=rule.id,
        outcome=outcome,
        missing=sorted(missing),
        report=report_values,
        thresholds={k: thresholds[k] for k in sorted(compiled.thresholds_used)},
        profile=profile.id if profile else None,
    )


def _jsonable(value: Value) -> Any:
    if value is UNKNOWN:
        return None
    if isinstance(value, float):
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return round(value, 6)
    return value
