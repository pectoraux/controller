"""Unit tests: the command/event boundary contract (adapter seam)."""

from __future__ import annotations

import dataclasses
import unittest

from controller.commands import (
    EXCEPTION_COMMANDS,
    Command,
    CommandName,
)
from controller.errors import InvalidTransitionError
from controller.states import LifecycleState
from controller.transitions import dispatch

WORK_ITEM = "CTRL-001"


class CommandContractTests(unittest.TestCase):
    def test_command_names_form_a_closed_vocabulary(self) -> None:
        expected = {
            "DISPATCH",
            "BEGIN_IMPLEMENTATION",
            "OPEN_PR",
            "AWAIT_CI",
            "RECORD_CI_SUCCESS",
            "REQUEST_CHANGES",
            "RESUME_IMPLEMENTATION",
            "APPROVE",
            "MERGE",
            "RECORD_MERGE",
            "RECONCILE",
            "RECORD_RECONCILIATION",
            "ADVANCE",
            "ESCALATE",
            "BLOCK",
            "CANCEL",
        }
        self.assertEqual({name.value for name in CommandName}, expected)

    def test_commands_are_immutable(self) -> None:
        command = Command(CommandName.DISPATCH, WORK_ITEM)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            command.work_item = "CTRL-002"  # type: ignore[misc]

    def test_events_are_immutable(self) -> None:
        event = dispatch(LifecycleState.READY, Command(CommandName.DISPATCH, WORK_ITEM))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            event.to_state = LifecycleState.MERGED  # type: ignore[misc]

    def test_events_carry_no_nondeterministic_fields(self) -> None:
        """No timestamps, UUIDs, or sequence numbers smuggled into events."""
        event = dispatch(LifecycleState.READY, Command(CommandName.DISPATCH, WORK_ITEM))
        field_names = {field.name for field in dataclasses.fields(event)}
        self.assertEqual(field_names, {"work_item", "command", "from_state", "to_state"})

    def test_exception_commands_are_exactly_three_reserved(self) -> None:
        """Reserved vocabulary: present at the boundary seam, unauthorized in
        the transition table — dispatch fails closed from every state."""
        self.assertEqual(
            {name.value for name in EXCEPTION_COMMANDS},
            {"ESCALATE", "BLOCK", "CANCEL"},
        )
        for state in LifecycleState:
            for name in EXCEPTION_COMMANDS:
                with self.assertRaises(InvalidTransitionError, msg=f"{state.value} + {name.value}"):
                    dispatch(state, Command(name, WORK_ITEM))


class BoundarySemanticsTests(unittest.TestCase):
    def test_dispatch_is_a_pure_function_of_state_and_command(self) -> None:
        command = Command(CommandName.APPROVE, WORK_ITEM)
        first = dispatch(LifecycleState.REVIEW_PENDING, command)
        second = dispatch(LifecycleState.REVIEW_PENDING, command)
        self.assertEqual(first, second)
        self.assertEqual(dataclasses.asdict(first), dataclasses.asdict(second))

    def test_boundary_rejects_commands_for_foreign_states(self) -> None:
        with self.assertRaises(InvalidTransitionError):
            dispatch(LifecycleState.READY, Command(CommandName.OPEN_PR, WORK_ITEM))

    def test_event_fold_projects_and_validates(self) -> None:
        event = dispatch(LifecycleState.MERGED, Command(CommandName.RECONCILE, WORK_ITEM))
        self.assertTrue(event.applies_to(LifecycleState.MERGED))
        self.assertIs(event.fold(LifecycleState.MERGED), LifecycleState.RECONCILING)
        self.assertFalse(event.applies_to(LifecycleState.COMPLETE))

    def test_command_and_event_values_serialize_deterministically(self) -> None:
        """String enums keep the boundary wire-friendly for future adapters."""
        command = Command(CommandName.DISPATCH, WORK_ITEM)
        event = dispatch(LifecycleState.READY, command)
        self.assertEqual(command.name.value, "DISPATCH")
        self.assertEqual(
            (event.command.value, event.from_state.value, event.to_state.value),
            ("DISPATCH", "READY", "DISPATCHED"),
        )


if __name__ == "__main__":
    unittest.main()
