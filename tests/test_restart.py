"""Unit tests: restart / state reconstruction from repository authority.

Covers acceptance criteria 2-4 of CTRL-001: controller state is rebuilt
from repository files alone, equivalent repositories reconstruct to equal
states, and contradictory authority is rejected instead of guessed.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from controller.authority import reconstruct
from controller.errors import ContradictionError, SpecError
from controller.states import LifecycleState
from tests.util import REPO_ROOT, canonical_state, make_repo, write_state


class ReconstructionEquivalenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = make_repo(self.base)

    def test_repeated_reconstruction_yields_equal_state(self) -> None:
        """Simulated restart: same repo, fresh process, same result."""
        first = reconstruct(self.root)
        second = reconstruct(self.root)
        self.assertEqual(first, second)
        self.assertEqual((first.work_item, first.lifecycle), ("CTRL-001", LifecycleState.READY))

    def test_equivalent_repository_tree_reconstructs_equal_state(self) -> None:
        """A byte-for-byte copy of the repo (another machine) is equal."""
        twin = self.base / "twin"
        shutil.copytree(self.root, twin)
        self.assertEqual(reconstruct(self.root), reconstruct(twin))

    def test_state_follows_authority_not_memory(self) -> None:
        """A consistently advanced repo reconstructs to the advanced state."""
        write_state(self.root, canonical_state(status="DISPATCHED"))
        work = self.root / "spec/work-items/CTRL-001.md"
        work.write_text(
            "# CTRL-001 — Synthetic Test Item\n\nStatus: `DISPATCHED`\n", encoding="utf-8"
        )
        self.assertEqual(reconstruct(self.root).lifecycle, LifecycleState.DISPATCHED)

    def test_reconstruction_reads_no_side_channel(self) -> None:
        """Deleting the state file makes reconstruction impossible —
        proving the repository file (not a cache) is the only source."""
        (self.root / "spec/state/controller-program-state.json").unlink()
        with self.assertRaises(SpecError):
            reconstruct(self.root)


class ContradictoryReconstructionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = make_repo(self.base)

    def test_state_and_work_order_disagreement_blocks_reconstruction(self) -> None:
        write_state(self.root, canonical_state(status="MERGED"))
        with self.assertRaises(ContradictionError):
            reconstruct(self.root)

    def test_bogus_status_in_both_sources_fails_closed(self) -> None:
        write_state(self.root, canonical_state(status="TELEPORTED"))
        work = self.root / "spec/work-items/CTRL-001.md"
        work.write_text(
            "# CTRL-001 — Synthetic Test Item\n\nStatus: `TELEPORTED`\n", encoding="utf-8"
        )
        with self.assertRaises(SpecError):
            reconstruct(self.root)

    def test_referenced_work_order_missing_blocks_reconstruction(self) -> None:
        (self.root / "spec/work-items/CTRL-001.md").unlink()
        with self.assertRaises(SpecError):
            reconstruct(self.root)


class RealRepositoryReconstructionTests(unittest.TestCase):
    def test_real_repository_reconstructs_ctrl_001_ready(self) -> None:
        state = reconstruct(REPO_ROOT)
        self.assertEqual(state.work_item, "CTRL-001")
        self.assertIs(state.lifecycle, LifecycleState.READY)

    def test_real_repository_reconstruction_is_stable(self) -> None:
        self.assertEqual(reconstruct(REPO_ROOT), reconstruct(REPO_ROOT))


if __name__ == "__main__":
    unittest.main()
