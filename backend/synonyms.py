from __future__ import annotations
import re
from typing import Iterable, List

SEP = re.compile(r"[|,;/]+")

def parse_synonyms(s: str | None) -> List[str]:
    if not s:
        return []
    toks = [t.strip().lower() for t in SEP.split(str(s))]
    uniq = {t for t in toks if t}
    return sorted(uniq)

def normalize_names(names: Iterable[str]) -> List[str]:
    out = []
    for n in names:
        if not n:
            continue
        out.append(str(n).strip().lower())
    seen = set()
    norm = []
    for n in out:
        if n not in seen:
            seen.add(n)
            norm.append(n)
    return norm
