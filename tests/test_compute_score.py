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


def test_compute_risk_splits_pipe_delimited_mechanisms(monkeypatch):
    mechanism_weight = 1.0
    monkeypatch.setattr(
        risk_api,
        "WEIGHTS",
        {**risk_api.WEIGHTS, "severity": 0.0, "evidence": 0.0, "mechanism": mechanism_weight},
    )
    inter = make_inter(
        severity="None",
        evidence="D",
        mechanism=["serotonergic|CYP3A4_induction"],
    )
    score = risk_api.compute_risk(inter)
    expected = round(
        (
            risk_api.MECHANISM_DELTAS["serotonergic"]
            + risk_api.MECHANISM_DELTAS["CYP3A4_induction"]
        )
        * mechanism_weight,
        2,
    )
    assert score == expected

def test_load_rules_custom_values(tmp_path):
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
formula: "severity * weights.severity + mech_sum + max(0, evidence_component)"
""",
        encoding="utf-8",
    )
    mechs, weights, severity_map, evidence_map, formula, formula_source = risk_api.load_rules(str(config_path))
    assert mechs["custom"] == 2.5
    assert weights["severity"] == 2.0
    assert severity_map["Severe"] == 5
    assert evidence_map["A"] == 1
    assert callable(formula)
    assert formula_source.strip().startswith("severity * weights.severity")
    try:
        risk_api.apply_rules(str(config_path))
        score = risk_api.compute_risk(
            {
                "severity": "Severe",
                "evidence": "A",
                "mechanism": ["custom"],
            }
        )
    finally:
        risk_api.apply_rules()
    expected = (
        severity_map["Severe"] * weights["severity"]
        + mechs["custom"]
        + max(0, (1 / evidence_map["A"]) * weights["evidence"])
    )
    assert score == round(expected, 2)

def test_load_rules_missing_file(tmp_path):
    missing_path = tmp_path / "missing.yaml"
    mechs, weights, severity_map, evidence_map, formula, formula_source = risk_api.load_rules(str(missing_path))
    assert mechs == risk_api.DEFAULT_MECHANISM_DELTAS
    assert weights == risk_api.DEFAULT_WEIGHTS
    assert severity_map == risk_api.DEFAULT_SEVERITY_MAP
    assert evidence_map == risk_api.DEFAULT_EVIDENCE_MAP
    assert formula is risk_api._default_formula
    assert formula_source == risk_api.DEFAULT_FORMULA_SOURCE

def test_load_rules_malformed_file(tmp_path):
    bad_path = tmp_path / "rules.yaml"
    bad_path.write_text("mechanisms: [\n", encoding="utf-8")
    mechs, weights, severity_map, evidence_map, formula, formula_source = risk_api.load_rules(str(bad_path))
    assert mechs == risk_api.DEFAULT_MECHANISM_DELTAS
    assert weights == risk_api.DEFAULT_WEIGHTS
    assert severity_map == risk_api.DEFAULT_SEVERITY_MAP
    assert evidence_map == risk_api.DEFAULT_EVIDENCE_MAP
    assert formula is risk_api._default_formula
    assert formula_source == risk_api.DEFAULT_FORMULA_SOURCE

def test_compute_risk_uses_overridden_default_evidence(monkeypatch, tmp_path):
    config_path = tmp_path / "rules.yaml"
    config_path.write_text(
        """
map:
  evidence:
    D: 10
""",
        encoding="utf-8",
    )
    _, _, _, evidence_map, _, _ = risk_api.load_rules(str(config_path))
    assert evidence_map["D"] == 10
    assert "Z" not in evidence_map
    monkeypatch.setattr(risk_api, "EVIDENCE_MAP", evidence_map)
    score = risk_api.compute_risk(make_inter(severity="None", evidence="Z"))
    evidence_weight = risk_api.WEIGHTS.get(
        "evidence", risk_api.DEFAULT_WEIGHTS["evidence"]
    )
    expected = round((1 / evidence_map["D"]) * evidence_weight, 2)
    assert score == expected
