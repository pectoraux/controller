"""Unit tests: the CTRL-002 domain model (identity, eligibility, commands,
events, reconstruction, idempotency, fail-closed behavior)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from controller.authority import STATE_FILE
from controller.commands import Command, CommandName
from controller.domain import (
    DispatchEligibility,
    DomainCommand,
    DomainEvent,
    GovernedWorkItem,
    WorkItemIdentity,
    reconstruct_domain,
)
from controller.errors import (
    CommandTargetError,
    ContradictionError,
    DomainError,
    IneligibleDispatchError,
    InvalidTransitionError,
    SpecError,
)
from controller.states import ALL_STATES, LifecycleState
from controller.transitions import allowed_commands
from controller.transitions import dispatch as lifecycle_dispatch
from tests.util import REPO_ROOT, canonical_state, make_repo, write_state

DISPATCH_CMD = DomainCommand(work_item="CTRL-002", command=CommandName.DISPATCH)


class RealRepositoryDomainTests(unittest.TestCase):
    def test_real_repository_reconstructs_ctrl_013_complete(self) -> None:
        item = reconstruct_domain(REPO_ROOT)
        self.assertEqual(item.identity.work_item, "CTRL-013")
        self.assertEqual(item.identity.work_order_path, "spec/work-items/CTRL-013.md")
        self.assertEqual(item.identity.repository, "pectoraux/controller")
        self.assertIs(item.lifecycle, LifecycleState.COMPLETE)
        self.assertFalse(item.eligibility.eligible)
        self.assertEqual(
            item.completed,
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
        self.assertEqual(
            item.authority.automation_stage,
            "STAGE-7-END-TO-END-AUTONOMOUS-GOVERNED-LOOP",
        )

    def test_real_repository_reconstruction_is_deterministic(self) -> None:
        self.assertEqual(reconstruct_domain(REPO_ROOT), reconstruct_domain(REPO_ROOT))

    def test_real_repository_refuses_dispatch_after_completion(self) -> None:
        """Post-reconciliation demonstration: the completed item is
        ineligible and the domain refuses to dispatch it."""
        item = reconstruct_domain(REPO_ROOT)
        with self.assertRaises(IneligibleDispatchError):
            item.handle(DomainCommand("CTRL-013", CommandName.DISPATCH))

    def test_real_repository_allowed_commands_delegate_to_table(self) -> None:
        item = reconstruct_domain(REPO_ROOT)
        self.assertEqual(item.allowed_commands(), allowed_commands(item.lifecycle))


class EligibilityTests(unittest.TestCase):
    """AC2: eligibility is derived from repository authority only."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_ready_active_uncompleted_item_is_eligible(self) -> None:
        root = make_repo(
            self.base,
            status="READY",
            work_item="CTRL-002",
            state_overrides={"completed": ["CTRL-001"]},
        )
        item = reconstruct_domain(root)
        self.assertTrue(item.eligibility.eligible)
        self.assertIn("lifecycle state is READY", item.eligibility.basis)

    def test_non_ready_status_is_ineligible(self) -> None:
        root = make_repo(self.base, status="DISPATCHED", work_item="CTRL-002")
        item = reconstruct_domain(root)
        self.assertFalse(item.eligibility.eligible)
        self.assertIn("lifecycle state is DISPATCHED, not READY", item.eligibility.basis)

    def test_completed_item_is_ineligible_even_when_ready(self) -> None:
        """A READY item already recorded in completed must not be dispatchable
        — a case the lifecycle table alone cannot detect (AC2 rationale)."""
        root = make_repo(
            self.base,
            status="READY",
            work_item="CTRL-002",
            state_overrides={"completed": ["CTRL-002"]},
        )
        item = reconstruct_domain(root)
        self.assertFalse(item.eligibility.eligible)
        self.assertIn("work item is already recorded in completed", item.eligibility.basis)

    def test_require_fails_closed_with_basis_in_message(self) -> None:
        eligibility = DispatchEligibility(
            work_item="CTRL-002", eligible=False, basis=("lifecycle state is MERGED",)
        )
        with self.assertRaises(IneligibleDispatchError) as ctx:
            eligibility.require()
        self.assertIn("CTRL-002", str(ctx.exception))
        self.assertIn("MERGED", str(ctx.exception))

    def test_require_passes_for_eligible_item(self) -> None:
        DispatchEligibility(
            work_item="CTRL-002", eligible=True, basis=("authority agrees",)
        ).require()

    def test_dispatch_of_ineligible_item_is_refused_by_domain(self) -> None:
        root = make_repo(
            self.base,
            status="READY",
            work_item="CTRL-002",
            state_overrides={"completed": ["CTRL-002"]},
        )
        item = reconstruct_domain(root)
        with self.assertRaises(IneligibleDispatchError):
            item.handle(DomainCommand("CTRL-002", CommandName.DISPATCH))


