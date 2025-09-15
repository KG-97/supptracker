import os
import tempfile


def _create_stub_dataset():
    """Create a minimal dataset in a temporary directory and point the
    application to use it via the SUPPTRACKER_DATA environment variable.
    This avoids mutating the repository's real data files during tests.
    """
    data_dir = tempfile.mkdtemp(prefix="supp-data-")

    comp_csv = os.path.join(data_dir, "compounds.csv")
    with open(comp_csv, "w", encoding="utf-8") as f:
        f.write("id,name,synonyms\n")
        f.write("caffeine,Caffeine,coffee;tea\n")
        f.write("aspirin,Aspirin,acetylsalicylic acid\n")

    inter_csv = os.path.join(data_dir, "interactions.csv")
    with open(inter_csv, "w", encoding="utf-8") as f:
        f.write("compound_a,compound_b,severity,evidence_grade,mechanism_tags,source_ids\n")
        f.write("caffeine,aspirin,Moderate,B,,source1\n")

    src_csv = os.path.join(data_dir, "sources.csv")
    with open(src_csv, "w", encoding="utf-8") as f:
        f.write("id,title\n")
        f.write("source1,Example source\n")

    rules_yaml = os.path.join(data_dir, "risk_rules.yaml")
    with open(rules_yaml, "w", encoding="utf-8") as f:
        f.write("severity_map:\n  None: 0\n  Mild: 1\n  Moderate: 2\n  Severe: 3\n")

    os.environ["SUPPTRACKER_DATA"] = data_dir


_create_stub_dataset()
