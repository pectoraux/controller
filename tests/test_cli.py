"""Unit tests: CLI smoke test (``python -m controller validate``).

Exercises the runtime through a real subprocess against both the real
repository and synthetic trees. Local and offline only.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.util import REPO_ROOT, make_repo


def _run_controller(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "controller", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=60,
        check=False,
    )


class ValidateCommandTests(unittest.TestCase):
    def test_validate_real_repository_succeeds(self) -> None:
        result = _run_controller("validate", "--repo", str(REPO_ROOT))
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("controller authority: OK", result.stdout)
        self.assertIn("active work item: CTRL-013", result.stdout)
        self.assertIn("lifecycle state: COMPLETE", result.stdout)

    def test_validate_synthetic_repository_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            result = _run_controller("validate", "--repo", str(root))
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("lifecycle state: READY", result.stdout)

    def test_validate_contradictory_repository_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp), status="READY", work_item_status="DISPATCHED")
            result = _run_controller("validate", "--repo", str(root))
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL-CLOSED", result.stderr)
            self.assertIn("contradictory authority", result.stderr)

    def test_validate_missing_state_file_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            (root / "spec/state/controller-program-state.json").unlink()
            result = _run_controller("validate", "--repo", str(root))
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL-CLOSED", result.stderr)

    def test_validate_outputs_are_deterministic(self) -> None:
        first = _run_controller("validate", "--repo", str(REPO_ROOT))
        second = _run_controller("validate", "--repo", str(REPO_ROOT))
        self.assertEqual(first.returncode, second.returncode)
        self.assertEqual(first.stdout, second.stdout)

    def test_version_reports_foundation_version(self) -> None:
        result = _run_controller("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn("0.1.0", result.stdout)


if __name__ == "__main__":
    unittest.main()
