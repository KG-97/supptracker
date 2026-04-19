import sys
import os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import compute_score

def make_inter(severity="Moderate", evidence_grade="B", mechanism_tags=None):
    return {
        "severity": severity,
        "evidence_grade": evidence_grade,
        "mechanism_tags": mechanism_tags or "",
    }

def test_compute_score_bucket_low():
    inter = make_inter(severity="None", evidence_grade="D")
    score, bucket, action = compute_score(inter)
    assert bucket == "No meaningful interaction"

def test_compute_score_bucket_high():
    inter = make_inter(severity="Severe", evidence_grade="A", mechanism_tags="m1;m2;m3")
    score, bucket, action = compute_score(inter)
    assert bucket in ("High", "Caution")

def test_compute_score_score_range():
    inter = make_inter(severity="Mild", evidence_grade="C")
    score, bucket, action = compute_score(inter)
    assert 0.0 <= score <= 10.0
