#!/usr/bin/env python3
from __future__ import annotations
import sys, yaml, pandas as pd
from pathlib import Path

REQUIRED = ["id","name","class","route","dose"]

def _join(x, sep=";"):
    if x is None: return ""
    if isinstance(x, str): return x
    return sep.join([str(i).strip() for i in x if str(i).strip()])

def _links_to_str(links):
    import json
    if not links: return "[]"
    if isinstance(links, str): return links
    return json.dumps(links, ensure_ascii=False, separators=(",",":"))

def compile_compounds(data_dir: str = "data"):
    d = Path(data_dir) / "compounds.d"
    out = Path(data_dir) / "compounds.csv"
    rows = []
    if not d.exists():
        print(f"[warn] {d} not found — nothing to compile.")
    else:
        for yml in sorted(d.glob("*.yaml")):
            y = yaml.safe_load(open(yml, "r", encoding="utf-8")) or {}
            dose = y.get("dose") or y.get("common_dose", "")
            synonyms = y.get("synonyms", [])
            if isinstance(synonyms, str):
                synonyms = [synonyms]
            row = {
                "id": y.get("id") or yml.stem,
                "name": y.get("name") or yml.stem,
                "synonyms": _join(synonyms),
                "class": y.get("class", ""),
                "route": y.get("route", ""),
                "dose": dose,
                "qt_risk": y.get("qt_risk", ""),
                "notes": y.get("notes", ""),
                "examine_slug": y.get("examine_slug", ""),
                "external_links": _links_to_str(y.get("external_links", [])),
            }
            miss = [k for k in REQUIRED if not str(row.get(k,"")).strip()]
            if miss:
                print(f"[warn] {yml.name} missing {miss}")
            rows.append(row)
    if not rows:
        print("[warn] no YAML rows found; will not overwrite existing CSV.")
        return 0
    df = pd.DataFrame(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"[ok] wrote {out} ({len(df)} rows)")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(compile_compounds(sys.argv[1] if len(sys.argv)>1 else "data"))
