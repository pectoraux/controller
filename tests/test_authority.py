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
        self.assertEqual(program.active_work_item, "CTRL-013")
        self.assertIs(program.status, LifecycleState.COMPLETE)
        self.assertEqual(program.schema_version, "0.1")
        self.assertEqual(
            program.automation_stage,
            "STAGE-7-END-TO-END-AUTONOMOUS-GOVERNED-LOOP",
        )
        self.assertEqual(
            program.completed,
            (
                "CTRL-001",
                "CTRL-002",
                "CTRL-003",
                "CTRL-004",
                "CTRL-005",
                "CTRL-006",
                "CTRL-007",
                "CTRL-008",
                "CTRL-009",
                "CTRL-010",
                "CTRL-011",
                "CTRL-012",
                "CTRL-013",
            ),
        )

    def test_real_repository_declares_stage7_architecture_rules(self) -> None:
        program = verify_authority(REPO_ROOT)
        self.assertEqual(len(program.rules), 7)
        self.assertFalse(program.rules["humanOperatorIsTemporaryMechanicalController"])
        self.assertTrue(
            all(
                value
                for name, value in program.rules.items()
                if name != "humanOperatorIsTemporaryMechanicalController"
            )
        )

    def test_real_work_item_status_parses(self) -> None:
        self.assertIs(load_work_item_status(REPO_ROOT, "CTRL-013"), LifecycleState.COMPLETE)


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


class StageDerivedRuleTests(unittest.TestCase):
    """The mechanical-controller rule is stage-semantic (CTRL-011).

    The accepted Stage-7 transition transfers the routine mechanical
    orchestration role from the human operator to the Controller, so the
    expected value of ``humanOperatorIsTemporaryMechanicalController`` is
    derived from the automation stage: ``false`` at exactly the accepted
    Stage-7 marker, ``true`` at every other stage. Any other combination
    is a contradiction and fails closed.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_repo(Path(self._tmp.name))

    def _with_rules(self, mechanical: bool, stage: str) -> None:
        rules = dict(canonical_state()["rules"])
        rules["humanOperatorIsTemporaryMechanicalController"] = mechanical
        write_state(self.root, canonical_state(rules=rules, automationStage=stage))

    def test_stage7_with_transferred_role_validates(self) -> None:
        self._with_rules(mechanical=False, stage="STAGE-7-END-TO-END-AUTONOMOUS-GOVERNED-LOOP")
        program = load_program_state(self.root)
        self.assertFalse(program.rules["humanOperatorIsTemporaryMechanicalController"])

    def test_stage7_with_untransferred_role_is_a_contradiction(self) -> None:
        self._with_rules(mechanical=True, stage="STAGE-7-END-TO-END-AUTONOMOUS-GOVERNED-LOOP")
        with self.assertRaises(ContradictionError):
            load_program_state(self.root)

    def test_pre_stage7_with_transferred_role_is_a_contradiction(self) -> None:
        self._with_rules(mechanical=False, stage="STAGE-1-STATE-MACHINE-AUTOMATION")
        with self.assertRaises(ContradictionError):
            load_program_state(self.root)

    def test_unknown_stage_keeps_pre_transfer_expectation(self) -> None:
        self._with_rules(mechanical=False, stage="STAGE-8-SOME-FUTURE-STAGE")
        with self.assertRaises(ContradictionError):
            load_program_state(self.root)

    def test_expected_rule_value_is_stage_derived_only_for_the_one_rule(self) -> None:
        from controller.authority import expected_rule_value

        self.assertTrue(
            expected_rule_value(
                "humanOperatorIsTemporaryMechanicalController",
                "STAGE-6-MERGE-RECONCILIATION-AUTOMATION",
            )
        )
        self.assertFalse(
            expected_rule_value(
                "humanOperatorIsTemporaryMechanicalController",
                "STAGE-7-END-TO-END-AUTONOMOUS-GOVERNED-LOOP",
            )
        )
        for rule in (
            "repositoryIsSourceOfTruth",
            "controllerRuntimeStateIsReconstructible",
            "onePrPerWorkItem",
            "workerCannotMerge",
            "failClosedOnContradiction",
            "architectMustAnnounceAutomationStage",
        ):
            self.assertTrue(
                expected_rule_value(rule, "STAGE-7-END-TO-END-AUTONOMOUS-GOVERNED-LOOP")
            )
            self.assertTrue(expected_rule_value(rule, "STAGE-0-MANUAL-CONTROLLER"))


if __name__ == "__main__":
    unittest.main()
