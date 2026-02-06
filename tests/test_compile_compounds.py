import json
from pathlib import Path

import pandas as pd

from tools.compile_compounds import compile_compounds


def test_compile_compounds_writes_csv_and_json(tmp_path: Path):
    data_dir = tmp_path / "data"
    compounds_dir = data_dir / "compounds.d"
    compounds_dir.mkdir(parents=True)

    (compounds_dir / "caffeine.yaml").write_text(
        """
id: caffeine
name: Caffeine
class: stimulant
route: oral
dose: 100-400 mg
synonyms:
  - coffee
  - caffeine anhydrous
""".strip()
        + "\n",
        encoding="utf-8",
    )

    rc = compile_compounds(str(data_dir))

    assert rc == 0

    csv_path = data_dir / "compounds.csv"
    json_path = data_dir / "compounds.json"
    assert csv_path.exists()
    assert json_path.exists()

    df = pd.read_csv(csv_path)
    assert list(df["id"]) == ["caffeine"]
    assert df.loc[0, "synonyms"] == "coffee;caffeine anhydrous"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload == [
        {
            "id": "caffeine",
            "name": "Caffeine",
            "aliases": ["coffee", "caffeine anhydrous"],
        }
    ]
