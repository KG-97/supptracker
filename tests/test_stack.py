import sys
import os
import pytest
from fastapi import HTTPException

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import stack_check
import pytest

def test_stack_check_bad_payload():
    with pytest.raises(Exception):
        stack_check({})

def test_stack_check_empty_items():
    with pytest.raises(Exception):
        stack_check({"items": []})

# If stub data contains fewer items, skip a full positive stack test
def test_stack_check_basic_skip_if_insufficient():
    # We only run a positive test if there are at least 2 compounds in the COMPOUNDS fixture
    from app import COMPOUNDS
    if len(COMPOUNDS) < 2:
        pytest.skip("Not enough compounds in stub data for stack_check positive test")
    items = [COMPOUNDS[0]["id"], COMPOUNDS[1]["id"]]
    res = stack_check({"items": items})
    assert "items" in res and "matrix" in res
