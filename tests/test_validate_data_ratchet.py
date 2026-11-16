import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "validate_data.py"
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=PROJECT_ROOT,
    )


def test_legacy_list_errors_only_pass_at_the_recorded_number():
    plain = _run()
    found = re.search(r"ERROR: (\d+) Error\(s\)", plain.stdout)
    if found is None:
        # The legacy list is clean: nothing to ratchet, and the plain run must pass.
        assert plain.returncode == 0
        return

    count = int(found.group(1))
    # Without a recorded number the errors fail the run.
    assert plain.returncode == 1
    # At exactly the recorded number the run passes and says the list is quarantined.
    at_baseline = _run("--known-errors", str(count))
    assert at_baseline.returncode == 0
    assert "stays quarantined" in at_baseline.stdout
    # One more error than recorded fails; so does a stale, higher baseline.
    assert _run("--known-errors", str(count - 1)).returncode == 1
    stale = _run("--known-errors", str(count + 1))
    assert stale.returncode == 1
    assert f"Lower --known-errors to {count}" in stale.stdout


def test_ci_records_the_current_number():
    plain = _run()
    found = re.search(r"ERROR: (\d+) Error\(s\)", plain.stdout)
    workflow = WORKFLOW.read_text(encoding="utf-8")
    if found is None:
        assert "--known-errors" not in workflow
    else:
        assert f"validate_data.py --known-errors {found.group(1)}\n" in workflow
