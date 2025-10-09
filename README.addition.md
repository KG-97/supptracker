## Data pipeline quickstart
```bash
# 1) Add or edit YAMLs
cp data/compound_template.yaml data/compounds.d/new-item.yaml
$EDITOR data/compounds.d/new-item.yaml

# 2) Compile
python tools/compile_compounds.py
python tools/compile_interactions.py

# 3) Validate
python tools/validate_compounds.py
python tools/validate_interactions.py

# 4) Test
pytest -q
```
