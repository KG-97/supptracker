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
- The compound search also calls it, with the one searched name, to say whether that name appears in the collection and to open its statements.
- A drug name matches by whole words only: `warfarin` finds `warfarin sodium`; `war` finds nothing. A combination product matches on any of its ingredients; its full name is shown and it is marked `combination_product: true`.
- Bare ions and excipients (`water`, `sodium`, `potassium`, `calcium`, `magnesium`, `zinc`, `iron`, `chloride`, `phosphate`, `sulfate`, `acetate`) never match a drug label on their own, so `water pills` does not find an insulin product and `calcium` does not find calcium chloride injection. `potassium chloride` still finds its own label.
- The page shows the names that were typed beside the label's own names, because they can differ (`K2` is filed under Vitamin K).
- Invalid input (no names, more than 20, or a name over 120 characters) returns HTTP 422 with `status: "invalid"`, `assessment: "not_assessed"` and a `detail` sentence.
- Results are ordered by how many labels carry the text. That is not a risk ranking.
- The supplement filter on the other statement endpoints ignores letter case.

## Measured limits

- 23,804 labels were scanned.
- 14,209 labels were skipped because openFDA supplied no active-substance identity.
- 114 multi-ingredient products were skipped.
- 1,440 sentences over 700 characters were skipped.
- At most three sentences were kept per supplement/drug pair.
- Within a pair, sentences that differ only in letter case, spacing, bullets or quote style are merged into one (991 merges before the three-per-pair cut); the most widely used wording is kept and its label count covers every variant. Digits, full stops, commas, arrows and comparison signs are never ignored, so 109 kept statements still differ from another in the same pair only by a comma, colon or hyphen.
- 252 of 974 pairs use group terms.
- A seeded sample of 60 statements was re-read from the live API; all 60 matched word for word.
- A model (Codex, 2026-11-16) read every sentence once and flagged 305 of 1,977; Claude Code then read the 53 flagged as not about a supplement or as unreadable. 34 of those were confirmed and are now excluded by dictionary rules (laboratory values such as serum electrolytes, drug classes such as folic acid antagonists, a drug's own magnesium content, cut-off table fragments), with 2 pointer sentences that carried no content. 19 were kept. This was a precision check, not a clinical review.
- Not acted on: 107 sentences that say no interaction or no relevant effect was observed, and 145 that name a supplement without saying anything about taking it with the drug. They are still shown, word for word, like every other statement.
- No person has reviewed the meaning of any sentence, and no sentence has been clinically reviewed.
