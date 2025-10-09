#!/usr/bin/env python3
from __future__ import annotations
import sys, os, yaml, pandas as pd
from pathlib import Path

def _join(v, sep=";"):
    if v is None: return ""
    if isinstance(v, str): return v
    return sep.join([str(x).strip() for x in v if str(x).strip()])

def compile_sources(dir_in: Path, out_csv: Path):
    rows = []
    if dir_in.exists():
        for yml in sorted(dir_in.glob("*.yaml")):
            y = yaml.safe_load(open(yml, "r", encoding="utf-8")) or {}
            rows.append({
                "id": y.get("id") or yml.stem,
                "title": y.get("title",""),
                "citation": y.get("citation",""),
                "identifier": y.get("identifier",""),
                "date": y.get("date",""),
                "extra": y.get("extra",""),
            })
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"[ok] wrote {out_csv} ({len(rows)} rows)")

def compile_interactions(dir_in: Path, out_csv: Path):
    rows = []
    if dir_in.exists():
        for yml in sorted(dir_in.glob("*.yaml")):
            y = yaml.safe_load(open(yml, "r", encoding="utf-8")) or {}
            rows.append({
                "compound_a": y.get("compound_a",""),
                "compound_b": y.get("compound_b",""),
                "severity": y.get("severity","None"),
                "evidence_grade": y.get("evidence_grade","D"),
                "mechanism_tags": _join(y.get("mechanism_tags")),
                "source_ids": _join(y.get("source_ids")),
                "action": y.get("action",""),
            })
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"[ok] wrote {out_csv} ({len(rows)} rows)")

def main(data_dir="data"):
    base = Path(data_dir)
    compile_sources(base/"sources.d", base/"sources.csv")
    compile_interactions(base/"interactions.d", base/"interactions.csv")

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv)>1 else "data"))
