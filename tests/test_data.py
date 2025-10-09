import os, sys, pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def test_compounds_csv_exists():
    path = DATA / "compounds.csv"
    assert path.exists(), "compile_compounds.py must produce data/compounds.csv"


def test_compounds_schema():
    df = pd.read_csv(DATA / "compounds.csv")
    cols = set(df.columns)
    for req in ["id","name","synonyms","class","route","dose"]:
        assert req in cols, f"missing column {req}"


def test_synonyms_format():
    df = pd.read_csv(DATA / "compounds.csv")
    assert df["synonyms"].map(lambda s: isinstance(s, str)).all()
