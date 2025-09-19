import sys
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api.risk_api as risk_api


def make_inter(severity="Moderate", evidence="B", mechanism=None):
    return {
        "severity": severity,
        "evidence": evidence,
        "mechanism": mechanism or [],
    }


def test_compute_risk_order():
    high = risk_api.compute_risk(make_inter(severity="Severe", evidence="A"))
    low = risk_api.compute_risk(make_inter(severity="Mild", evidence="D"))
    assert high > low


def test_load_rules_custom_values(monkeypatch, tmp_path):
    config_path = tmp_path / "rules.yaml"
    config_path.write_text(
        """
mechanisms:
  custom:
    delta: 2.5
weights:
  severity: 2.0
  evidence: 1.5
  mechanism: 0.5
map:
  severity:
    Severe: 5
  evidence:
    A: 1
""",
        encoding="utf-8",
    )

    mechs, weights, severity_map, evidence_map = risk_api.load_rules(str(config_path))
    assert mechs["custom"] == 2.5
    assert weights["severity"] == 2.0
    assert severity_map["Severe"] == 5
    assert evidence_map["A"] == 1

    monkeypatch.setattr(risk_api, "MECHANISM_DELTAS", mechs)
    monkeypatch.setattr(risk_api, "WEIGHTS", weights)
    monkeypatch.setattr(risk_api, "SEVERITY_MAP", severity_map)
    monkeypatch.setattr(risk_api, "EVIDENCE_MAP", evidence_map)

    score = risk_api.compute_risk(
        {
            "severity": "Severe",
            "evidence": "A",
            "mechanism": ["custom"],
        }
    )

    expected = (
        severity_map["Severe"] * weights["severity"]
        + (1 / evidence_map["A"]) * weights["evidence"]
        + mechs["custom"] * weights["mechanism"]
    )
    assert score == round(expected, 2)


def test_load_rules_missing_file(tmp_path):
    missing_path = tmp_path / "missing.yaml"
    mechs, weights, severity_map, evidence_map = risk_api.load_rules(str(missing_path))
    assert mechs == risk_api.DEFAULT_MECHANISM_DELTAS
    assert weights == risk_api.DEFAULT_WEIGHTS
    assert severity_map == risk_api.DEFAULT_SEVERITY_MAP
    assert evidence_map == risk_api.DEFAULT_EVIDENCE_MAP


def test_load_rules_malformed_file(tmp_path):
    bad_path = tmp_path / "rules.yaml"
    bad_path.write_text("mechanisms: [\n", encoding="utf-8")
    mechs, weights, severity_map, evidence_map = risk_api.load_rules(str(bad_path))
    assert mechs == risk_api.DEFAULT_MECHANISM_DELTAS
    assert weights == risk_api.DEFAULT_WEIGHTS
    assert severity_map == risk_api.DEFAULT_SEVERITY_MAP
    assert evidence_map == risk_api.DEFAULT_EVIDENCE_MAP


