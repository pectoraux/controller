"""Unit tests: repository authority loading and validation (fail-closed)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from controller.authority import (
    STATE_FILE,
    load_program_state,
    load_work_item_status,
    verify_authority,
)
from controller.errors import ContradictionError, SpecError
from controller.states import LifecycleState
from tests.util import REPO_ROOT, canonical_state, make_repo, write_state

_ALL_REQUIRED_FIELDS = [
    "schemaVersion",
    "repository",
    "roadmap",
    "architecture",
    "buildProcess",
    "activeWorkItem",
    "status",
    "automationStage",
    "completed",
    "rules",
    "nextAction",
]


class RealRepositoryTests(unittest.TestCase):
    def test_real_repository_authority_validates(self) -> None:
        program = verify_authority(REPO_ROOT)
        self.assertEqual(program.active_work_item, "CTRL-001")
        self.assertIs(program.status, LifecycleState.READY)
        self.assertEqual(program.schema_version, "0.1")
        self.assertEqual(program.automation_stage, "STAGE-0-MANUAL-CONTROLLER")
        self.assertEqual(program.completed, ())

    def test_real_repository_declares_all_architecture_rules_true(self) -> None:
        program = verify_authority(REPO_ROOT)
        self.assertTrue(all(program.rules.values()))
        self.assertEqual(len(program.rules), 7)

    def test_real_work_item_status_parses(self) -> None:
        self.assertIs(load_work_item_status(REPO_ROOT, "CTRL-001"), LifecycleState.READY)


class ValidLoadTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = make_repo(self.base)

    def test_valid_synthetic_state_loads(self) -> None:
        program = load_program_state(self.root)
        self.assertEqual(program.active_work_item, "CTRL-001")
        self.assertIs(program.status, LifecycleState.READY)
        self.assertEqual(program.repository, "pectoraux/controller-test")

    def test_verify_authority_accepts_consistent_tree(self) -> None:
        program = verify_authority(self.root)
        self.assertIs(program.status, LifecycleState.READY)


class MalformedStateTests(unittest.TestCase):
    """Structural defects must raise SpecError, never defaults or guesses."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = make_repo(self.base)

    def _write(self, state: object) -> None:
        (self.root / STATE_FILE).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    def test_missing_state_file_fails_closed(self) -> None:
        (self.root / STATE_FILE).unlink()
        with self.assertRaises(SpecError):
            load_program_state(self.root)

    def test_invalid_json_fails_closed(self) -> None:
        (self.root / STATE_FILE).write_text("{not json", encoding="utf-8")
        with self.assertRaises(SpecError):
            load_program_state(self.root)

    def test_non_object_json_fails_closed(self) -> None:
        self._write(["unexpected", "list"])
        with self.assertRaises(SpecError):
            load_program_state(self.root)

    def test_every_missing_required_field_fails_closed(self) -> None:
        for field in _ALL_REQUIRED_FIELDS:
            with self.subTest(field=field):
                state = canonical_state()
                del state[field]
                self._write(state)
                with self.assertRaises(SpecError):
                    load_program_state(self.root)

    def test_unsupported_schema_version_fails_closed(self) -> None:
        self._write(canonical_state(schemaVersion="0.2"))
        with self.assertRaises(SpecError):
            load_program_state(self.root)

    def test_unknown_status_value_fails_closed(self) -> None:
        self._write(canonical_state(status="HALF_READY"))
        with self.assertRaises(SpecError):
            load_program_state(self.root)

    def test_wrong_typed_field_fails_closed(self) -> None:
        cases: dict[str, object] = {
            "status": 7,
            "activeWorkItem": None,
            "completed": "CTRL-001",
            "rules": ["repositoryIsSourceOfTruth"],
            "nextAction": "",
        }
        for field, value in cases.items():
            with self.subTest(field=field, value=value):
                self._write(canonical_state(**{field: value}))
                with self.assertRaises(SpecError):
                    load_program_state(self.root)

    def test_missing_referenced_authority_file_fails_closed(self) -> None:
        (self.root / "spec/roadmap/roadmap.md").unlink()
        with self.assertRaises(SpecError):
            load_program_state(self.root)

    def test_missing_work_item_file_fails_closed(self) -> None:
        (self.root / "spec/work-items/CTRL-001.md").unlink()
        with self.assertRaises(SpecError):
            load_work_item_status(self.root, "CTRL-001")

    def test_work_item_heading_mismatch_fails_closed(self) -> None:
        path = self.root / "spec/work-items/CTRL-001.md"
        path.write_text("# CTRL-009 — Wrong Item\n\nStatus: `READY`\n", encoding="utf-8")
        with self.assertRaises(SpecError):
            load_work_item_status(self.root, "CTRL-001")

    def test_work_item_without_status_line_fails_closed(self) -> None:
        path = self.root / "spec/work-items/CTRL-001.md"
        path.write_text("# CTRL-001 — No Status\n\nBody only.\n", encoding="utf-8")
        with self.assertRaises(SpecError):
            load_work_item_status(self.root, "CTRL-001")


class ContradictoryAuthorityTests(unittest.TestCase):
    """Authority sources that disagree must fail closed, not be repaired."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = make_repo(self.base)

    def test_status_disagreement_between_state_and_work_order(self) -> None:
        # Machine state says READY; the work order file says DISPATCHED.
        write_state(self.root, canonical_state(status="READY"))
        work = self.root / "spec/work-items/CTRL-001.md"
        work.write_text(
            "# CTRL-001 — Synthetic Test Item\n\nStatus: `DISPATCHED`\n", encoding="utf-8"
        )
        with self.assertRaises(ContradictionError):
            verify_authority(self.root)

    def test_missing_architecture_rule_is_a_contradiction(self) -> None:
        rules = {key: True for key in canonical_state()["rules"] if key != "workerCannotMerge"}
        write_state(self.root, canonical_state(rules=rules))
        with self.assertRaises(ContradictionError):
            load_program_state(self.root)

    def test_negated_architecture_rule_is_a_contradiction(self) -> None:
        rules = dict(canonical_state()["rules"])
        rules["failClosedOnContradiction"] = False
        write_state(self.root, canonical_state(rules=rules))
        with self.assertRaises(ContradictionError):
            load_program_state(self.root)

    def test_extra_unknown_rule_is_tolerated(self) -> None:
        """Unknown future rules are informational, not contradictory."""
        rules = dict(canonical_state()["rules"])
        rules["someFutureRule"] = True
        write_state(self.root, canonical_state(rules=rules))
        program = load_program_state(self.root)
        self.assertTrue(program.rules["someFutureRule"])


if __name__ == "__main__":
    unittest.main()
