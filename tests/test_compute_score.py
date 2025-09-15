import sys
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api.risk_api import compute_risk


def make_inter(severity="Moderate", evidence="B", mechanism=None):
    return {
        "severity": severity,
        "evidence": evidence,
        "mechanism": mechanism or [],
    }


def test_compute_risk_order():
    high = compute_risk(make_inter(severity="Severe", evidence="A"))
    low = compute_risk(make_inter(severity="Mild", evidence="D"))
    assert high > low


