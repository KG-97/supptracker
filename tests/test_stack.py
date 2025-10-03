import copy
import os
import re
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api.risk_api import StackRequest, check_stack
import api.risk_api as app_module


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "App.tsx"
STACK_PATTERN = re.compile(r"DEFAULT_STACK_EXAMPLE\s*=\s*['\"]([^'\"]+)['\"]")


def _parse_stack_example() -> list[str]:
    """Load and parse the default stack example from the frontend."""
    content = APP_PATH.read_text(encoding="utf-8")
    match = STACK_PATTERN.search(content)
    if not match:
        raise AssertionError("DEFAULT_STACK_EXAMPLE not found in App.tsx")
    tokens = re.split("[,\n]+", match.group(1))
    return [token.strip() for token in tokens if token.strip()]


@pytest.fixture(scope="module")
def dataset_snapshot():
    """Capture the baseline dataset so tests can restore it after mutation."""
    return {
        "compounds": app_module.load_compounds(),
        "interactions": app_module.load_interactions(),
        "sources": app_module.load_sources(),
    }


@pytest.fixture(autouse=True)
def restore_dataset(dataset_snapshot):
    """Reset module-level data stores before and after each test."""
    app_module.COMPOUNDS = copy.deepcopy(dataset_snapshot["compounds"])
    app_module.INTERACTIONS = copy.deepcopy(dataset_snapshot["interactions"])
    app_module.SOURCES = copy.deepcopy(dataset_snapshot["sources"])
    yield
    app_module.COMPOUNDS = copy.deepcopy(dataset_snapshot["compounds"])
    app_module.INTERACTIONS = copy.deepcopy(dataset_snapshot["interactions"])
    app_module.SOURCES = copy.deepcopy(dataset_snapshot["sources"])


def test_check_stack_with_interaction():
    app_module.COMPOUNDS = {
        "caffeine": {"id": "caffeine", "name": "Caffeine", "synonyms": []},
        "aspirin": {"id": "aspirin", "name": "Aspirin", "synonyms": []},
    }
    app_module.INTERACTIONS = [
        {
            "id": "caf-asp",
            "a": "caffeine",
            "b": "aspirin",
            "bidirectional": True,
            "mechanism": [],
            "severity": "Moderate",
            "evidence": "B",
            "effect": "",
            "action": "",
            "sources": [],
        }
    ]
    payload = StackRequest(compounds=["caffeine", "aspirin"])
    res = check_stack(payload)
    assert any(inter["a"] == "caffeine" and inter["b"] == "aspirin" for inter in res["interactions"])


def test_check_stack_unknown_compound():
    app_module.COMPOUNDS = {"caffeine": {"id": "caffeine", "name": "Caffeine", "synonyms": []}}
    payload = StackRequest(compounds=["caffeine", "unknown"])
    with pytest.raises(HTTPException):
        check_stack(payload)


def test_default_stack_example_executes_successfully():
    stack_compounds = _parse_stack_example()
    payload = StackRequest(compounds=stack_compounds)
    result = check_stack(payload)

    assert "interactions" in result
    assert isinstance(result["interactions"], list)
    # Every compound from the example should resolve against the dataset
    resolved_ids = [app_module.resolve_compound(name) for name in stack_compounds]
    assert all(resolved_ids), f"Unresolved compounds in default stack: {stack_compounds}"

