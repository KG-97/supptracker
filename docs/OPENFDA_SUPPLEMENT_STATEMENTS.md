# openFDA supplement statements

`data/openfda_supplement_statements/` is a read-only corpus of FDA-approved drug-label sentences. One record is one sentence copied word for word from the `DRUG INTERACTIONS` section of an FDA label where a supplement, food, or defined supplement group is named.

The source is the [openFDA drug label API](https://api.fda.gov/drug/label.json). openFDA content is dedicated to the public domain under CC0 1.0 unless otherwise noted; see [the openFDA licence](https://open.fda.gov/license/). Each row retains its openFDA source URL, set ID, label ID, effective time, retrieval time, and rights status.

## Build and validate

Rebuild deliberately, inspect the resulting data, then validate it:

```powershell
python scripts/build_openfda_supplement_statements.py
python scripts/validate_openfda_supplement_statements.py --dir data/openfda_supplement_statements --terms data/openfda_supplement_statements/supplement_terms.json
```

Do not alter the generated files by hand.

## Contract

- These statements never enter a score, severity, risk flag, stack result, or assessed-interaction lookup.
- A missing statement means `not_assessed`; it never means a combination is safe or has no interaction.
- No severity, score, risk level, mechanism, evidence grade, recommendation, or clinical interpretation is attached to a statement.
- API responses carrying statements repeat the record kind, review status, and this fixed disclaimer: FDA-approved label text, quoted verbatim, not reviewed or assessed by SuppTracker, not medical advice, absence of a statement does not mean a combination is safe.
- Loading is all-or-nothing. A missing folder, unreadable file, missing required column, wrong fixed value, or duplicate statement ID disables the statement feature and serves zero statements. It does not affect the rest of the application.
- `otc_class`, `generic_class`, and `mineral_class` are group terms, not individual supplements.

## Lookup by name

`GET /api/label-statements/lookup?names=<a>&names=<b>` finds statements that name any two of the given names together (1 to 20 names). The pair checker and the stack checker call it and show the result in a separate "FDA label statements" block under their own answer.

- It is a pointer to label text. It does not change the pair or stack response, and every lookup response carries `assessment: "not_assessed"`, whether or not statements were found.
- A supplement name matches by identifier, by name, or by the dictionary's wording (so `calcium` is tried as `calcium supplements`).
- A short list of everyday spellings is also accepted (`LOOKUP_ALIASES` in `api/label_statements.py`): `grapefruit juice`, `CoQ10`, `K2`, `D3`, `B6`, `B12`, `5 HTP`, `L-tryptophan`, `vitamin B3`, `Saint John's wort`, `retinol`, `cholecalciferol`. Each is an exact whole-name match for one supplement, so a fragment such as `q10` or `k` still finds nothing. The list is used by the lookup only; it does not change the mining dictionary or its recorded hash.
- A drug name matches by whole words only: `warfarin` finds `warfarin sodium`; `war` finds nothing. A combination product matches on any of its ingredients, and its full name is shown.
- Results are ordered by how many labels carry the text. That is not a risk ranking.
- The supplement filter on the other statement endpoints ignores letter case.

## Measured limits

- 23,804 labels were scanned.
- 14,209 labels were skipped because openFDA supplied no active-substance identity.
- 114 multi-ingredient products were skipped.
- 1,440 sentences over 700 characters were skipped.
- At most three sentences were kept per supplement/drug pair.
- Within a pair, sentences that differ only in letter case, spacing, bullets or quote style are merged into one (998 merges before the three-per-pair cut); the most widely used wording is kept and its label count covers every variant. Digits, full stops, commas, arrows and comparison signs are never ignored, so 109 kept statements still differ from another in the same pair only by a comma, colon or hyphen.
- 271 of 992 pairs use group terms.
- A seeded sample of 60 statements was re-read from the live API; all 60 matched word for word.
- No person or model has reviewed the meaning of any sentence.
