"""Load the knowledge base from ``knowledge/`` into typed records.

Loading never stops at the first bad file: each file is parsed independently,
failures become ``Problem`` entries, and everything that did parse is returned
so that validation can report every defect in one pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from .model import (
    CalibrationResult,
    ControlOwner,
    Entity,
    Feature,
    Incident,
    Invariant,
    Mechanism,
    Primitive,
    Profile,
    Rule,
    Surface,
)


@dataclass(frozen=True)
class Problem:
    level: str  # "error" or "warning"
    location: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper()}: {self.location}: {self.message}"


@dataclass
class KnowledgeBase:
    root: Path
    control_owners: dict[str, ControlOwner] = field(default_factory=dict)
    mechanisms: dict[str, Mechanism] = field(default_factory=dict)
    invariants: dict[str, Invariant] = field(default_factory=dict)
    primitives: dict[str, Primitive] = field(default_factory=dict)
    surfaces: dict[str, Surface] = field(default_factory=dict)
    entities: dict[str, Entity] = field(default_factory=dict)
    features: dict[str, Feature] = field(default_factory=dict)
    incidents: dict[str, Incident] = field(default_factory=dict)
    rules: dict[str, Rule] = field(default_factory=dict)
    profiles: dict[str, Profile] = field(default_factory=dict)
    calibrations: dict[str, CalibrationResult] = field(default_factory=dict)
    files: dict[str, Path] = field(default_factory=dict)  # "rule:<id>" -> path


# --------------------------------------------------------------------------
# A stricter YAML loader
# --------------------------------------------------------------------------


class StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate keys and parses 1e6 as a float."""


def _mapping_without_duplicates(loader: StrictLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r}", key_node.start_mark
            )
        seen.add(key)
    loader.flatten_mapping(node)
    return dict(loader.construct_pairs(node))


StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping_without_duplicates
)
StrictLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^[-+]?(?:[0-9][0-9_]*)(?:\.[0-9_]*)?[eE][-+]?[0-9]+$"),
    list("-+0123456789"),
)


def read_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return yaml.load(handle, Loader=StrictLoader)  # noqa: S506 - SafeLoader subclass


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

M = TypeVar("M", bound=BaseModel)

ONTOLOGY_FILES: dict[str, type[BaseModel]] = {
    "control_owners": ControlOwner,
    "mechanisms": Mechanism,
    "invariants": Invariant,
    "primitives": Primitive,
    "surfaces": Surface,
    "entities": Entity,
}


def _record_id(record: BaseModel) -> str:
    """Every top-level knowledge record has an ``id`` field (enforced by the models)."""
    return str(record.model_dump(include={"id"})["id"])


def _describe(error: ValidationError) -> str:
    parts = []
    for item in error.errors():
        where = ".".join(str(p) for p in item["loc"]) or "<root>"
        parts.append(f"{where}: {item['msg']}")
    return "; ".join(parts)


def _load_list(
    path: Path, model: type[M], problems: list[Problem], kb: KnowledgeBase, kind: str
) -> list[M]:
    try:
        raw = read_yaml(path)
    except (OSError, yaml.YAMLError) as exc:
        problems.append(Problem("error", str(path), f"cannot parse YAML: {exc}"))
        return []
    if not isinstance(raw, list):
        problems.append(Problem("error", str(path), "expected a YAML list"))
        return []
    records: list[M] = []
    for index, item in enumerate(raw):
        try:
            record = model.model_validate(item)
        except ValidationError as exc:
            problems.append(Problem("error", f"{path}[{index}]", _describe(exc)))
            continue
        records.append(record)
        kb.files[f"{kind}:{_record_id(record)}"] = path
    return records


def _load_one(path: Path, model: type[M], problems: list[Problem]) -> M | None:
    try:
        raw = read_yaml(path)
    except (OSError, yaml.YAMLError) as exc:
        problems.append(Problem("error", str(path), f"cannot parse YAML: {exc}"))
        return None
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        problems.append(Problem("error", str(path), _describe(exc)))
        return None


def _index(records: list[M], kind: str, problems: list[Problem], where: str) -> dict[str, M]:
    out: dict[str, M] = {}
    for record in records:
        key = _record_id(record)
        if key in out:
            problems.append(Problem("error", where, f"duplicate {kind} id {key!r}"))
            continue
        out[key] = record
    return out


def load(root: Path) -> tuple[KnowledgeBase, list[Problem]]:
    root = Path(root)
    kb = KnowledgeBase(root=root)
    problems: list[Problem] = []
    ontology = root / "ontology"
    for name, model in ONTOLOGY_FILES.items():
        path = ontology / f"{name}.yaml"
        if not path.exists():
            problems.append(Problem("error", str(path), "missing ontology file"))
            continue
        records = _load_list(path, model, problems, kb, name)
        setattr(kb, name, _index(records, name, problems, str(path)))

    features_path = root / "features.yaml"
    if features_path.exists():
        features = _load_list(features_path, Feature, problems, kb, "feature")
        kb.features = _index(features, "feature", problems, str(features_path))
    else:
        problems.append(Problem("error", str(features_path), "missing features file"))

    for directory, model, attr in (
        ("incidents", Incident, "incidents"),
        ("rules", Rule, "rules"),
        ("profiles", Profile, "profiles"),
        ("calibration", CalibrationResult, "calibrations"),
    ):
        records_by_id: dict[str, Any] = {}
        for path in sorted((root / directory).glob("*.yaml")):
            record = _load_one(path, model, problems)
            if record is None:
                continue
            key = _record_id(record)
            if path.stem != key:
                problems.append(Problem("error", str(path), f"file name must match id {key!r}"))
            if key in records_by_id:
                problems.append(Problem("error", str(path), f"duplicate id {key!r}"))
                continue
            records_by_id[key] = record
            kb.files[f"{attr}:{key}"] = path
        setattr(kb, attr, records_by_id)
    return kb, problems