class FailClosedDomainTests(unittest.TestCase):
    """AC4: malformed/missing/contradictory authority fails closed."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = make_repo(self.base, status="READY", work_item="CTRL-002")

    def test_malformed_state_json_raises_spec_error(self) -> None:
        (self.root / STATE_FILE).write_text("{broken", encoding="utf-8")
        with self.assertRaises(SpecError):
            reconstruct_domain(self.root)

    def test_authority_disagreement_raises_contradiction_error(self) -> None:
        write_state(self.root, canonical_state(status="DISPATCHED", activeWorkItem="CTRL-002"))
        # work-order file still says READY -> contradiction
        with self.assertRaises(ContradictionError):
            reconstruct_domain(self.root)

    def test_missing_work_order_raises_spec_error(self) -> None:
        (self.root / "spec/work-items/CTRL-002.md").unlink()
        with self.assertRaises(SpecError):
            reconstruct_domain(self.root)

    def test_missing_state_file_raises_spec_error(self) -> None:
        (self.root / STATE_FILE).unlink()
        with self.assertRaises(SpecError):
            reconstruct_domain(self.root)


class SerializationTests(unittest.TestCase):
    """AC6: deterministic value serialization for future adapters."""

    def test_work_item_identity_round_trip(self) -> None:
        identity = WorkItemIdentity(
            repository="pectoraux/controller",
            work_item="CTRL-002",
            work_order_path="spec/work-items/CTRL-002.md",
        )
        self.assertEqual(WorkItemIdentity.deserialize(identity.serialize()), identity)

    def test_domain_command_round_trip(self) -> None:
        command = DomainCommand("CTRL-002", CommandName.DISPATCH)
        self.assertEqual(DomainCommand.deserialize(command.serialize()), command)

    def test_domain_event_round_trip(self) -> None:
        event = DomainEvent(
            work_item="CTRL-002",
            command=CommandName.DISPATCH,
            from_state=LifecycleState.READY,
            to_state=LifecycleState.DISPATCHED,
        )
        self.assertEqual(DomainEvent.deserialize(event.serialize()), event)

    def test_serialized_forms_are_flat_string_dicts(self) -> None:
        event = DomainEvent(
            work_item="CTRL-002",
            command=CommandName.APPROVE,
            from_state=LifecycleState.REVIEW_PENDING,
            to_state=LifecycleState.APPROVED,
        )
        serialized = event.serialize()
        self.assertEqual(
            serialized,
            {
                "workItem": "CTRL-002",
                "command": "APPROVE",
                "fromState": "REVIEW_PENDING",
                "toState": "APPROVED",
            },
        )
        self.assertTrue(all(isinstance(v, str) for v in serialized.values()))

    def test_serialization_is_deterministic(self) -> None:
        command = DomainCommand("CTRL-002", CommandName.DISPATCH)
        self.assertEqual(command.serialize(), command.serialize())

    def test_handled_event_survives_round_trip(self) -> None:
        expected = DomainEvent.from_lifecycle_event(
            lifecycle_dispatch(LifecycleState.READY, Command(CommandName.DISPATCH, "CTRL-002"))
        )
        serialized = expected.serialize()
        self.assertEqual(DomainEvent.deserialize(serialized), expected)

    def test_deserialize_rejects_non_object(self) -> None:
        bad_values: tuple[object, ...] = (None, [], "x", 7)
        for bad in bad_values:
            with self.subTest(bad=bad):
                with self.assertRaises(DomainError):
                    DomainCommand.deserialize(bad)
                with self.assertRaises(DomainError):
                    DomainEvent.deserialize(bad)
                with self.assertRaises(DomainError):
                    WorkItemIdentity.deserialize(bad)

    def test_deserialize_rejects_unknown_keys(self) -> None:
        with self.assertRaises(DomainError):
            DomainCommand.deserialize({"workItem": "X", "command": "DISPATCH", "extra": 1})

    def test_deserialize_rejects_missing_keys(self) -> None:
        with self.assertRaises(DomainError):
            DomainCommand.deserialize({"workItem": "X"})

    def test_deserialize_rejects_wrong_types(self) -> None:
        cases: list[object] = [
            {"workItem": 7, "command": "DISPATCH"},
            {"workItem": "", "command": "DISPATCH"},
            {"workItem": "X", "command": 42},
        ]
        for bad in cases:
            with self.subTest(bad=bad):
                with self.assertRaises(DomainError):
                    DomainCommand.deserialize(bad)

    def test_deserialize_rejects_unknown_command(self) -> None:
        with self.assertRaises(DomainError):
            DomainCommand.deserialize({"workItem": "X", "command": "TELEPORT"})

    def test_deserialize_rejects_unknown_states(self) -> None:
        bad_event = {
            "workItem": "X",
            "command": "DISPATCH",
            "fromState": "HALF_READY",
            "toState": "DISPATCHED",
        }
        with self.assertRaises(DomainError):
            DomainEvent.deserialize(bad_event)
        bad_event["fromState"] = "READY"
        bad_event["toState"] = "TELEPORTED"
        with self.assertRaises(DomainError):
            DomainEvent.deserialize(bad_event)


class LifecycleIntegrationTests(unittest.TestCase):
    """AC5: delegation to the CTRL-001 machine, no policy redefinition."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = make_repo(self.base, status="READY", work_item="CTRL-002")
        self.item = reconstruct_domain(self.root)

    def test_handle_delegates_to_frozen_table(self) -> None:
        domain_event = self.item.handle(DISPATCH_CMD)
        lifecycle_event = lifecycle_dispatch(
            LifecycleState.READY, Command(CommandName.DISPATCH, "CTRL-002")
        )
        self.assertEqual(
            domain_event,
            DomainEvent.from_lifecycle_event(lifecycle_event),
        )

    def test_invalid_lifecycle_command_raises_transition_error(self) -> None:
        with self.assertRaises(InvalidTransitionError):
            self.item.handle(DomainCommand("CTRL-002", CommandName.APPROVE))

    def test_foreign_work_item_command_is_rejected(self) -> None:
        with self.assertRaises(CommandTargetError):
            self.item.handle(DomainCommand("CTRL-009", CommandName.DISPATCH))

    def test_allowed_commands_match_the_table_for_every_state(self) -> None:
        for state in ALL_STATES:
            snapshot = self._at_state(state)
            self.assertEqual(snapshot.allowed_commands(), allowed_commands(state), msg=state.value)

    def _at_state(self, state: LifecycleState) -> GovernedWorkItem:
        return GovernedWorkItem(
            identity=self.item.identity,
            lifecycle=state,
            eligibility=self.item.eligibility,
            authority=self.item.authority,
            completed=self.item.completed,
        )


