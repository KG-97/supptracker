import sys
import os
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api.risk_api as app_module


def test_resolve_compound(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "COMPOUNDS",
        {"caffeine": {"id": "caffeine", "name": "Caffeine", "synonyms": ["coffee"]}},
    )
    assert app_module.resolve_compound("coffee") == "caffeine"
    assert app_module.resolve_compound("unknown") is None


def test_resolve_compound_with_comma_synonyms(tmp_path, monkeypatch):
    csv_content = (
        "id,name,synonyms\n"
        "st_johns_wort,St. John's Wort,\"St. John's Wort, Hypericum\"\n"
    )
    (tmp_path / "compounds.csv").write_text(csv_content)

    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    compounds = app_module.load_compounds()
    monkeypatch.setattr(app_module, "COMPOUNDS", compounds)

    assert compounds["st_johns_wort"]["synonyms"] == ["St. John's Wort", "Hypericum"]
    assert app_module.resolve_compound("hypericum") == "st_johns_wort"


def test_compute_risk_returns_float():
    inter = {"severity": "Mild", "evidence": "C", "mechanism": []}
    score = app_module.compute_risk(inter)
    assert isinstance(score, float)

