from pathlib import Path

import pytest

from hyperliquid_security.knowledge_base import KnowledgeBase, load

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"


@pytest.fixture(scope="session")
def repo_kb() -> KnowledgeBase:
    kb, problems = load(KNOWLEDGE)
    assert not [p for p in problems if p.level == "error"], problems
    return kb
