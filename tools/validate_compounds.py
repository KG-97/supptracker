#!/usr/bin/env python3
from __future__ import annotations
import sys, json, yaml, pandas as pd
from pathlib import Path

MUST = ["id","name","class","route","dose"]
ROUTES = {"oral","sublingual","topical","transdermal","injection","inhaled","ophthalmic","other"}

def validate_yaml_dir(dir_path: str = "data/compounds.d") -> int:
    base = Path(dir_path)
    n_err = 0
    if not base.exists():
        print(f"[err] {base} does not exist"); return 1
    for yml in sorted(base.glob("*.yaml")):
        y = yaml.safe_load(open(yml,"r",encoding="utf-8")) or {}
        for k in MUST:
            if not str(y.get(k, y.get("common_dose","") if k=="dose" else "")).strip():
                print(f"[err] {yml.name}: missing field '{k}'")
                n_err += 1
        r = str(y.get("route","")).lower().strip()
        if r and r not in ROUTES:
            print(f"[warn] {yml.name}: unusual route '{r}' (allowed: {sorted(ROUTES)})")
        syn = y.get("synonyms", [])
        if isinstance(syn, list) and any((";" in s) for s in syn):
            print(f"[warn] {yml.name}: semicolons found inside synonyms list; they will be re-joined later")
        links = y.get("external_links", [])
        if links and not isinstance(links, list):
            print(f"[err] {yml.name}: external_links must be a list of {label,url}"); n_err += 1
        elif isinstance(links, list):
            for i,lnk in enumerate(links):
                if not isinstance(lnk, dict) or not lnk.get("url"):
                    print(f"[err] {yml.name}: external_links[{i}] must include 'url'"); n_err += 1
    return 0 if n_err==0 else 2

def main() -> int:
    return validate_yaml_dir(sys.argv[1] if len(sys.argv)>1 else "data/compounds.d")

if __name__ == "__main__":
    raise SystemExit(main())