class AdvanceAndIdempotencyTests(unittest.TestCase):
    """AC7: pure advancement; re-application fails deterministically."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = make_repo(self.base, status="READY", work_item="CTRL-002")
        self.item = reconstruct_domain(self.root)

    def test_advance_produces_new_snapshot(self) -> None:
        event = self.item.handle(DISPATCH_CMD)
        advanced = self.item.advance(event)
        self.assertIs(advanced.lifecycle, LifecycleState.DISPATCHED)
        self.assertIs(self.item.lifecycle, LifecycleState.READY)  # original untouched

    def test_advance_updates_eligibility(self) -> None:
        event = self.item.handle(DISPATCH_CMD)
        advanced = self.item.advance(event)
        self.assertFalse(advanced.eligibility.eligible)
        self.assertIn("lifecycle state is DISPATCHED, not READY", advanced.eligibility.basis)

    def test_reapplying_event_fails_deterministically(self) -> None:
        event = self.item.handle(DISPATCH_CMD)
        advanced = self.item.advance(event)
        with self.assertRaises(DomainError):
            advanced.advance(event)

    def test_advance_rejects_mismatched_from_state(self) -> None:
        stale = DomainEvent(
            work_item="CTRL-002",
            command=CommandName.BEGIN_IMPLEMENTATION,
            from_state=LifecycleState.DISPATCHED,
            to_state=LifecycleState.IMPLEMENTING,
        )
        with self.assertRaises(DomainError):
            self.item.advance(stale)

    def test_advance_rejects_foreign_work_item(self) -> None:
        foreign = DomainEvent(
            work_item="CTRL-009",
            command=CommandName.DISPATCH,
            from_state=LifecycleState.READY,
            to_state=LifecycleState.DISPATCHED,
        )
        with self.assertRaises(CommandTargetError):
            self.item.advance(foreign)

    def test_repeated_handle_is_pure(self) -> None:
        first = self.item.handle(DISPATCH_CMD)
        second = self.item.handle(DISPATCH_CMD)
        self.assertEqual(first, second)

    def test_full_lifecycle_walk_via_domain(self) -> None:
        chain = [
            CommandName.DISPATCH,
            CommandName.BEGIN_IMPLEMENTATION,
            CommandName.OPEN_PR,
            CommandName.AWAIT_CI,
            CommandName.RECORD_CI_SUCCESS,
            CommandName.APPROVE,
            CommandName.MERGE,
            CommandName.RECORD_MERGE,
            CommandName.RECONCILE,
            CommandName.RECORD_RECONCILIATION,
            CommandName.ADVANCE,
        ]
        item = self.item
        for name in chain:
            event = item.handle(DomainCommand("CTRL-002", name))
            item = item.advance(event)
        self.assertIs(item.lifecycle, LifecycleState.NEXT_READY)


class ReconstructionTests(unittest.TestCase):
    """AC3: equivalent authority reconstructs to equivalent domain state."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = make_repo(self.base, status="READY", work_item="CTRL-002")

    def test_repeated_reconstruction_is_equal(self) -> None:
        self.assertEqual(reconstruct_domain(self.root), reconstruct_domain(self.root))

    def test_copied_tree_reconstructs_equal_domain(self) -> None:
        twin = self.base / "twin"
        shutil.copytree(self.root, twin)
        self.assertEqual(reconstruct_domain(self.root), reconstruct_domain(twin))

    def test_domain_follows_authority_not_memory(self) -> None:
        write_state(
            self.root,
            canonical_state(status="DISPATCHED", activeWorkItem="CTRL-002"),
        )
        work = self.root / "spec/work-items/CTRL-002.md"
        work.write_text(
            "# CTRL-002 — Synthetic Test Item\n\nStatus: `DISPATCHED`\n", encoding="utf-8"
        )
        item = reconstruct_domain(self.root)
        self.assertIs(item.lifecycle, LifecycleState.DISPATCHED)
        self.assertFalse(item.eligibility.eligible)

    def test_no_local_persistence_is_consulted(self) -> None:
        (self.root / STATE_FILE).unlink()
        with self.assertRaises(SpecError):
            reconstruct_domain(self.root)


