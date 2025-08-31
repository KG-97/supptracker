import os


def _ensure_test_data():
    root = os.getcwd()
    data_dir = os.path.join(root, "data")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

    # compounds.csv
    comp_csv = os.path.join(data_dir, "compounds.csv")
    if not os.path.exists(comp_csv):
        with open(comp_csv, "w", encoding="utf-8") as f:
            f.write("id,name,synonyms\n")
            f.write("caffeine,Caffeine,coffee;tea\n")
            f.write("aspirin,Aspirin,acetylsalicylic acid\n")

    # interactions.csv
    inter_csv = os.path.join(data_dir, "interactions.csv")
    if not os.path.exists(inter_csv):
        with open(inter_csv, "w", encoding="utf-8") as f:
            f.write("compound_a,compound_b,severity,evidence_grade,mechanism_tags,source_ids\n")
            f.write("caffeine,aspirin,Moderate,B,,source1\n")

    # sources.csv
    src_csv = os.path.join(data_dir, "sources.csv")
    if not os.path.exists(src_csv):
        with open(src_csv, "w", encoding="utf-8") as f:
            f.write("id,title\n")
            f.write("source1,Example source\n")

    # risk_rules.yaml
    rules_yaml = os.path.join(data_dir, "risk_rules.yaml")
    if not os.path.exists(rules_yaml):
        with open(rules_yaml, "w", encoding="utf-8") as f:
            f.write("severity_map:\n  None: 0\n  Mild: 1\n  Moderate: 2\n  Severe: 3\n")


# Ensure data files exist before tests import app
_ensure_test_data()
