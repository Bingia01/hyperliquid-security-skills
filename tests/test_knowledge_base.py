"""The repository's own knowledge base is a test subject: it must validate cleanly."""

import json
from pathlib import Path

import pytest
import yaml

from hyperliquid_security.knowledge_base import KnowledgeBase, StrictLoader, load
from hyperliquid_security.reports import render_all
from hyperliquid_security.validate import validate, validate_snapshot_values

from .conftest import KNOWLEDGE, ROOT


def test_repository_knowledge_base_has_no_errors(repo_kb: KnowledgeBase) -> None:
    errors = [p for p in validate(repo_kb) if p.level == "error"]
    assert errors == []


def test_generated_docs_are_up_to_date(repo_kb: KnowledgeBase) -> None:
    for name, text in render_all(repo_kb).items():
        path = ROOT / "docs" / "generated" / name
        assert path.exists(), f"missing {path}; run `hyperliquid-security report`"
        assert path.read_text(encoding="utf-8") == text, (
            f"{path} is stale; run `hyperliquid-security report`"
        )


def test_strict_loader_rejects_duplicate_keys() -> None:
    with pytest.raises(yaml.YAMLError, match="duplicate key"):
        yaml.load("a: 1\na: 2\n", Loader=StrictLoader)


def test_strict_loader_reads_exponent_floats() -> None:
    assert yaml.load("x: 1e6\ny: 2.5e-3\n", Loader=StrictLoader) == {"x": 1e6, "y": 2.5e-3}
    # PyYAML's default loader reads "1e6" as a string; this is why StrictLoader exists.
    assert yaml.safe_load("x: 1e6") == {"x": "1e6"}


def test_loader_reports_bad_files_without_stopping(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    (root / "ontology").mkdir(parents=True)
    for name in (
        "control_owners",
        "mechanisms",
        "invariants",
        "primitives",
        "surfaces",
        "entities",
    ):
        (root / "ontology" / f"{name}.yaml").write_text(
            (KNOWLEDGE / "ontology" / f"{name}.yaml").read_text(encoding="utf-8"), encoding="utf-8"
        )
    (root / "features.yaml").write_text(
        (KNOWLEDGE / "features.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (root / "rules").mkdir()
    (root / "rules" / "broken.yaml").write_text("id: broken\nunknown_field: 1\n", encoding="utf-8")
    (root / "rules" / "dup.yaml").write_text("a: 1\na: 2\n", encoding="utf-8")
    good = KNOWLEDGE / "rules" / "mark_diverges_from_oracle.yaml"
    (root / "rules" / "renamed.yaml").write_text(good.read_text(encoding="utf-8"), encoding="utf-8")
    kb, problems = load(root)
    messages = " ".join(str(p) for p in problems)
    assert "unknown_field" in messages
    assert "duplicate key" in messages
    assert "file name must match id" in messages
    assert "mark_diverges_from_oracle" in kb.rules


@pytest.mark.parametrize(
    "path",
    sorted(p for p in (ROOT / "examples").glob("*.json") if not p.name.startswith("evaluation")),
)
def test_example_snapshots_match_the_feature_dictionary(repo_kb: KnowledgeBase, path: Path) -> None:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    assert snapshot["surface"] in repo_kb.surfaces
    assert validate_snapshot_values(repo_kb, snapshot["values"]) == []
