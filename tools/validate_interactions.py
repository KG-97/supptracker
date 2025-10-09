#!/usr/bin/env python3
from __future__ import annotations
import sys, yaml, pandas as pd
from pathlib import Path

def main(compounds_csv="data/compounds.csv", interactions_dir="data/interactions.d") -> int:
    comp = Path(compounds_csv)
    idir = Path(interactions_dir)
    if not comp.exists() or not idir.exists():
        print(f"[err] missing {comp} or {idir}")
        return 1
    df = pd.read_csv(comp)
    known = set(df["id"].astype(str).str.lower())
    errs = 0
    for yml in sorted(idir.glob("*.yaml")):
        y = yaml.safe_load(open(yml,"r",encoding="utf-8")) or {}
        a = str(y.get("compound_a","")).lower()
        b = str(y.get("compound_b","")).lower()
        if a not in known:
            print(f"[err] {yml.name}: compound_a '{a}' not in compounds.csv"); errs += 1
        if b not in known:
            print(f"[err] {yml.name}: compound_b '{b}' not in compounds.csv"); errs += 1
        sev = (y.get("severity") or "None").title()
        evd = (y.get("evidence_grade") or "D").upper()
        if sev not in {"None","Mild","Moderate","Severe"}:
            print(f"[warn] {yml.name}: unusual severity '{sev}'")
        if evd not in {"A","B","C","D"}:
            print(f"[warn] {yml.name}: unusual evidence grade '{evd}'")
    return 0 if errs==0 else 2

if __name__ == "__main__":
    raise SystemExit(main(*(sys.argv[1:4])))