class ForgedEventTests(unittest.TestCase):
    """FZ-CTRL002-001: transition-impossible events fail closed everywhere.

    A structurally valid but frozen-table-impossible event (e.g.
    APPROVE issued from READY) must be rejected by BOTH deserialization
    and advance(), through the single shared semantic validation path.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = make_repo(self.base, status="READY", work_item="CTRL-002")
        self.item = reconstruct_domain(self.root)

    def test_impossible_pair_fails_deserialization(self) -> None:
        forged = {
            "workItem": "CTRL-002",
            "command": "APPROVE",
            "fromState": "READY",
            "toState": "APPROVED",
        }
        with self.assertRaises(DomainError):
            DomainEvent.deserialize(forged)

    def test_impossible_pair_fails_advance(self) -> None:
        forged = DomainEvent(
            work_item="CTRL-002",
            command=CommandName.APPROVE,
            from_state=LifecycleState.READY,
            to_state=LifecycleState.APPROVED,
        )
        with self.assertRaises(DomainError):
            self.item.advance(forged)

    def test_wrong_successor_fails_deserialization(self) -> None:
        forged = {
            "workItem": "CTRL-002",
            "command": "DISPATCH",
            "fromState": "READY",
            "toState": "MERGED",
        }
        with self.assertRaises(DomainError):
            DomainEvent.deserialize(forged)

    def test_wrong_successor_fails_advance(self) -> None:
        forged = DomainEvent(
            work_item="CTRL-002",
            command=CommandName.DISPATCH,
            from_state=LifecycleState.READY,
            to_state=LifecycleState.MERGED,
        )
        with self.assertRaises(DomainError):
            self.item.advance(forged)

    def test_table_valid_event_still_round_trips_and_advances(self) -> None:
        event = DomainEvent.deserialize(
            {
                "workItem": "CTRL-002",
                "command": "DISPATCH",
                "fromState": "READY",
                "toState": "DISPATCHED",
            }
        )
        advanced = self.item.advance(event)
        self.assertIs(advanced.lifecycle, LifecycleState.DISPATCHED)

    def test_error_messages_cite_the_frozen_table(self) -> None:
        forged = DomainEvent(
            work_item="CTRL-002",
            command=CommandName.APPROVE,
            from_state=LifecycleState.READY,
            to_state=LifecycleState.APPROVED,
        )
        with self.assertRaises(DomainError) as ctx:
            self.item.advance(forged)
        message = str(ctx.exception)
        self.assertIn("APPROVE", message)
        self.assertIn("READY", message)
        self.assertIn("frozen transition table", message)

    def test_every_table_event_passes_semantic_validation(self) -> None:
        """Positive sweep: every (state, command, successor) in the frozen
        table deserializes and validates without error."""
        from controller.transitions import TRANSITIONS

        for (from_state, command), to_state in TRANSITIONS.items():
            event = DomainEvent.deserialize(
                {
                    "workItem": "CTRL-002",
                    "command": command.value,
                    "fromState": from_state.value,
                    "toState": to_state.value,
                }
            )
            self.assertIs(event.to_state, to_state)


class DomainCLITests(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "controller", *args],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=60,
            check=False,
        )

    def test_domain_real_repository_succeeds(self) -> None:
        result = self._run("domain", "--repo", str(REPO_ROOT))
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("domain model: OK", result.stdout)
        self.assertIn("active work item: CTRL-013", result.stdout)
        self.assertIn("lifecycle state: COMPLETE", result.stdout)
        self.assertIn("dispatch eligibility: INELIGIBLE", result.stdout)

    def test_domain_contradictory_repository_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(
                Path(tmp), status="READY", work_item="CTRL-002", work_item_status="DISPATCHED"
            )
            result = self._run("domain", "--repo", str(root))
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL-CLOSED", result.stderr)

    def test_domain_output_is_deterministic(self) -> None:
        first = self._run("domain", "--repo", str(REPO_ROOT))
        second = self._run("domain", "--repo", str(REPO_ROOT))
        self.assertEqual(first.stdout, second.stdout)


if __name__ == "__main__":
    unittest.main()
