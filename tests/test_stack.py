import sys
import os
import pytest
from fastapi import HTTPException

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api.risk_api import StackRequest, check_stack
import api.risk_api as app_module


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

