import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.synonyms import parse_synonyms


def test_parse_synonyms_handles_various_delimiters():
    value = "Coffee; tea | matcha / yerba mate"
    assert parse_synonyms(value) == [
        "Coffee",
        "tea",
        "matcha",
        "yerba mate",
    ]


def test_parse_synonyms_preserves_parenthetical_aliases():
    value = "Vitamin K2 (MK-7, menaquinone-7)"
    assert parse_synonyms(value) == [
        "Vitamin K2",
        "MK-7",
        "menaquinone-7",
    ]


def test_parse_synonyms_ignores_numeric_commas():
    value = '"1,3,7-trimethylxanthine"'
    assert parse_synonyms(value) == ["1,3,7-trimethylxanthine"]


def test_parse_synonyms_flattens_nested_iterables():
    value = ["Coffee", ["Tea", "Tea"], {"alt": "matcha"}, ("yerba", "mate")]
    assert parse_synonyms(value) == ["Coffee", "Tea", "matcha", "yerba", "mate"]


def test_parse_synonyms_understands_json_strings():
    value = '["Coffee", "Tea", "Tea"]'
    assert parse_synonyms(value) == ["Coffee", "Tea"]

