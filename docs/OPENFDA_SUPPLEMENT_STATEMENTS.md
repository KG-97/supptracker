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

## Measured limits

- 23,804 labels were scanned.
- 14,209 labels were skipped because openFDA supplied no active-substance identity.
- 114 multi-ingredient products were skipped.
- 1,440 sentences over 700 characters were skipped.
- At most three sentences were kept per supplement/drug pair.
- 271 of 992 pairs use group terms.
- A seeded sample of 60 statements was re-read from the live API; all 60 matched word for word.
- No person or model has reviewed the meaning of any sentence.
