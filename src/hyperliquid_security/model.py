"""Typed records for every file in the knowledge base.

Every YAML file under ``knowledge/`` is parsed into one of these models.
Unknown keys are rejected (``extra="forbid"``) so that a typo in a field name
is an error, not a silently ignored field. Cross-record references (an incident
naming a primitive, a rule naming a feature) are checked in ``validate.py``.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Annotated, Any, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .units import Unit, UnitError

IDENTIFIER = r"^[a-z][a-z0-9_]*$"
INCIDENT_ID = r"^[a-z0-9][a-z0-9-]*$"
FEATURE_ID = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"

Identifier = Annotated[str, Field(pattern=IDENTIFIER)]
IncidentId = Annotated[str, Field(pattern=INCIDENT_ID)]
FeatureId = Annotated[str, Field(pattern=FEATURE_ID)]
NonEmpty = Annotated[str, Field(min_length=1)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------
# Ontology
# --------------------------------------------------------------------------


class ControlOwner(Record):
    """The party responsible for the control that failed or was exploited."""

    id: Identifier
    name: NonEmpty
    description: NonEmpty


class Mechanism(Record):
    """How value was extracted or a safety property was broken."""

    id: Identifier
    name: NonEmpty
    description: NonEmpty


class Invariant(Record):
    id: Identifier
    name: NonEmpty
    statement: NonEmpty
    rationale: NonEmpty


class PrimitiveKind(StrEnum):
    attacker_action = "attacker_action"
    system_weakness = "system_weakness"


class Primitive(Record):
    id: Identifier
    name: NonEmpty
    kind: PrimitiveKind
    description: NonEmpty
    threatens: list[Identifier] = Field(min_length=1)


class Surface(Record):
    """A deployment context that rules apply to and profiles tune for."""

    id: Identifier
    name: NonEmpty
    control_owner: Identifier
    description: NonEmpty


class Entity(Record):
    """A kind of thing a feature describes (a market, an account, ...)."""

    id: Identifier
    description: NonEmpty


# --------------------------------------------------------------------------
# Evidence and incidents
# --------------------------------------------------------------------------


class SourceTier(StrEnum):
    primary = "primary"  # the affected party, its docs, or on-chain data
    technical_secondary = "technical_secondary"  # security or chain-analytics firm
    news = "news"
    social = "social"


class Source(Record):
    id: Identifier
    title: NonEmpty
    publisher: NonEmpty
    url: Annotated[str, Field(pattern=r"^https?://\S+$")]
    tier: SourceTier
    published: dt.date | None = None


class Claim(Record):
    id: Identifier
    statement: NonEmpty
    sources: list[Identifier] = Field(min_length=1)
    core: bool = Field(
        default=False,
        description="Core claims define the incident's mechanism; the incident's "
        "evidence tier is the weakest support among its core claims.",
    )


class LossBasis(StrEnum):
    realized = "realized"
    peak_unrealized = "peak_unrealized"
    reported_unspecified = "reported_unspecified"


class Loss(Record):
    bearer: NonEmpty
    amount_usd_low: float = Field(ge=0)
    amount_usd_high: float = Field(ge=0)
    basis: LossBasis
    claims: list[Identifier] = Field(min_length=1)

    @model_validator(mode="after")
    def _ordered(self) -> Loss:
        if self.amount_usd_low > self.amount_usd_high:
            raise ValueError("amount_usd_low exceeds amount_usd_high")
        return self


class MoviePhase(StrEnum):
    preconditions = "preconditions"
    setup = "setup"
    trigger = "trigger"
    protocol_reaction = "protocol_reaction"
    amplification = "amplification"
    loss = "loss"
    response = "response"


class MovieStep(Record):
    phase: MoviePhase
    description: NonEmpty
    claims: list[Identifier] = Field(
        default_factory=list,
        description="Claims supporting this step. An empty list marks the step as inferred.",
    )


class CodeDefect(StrEnum):
    """Whether a code defect in the control owner's software enabled the loss.

    Spelled out (not yes/no) because YAML 1.1 parses bare yes/no as booleans.
    """

    present = "present"
    absent = "absent"
    undetermined = "undetermined"


class Period(Record):
    start: dt.date
    end: dt.date

    @model_validator(mode="after")
    def _ordered(self) -> Period:
        if self.start > self.end:
            raise ValueError("period start is after end")
        return self


class Incident(Record):
    id: IncidentId
    title: NonEmpty
    period: Period
    summary: NonEmpty
    control_owner: Identifier
    mechanisms: list[Identifier] = Field(min_length=1)
    code_defect: CodeDefect
    surfaces: list[Identifier] = Field(min_length=1)
    losses: list[Loss] = Field(default_factory=list)
    sources: list[Source] = Field(min_length=1)
    claims: list[Claim] = Field(min_length=1)
    movie: list[MovieStep] = Field(min_length=1)
    primitives: list[Identifier] = Field(default_factory=list)
    invariants_violated: list[Identifier] = Field(default_factory=list)
    response: str = ""
    open_questions: list[str] = Field(default_factory=list)
    citations_checked: bool = Field(
        default=False,
        description="True once a reviewer has read every cited source and confirmed "
        "it supports each claim that cites it. Derived tiers assume citations are honest; "
        "this field records whether anyone checked.",
    )


# --------------------------------------------------------------------------
# Features (the data dictionary)
# --------------------------------------------------------------------------


class FeatureKind(StrEnum):
    number = "number"
    bool = "bool"
    string = "string"
    list = "list"


class SourceType(StrEnum):
    public_api = "public_api"  # Hyperliquid public info API, computable today
    node_data = "node_data"  # needs a non-validating node or its archives
    external_market_data = "external_market_data"  # other venues' data
    static_analysis = "static_analysis"  # read from contract source or bytecode
    analyst = "analyst"  # human or model judgment; never automatic
    derived_history = "derived_history"  # needs earlier snapshots of public data


AUTOMATABLE_SOURCES = frozenset(
    {
        SourceType.public_api,
        SourceType.node_data,
        SourceType.external_market_data,
        SourceType.static_analysis,
        SourceType.derived_history,
    }
)


class FeatureSource(Record):
    type: SourceType
    detail: NonEmpty


class Feature(Record):
    id: FeatureId
    kind: FeatureKind
    unit: str | None = None
    element_kind: FeatureKind | None = None
    element_unit: str | None = None
    values: list[str] | None = None
    description: NonEmpty
    source: FeatureSource

    @property
    def entity(self) -> str:
        return self.id.split(".", 1)[0]

    @model_validator(mode="after")
    def _shape(self) -> Feature:
        if self.kind is FeatureKind.number:
            if self.unit is None:
                raise ValueError("numeric features need a unit")
            _parse_unit(self.unit)
        elif self.unit is not None:
            raise ValueError("only numeric features take a unit")
        if self.kind is FeatureKind.list:
            if self.element_kind is None:
                raise ValueError("list features need element_kind")
            if self.element_kind is FeatureKind.number:
                if self.element_unit is None:
                    raise ValueError("numeric list elements need element_unit")
                _parse_unit(self.element_unit)
        elif self.element_kind is not None or self.element_unit is not None:
            raise ValueError("element_kind/element_unit apply only to lists")
        if self.values is not None and not (
            self.kind is FeatureKind.string
            or (self.kind is FeatureKind.list and self.element_kind is FeatureKind.string)
        ):
            raise ValueError("values (a closed vocabulary) apply only to strings")
        return self


def _parse_unit(text: str) -> Unit:
    try:
        return Unit.parse(text)
    except UnitError as exc:
        raise ValueError(str(exc)) from None


# --------------------------------------------------------------------------
# Rules, fixtures, profiles
# --------------------------------------------------------------------------


class Stage(StrEnum):
    precondition = "precondition"  # exposure exists before any attack
    active_attack = "active_attack"  # attack or failure in progress
    post_loss = "post_loss"  # loss has occurred; supports response and forensics
    pre_deployment = "pre_deployment"  # code review before shipping


class Mode(StrEnum):
    report = "report"  # recorded for analysts; never pages anyone
    alert = "alert"  # pages a human; requires stronger evidence


class Severity(StrEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class ThresholdBasis(StrEnum):
    placeholder = "placeholder"  # chosen by judgment; not calibrated on data
    incident_reconstruction = "incident_reconstruction"
    calibrated = "calibrated"  # fitted on historical data with a stated method


class Threshold(Record):
    value: float
    unit: str
    basis: ThresholdBasis
    note: str = ""

    @field_validator("unit")
    @classmethod
    def _unit(cls, value: str) -> str:
        _parse_unit(value)
        return value


Condition = Union[str, "AllOf", "AnyOf", "NotOf"]


class AllOf(Record):
    all: list[Condition] = Field(min_length=1)


class AnyOf(Record):
    any: list[Condition] = Field(min_length=1)


class NotOf(Record):
    not_: Condition = Field(alias="not")

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Expectation(StrEnum):
    fires = "fires"
    silent = "silent"
    unknown = "unknown"
    not_applicable = "not_applicable"


class FixtureProvenance(StrEnum):
    synthetic = "synthetic"  # constructed to exercise logic; proves nothing about efficacy
    reconstructed = "reconstructed"  # values reconstructed from an incident's evidence
    recorded = "recorded"  # captured from live or archived data


class Fixture(Record):
    name: NonEmpty
    expect: Expectation
    provenance: FixtureProvenance
    surface: Identifier
    incident: IncidentId | None = None
    values: dict[FeatureId, Any]
    evidence: dict[FeatureId, Identifier] = Field(
        default_factory=dict,
        description="For reconstructed fixtures: the incident claim behind each value.",
    )
    note: str = ""

    @model_validator(mode="after")
    def _incident(self) -> Fixture:
        if self.provenance is FixtureProvenance.reconstructed and self.incident is None:
            raise ValueError("reconstructed fixtures must name their incident")
        if self.provenance is FixtureProvenance.synthetic and self.evidence:
            raise ValueError("synthetic fixtures cite no evidence; use provenance: reconstructed")
        return self


class FalsePositive(Record):
    scenario: NonEmpty
    distinguisher: NonEmpty


class Rule(Record):
    id: Identifier
    title: NonEmpty
    summary: NonEmpty
    stage: Stage
    mode: Mode
    severity: Severity
    consumer: NonEmpty
    action: NonEmpty
    applies_to: list[Identifier] = Field(min_length=1)
    scope: list[Identifier] = Field(
        min_length=1, description="Entities whose features the rule may read."
    )
    detects: list[Identifier] = Field(min_length=1)
    protects: list[Identifier] = Field(min_length=1)
    anchors: list[IncidentId] = Field(default_factory=list)
    thresholds: dict[Identifier, Threshold] = Field(default_factory=dict)
    condition: Condition
    report: dict[Identifier, str] = Field(default_factory=dict)
    false_positives: list[FalsePositive] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    fixtures: list[Fixture] = Field(min_length=1)


class Profile(Record):
    id: Identifier
    surface: Identifier
    description: NonEmpty
    overrides: dict[Identifier, dict[Identifier, float]] = Field(default_factory=dict)


for _model in (AllOf, AnyOf, NotOf, Rule):
    _model.model_rebuild()


def condition_leaves(condition: Condition) -> list[str]:
    """All expression strings in a condition tree, in order."""
    if isinstance(condition, str):
        return [condition]
    if isinstance(condition, AllOf):
        return [leaf for child in condition.all for leaf in condition_leaves(child)]
    if isinstance(condition, AnyOf):
        return [leaf for child in condition.any for leaf in condition_leaves(child)]
    return condition_leaves(condition.not_)
