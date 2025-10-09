#!/usr/bin/env python3
from __future__ import annotations
import sys, yaml
from pathlib import Path

def main(data_dir="data"):
    d = Path(data_dir)/"compounds.d"
    if not d.exists():
        print(f"[err] {d} not found"); return 1
    for yml in d.glob("*.yaml"):
        y = yaml.safe_load(open(yml,"r",encoding="utf-8")) or {}
        if "dose" not in y and y.get("common_dose"):
            y["dose"] = y.pop("common_dose")
        links = y.get("external_links", [])
        if isinstance(links, list) and y.get("examine_slug"):
            url = f"https://examine.com/{y['examine_slug'].lstrip('/')}"
            if not any((isinstance(x, dict) and x.get("url")==url) for x in links):
                links.append({"label":"Examine", "url": url})
                y["external_links"] = links
        with open(yml, "w", encoding="utf-8") as f:
            yaml.safe_dump(y, f, sort_keys=False, allow_unicode=True)
    print("[ok] migrated YAMLs")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv)>1 else "data"))
