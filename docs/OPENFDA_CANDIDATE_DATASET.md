# openFDA label-derived candidate dataset

This is a discovery corpus, not a clinically validated interaction database.

The importer fetches labels with a `DRUG INTERACTIONS` section and generic-name metadata from openFDA. It creates a candidate only when the generic/substance name for one labelled product appears in the interaction text of another label. Each candidate carries the FDA label set ID, a query URL, retrieval time and a SHA-256 hash of the full source interaction text. Candidates live in `label_candidates.csv`, not `interactions.csv`.

Same-substance pairs are excluded when removing terminal salt, hydrate, ester, dosage-form, and known biologic-suffix words yields the same complete base identifier. They are also excluded when either identifier is a documented ingredient of the other's explicit combination product; see `manifest.json` for current counts.

## Safety contract

- A candidate must never receive a clinical severity, risk score, "avoid" recommendation, or a statement that a pair is safe.
- The interface must call these records **label-derived candidates requiring review**.
- A future assessed interaction needs an independently reviewed source and a separate assessed-data import; it may not be promoted automatically from this corpus.

## Licence and attribution

openFDA says that, unless otherwise noted, its content/data are dedicated to the public domain under CC0 1.0. The generated `manifest.json` repeats the official licence URL and every source row retains its individual label URL. See <https://open.fda.gov/license/>.
