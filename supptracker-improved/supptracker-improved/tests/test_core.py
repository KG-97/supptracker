import sys
import os
import pytest

# Ensure repo root is on sys.path so tests can import top-level modules like `app`
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import compute_score, search_compounds, find_interaction, COMPOUNDS, INTERACTIONS

def test_search_compounds_found():
    # Expect that the stub data contains 'caffeine' per earlier setup
    hits = search_compounds('caffeine')
    assert isinstance(hits, list)
    assert any(h['id'] == 'caffeine' for h in hits)

def test_search_compounds_notfound():
    hits = search_compounds('nonexistent-xyz')
    assert hits == []

def test_find_interaction_none():
    # Use two items unlikely to have an interaction in stub data
    assert find_interaction('caffeine', 'nonexistent-xyz') is None

def test_compute_score_returns_tuple():
    # If there is at least one interaction in INTERACTIONS, test compute_score shape
    if len(INTERACTIONS) > 0:
        inter = INTERACTIONS[0]
        score, bucket, action = compute_score(inter)
        assert isinstance(score, float)
        assert isinstance(bucket, str)
        assert isinstance(action, str)
    else:
        pytest.skip("No interactions available in stub data")
