import sys
import os
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api.risk_api as app_module


def test_resolve_compound():
    app_module.COMPOUNDS = {
        "caffeine": {"id": "caffeine", "name": "Caffeine", "synonyms": ["coffee"]}
    }
    assert app_module.resolve_compound("coffee") == "caffeine"
    assert app_module.resolve_compound("unknown") is None


def test_compute_risk_returns_float():
    inter = {"severity": "Mild", "evidence": "C", "mechanism": []}
    score = app_module.compute_risk(inter)
    assert isinstance(score, float)

