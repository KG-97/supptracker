import os


def _ensure_test_data():
    """Write minimal CSV/YAML fixtures and point the application to them.

    The real repository ships a much larger dataset under ``data/``.  For the
    purposes of unit tests we only need a tiny, deterministic subset.  The tests
    place these files in ``tests/test_data`` and instruct the application to use
    that directory via the ``SUPPTRACKER_DATA`` environment variable.
    """
    root = os.path.dirname(__file__)
    data_dir = os.path.join(root, "test_data")
    os.makedirs(data_dir, exist_ok=True)

    # compounds.csv
    with open(os.path.join(data_dir, "compounds.csv"), "w", encoding="utf-8") as f:
        f.write("id,name,synonyms\n")
        f.write("caffeine,Caffeine,coffee;tea\n")
        f.write("aspirin,Aspirin,acetylsalicylic acid\n")

    # interactions.csv
    with open(os.path.join(data_dir, "interactions.csv"), "w", encoding="utf-8") as f:
        f.write("compound_a,compound_b,severity,evidence_grade,mechanism_tags,source_ids\n")
        f.write("caffeine,aspirin,Moderate,B,,source1\n")

    # sources.csv
    with open(os.path.join(data_dir, "sources.csv"), "w", encoding="utf-8") as f:
        f.write("id,title\n")
        f.write("source1,Example source\n")

    # risk_rules.yaml
    with open(os.path.join(data_dir, "risk_rules.yaml"), "w", encoding="utf-8") as f:
        f.write("severity_map:\n  None: 0\n  Mild: 1\n  Moderate: 2\n  Severe: 3\n")

    # Point the application to the stub data directory before it is imported.
    os.environ["SUPPTRACKER_DATA"] = data_dir

    # Ensure the static assets directory exists so FastAPI can mount it during tests.
    project_root = os.path.dirname(root)
    static_assets = os.path.join(project_root, "frontend_dist", "assets")
    os.makedirs(static_assets, exist_ok=True)


# Ensure data files exist before tests import app
_ensure_test_data()
