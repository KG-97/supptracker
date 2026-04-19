#!/usr/bin/env python3
"""Compile per-compound YAML files (data/compounds.d/*.yaml) into data/compounds.csv.
Keeps backward compatibility with the current app which reads CSV.
"""
from __future__ import annotations
import os, sys, glob, csv, yaml, pandas as pd
from pathlib import Path

def main(data_dir: str = "data"):
    comp_dir = Path(data_dir) / "compounds.d"
    out_csv = Path(data_dir) / "compounds.csv"
    rows = []
    if comp_dir.exists():
        for path in sorted(comp_dir.glob("*.yaml")):
            with open(path, "r", encoding="utf-8") as f:
                y = yaml.safe_load(f) or {}
            syn = y.get("synonyms") or []
            if isinstance(syn, str):
                syn = [syn]
            row = {
                "id": y.get("id") or path.stem,
                "name": y.get("name") or path.stem,
                "synonyms": ";".join([s.strip() for s in syn if s and str(s).strip()]),
                "class": y.get("class",""),
                "route": y.get("route",""),
                "common_dose": y.get("common_dose",""),
                "qt_risk": y.get("qt_risk",""),
                "notes": y.get("notes",""),
                "examine_slug": y.get("examine_slug",""),
            }
            rows.append(row)
    else:
        print(f"[warn] {comp_dir} not found — nothing to compile.", file=sys.stderr)
    if not rows:
        print("[warn] no YAML rows found; will not overwrite existing CSV.", file=sys.stderr)
        return 0
    df = pd.DataFrame(rows)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    print(f"[ok] wrote {out_csv} ({len(df)} rows)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "data"))
