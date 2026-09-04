"""Unit tests: deterministic, fail-closed lifecycle transitions."""

from __future__ import annotations

import unittest

from controller.commands import (
    EXCEPTION_COMMANDS,
    Command,
    CommandName,
    Event,
)
from controller.errors import InvalidTransitionError
from controller.states import (
    ALL_STATES,
    TERMINAL_EXCEPTION_STATES,
    LifecycleState,
)
from controller.transitions import (
    TRANSITIONS,
    allowed_commands,
    dispatch,
    target_state,
)

#: Happy-path command chain from READY to NEXT_READY.
_HAPPY_PATH: list[CommandName] = [
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

#: Review change loop: REQUEST_CHANGES then re-enter implementation.
_CHANGE_LOOP: list[CommandName] = [
    CommandName.REQUEST_CHANGES,
    CommandName.RESUME_IMPLEMENTATION,
    CommandName.OPEN_PR,
    CommandName.AWAIT_CI,
    CommandName.RECORD_CI_SUCCESS,
]

WORK_ITEM = "CTRL-001"


def _run(start: LifecycleState, commands: list[CommandName]) -> tuple[LifecycleState, list[Event]]:
    """Dispatch a command list from ``start``; return final state and events."""
    state = start
    events: list[Event] = []
    for name in commands:
        event = dispatch(state, Command(name, WORK_ITEM))
        state = event.fold(state)
        events.append(event)
    return state, events


class HappyPathTests(unittest.TestCase):
    def test_full_lifecycle_reaches_next_ready(self) -> None:
        final, _ = _run(LifecycleState.READY, _HAPPY_PATH)
        self.assertIs(final, LifecycleState.NEXT_READY)

    def test_every_intermediate_state_is_the_architecture_state(self) -> None:
        expected = [
            LifecycleState.DISPATCHED,
            LifecycleState.IMPLEMENTING,
            LifecycleState.PR_OPEN,
            LifecycleState.CI_PENDING,
            LifecycleState.REVIEW_PENDING,
            LifecycleState.APPROVED,
            LifecycleState.MERGING,
            LifecycleState.MERGED,
            LifecycleState.RECONCILING,
            LifecycleState.COMPLETE,
            LifecycleState.NEXT_READY,
        ]
        state = LifecycleState.READY
        seen: list[LifecycleState] = []
        for name in _HAPPY_PATH:
            state = target_state(state, name)
            seen.append(state)
        self.assertEqual(seen, expected)

    def test_change_loop_returns_to_review_pending_twice(self) -> None:
        # Reach REVIEW_PENDING, then run the change loop two full iterations.
        state, _ = _run(LifecycleState.READY, _HAPPY_PATH[:5])
        self.assertIs(state, LifecycleState.REVIEW_PENDING)
        for iteration in (1, 2):
            for name in _CHANGE_LOOP:
                state = target_state(state, name)
            self.assertIs(
                state,
                LifecycleState.REVIEW_PENDING,
                f"change loop iteration {iteration} must return to REVIEW_PENDING",
            )
        self.assertIs(target_state(state, CommandName.APPROVE), LifecycleState.APPROVED)


class DeterminismTests(unittest.TestCase):
    def test_same_inputs_always_produce_equal_events(self) -> None:
        command = Command(CommandName.DISPATCH, WORK_ITEM)
        first = dispatch(LifecycleState.READY, command)
        for _ in range(100):
            self.assertEqual(dispatch(LifecycleState.READY, command), first)

    def test_repeated_full_run_is_bit_identical(self) -> None:
        first_state, first_events = _run(LifecycleState.READY, _HAPPY_PATH)
        second_state, second_events = _run(LifecycleState.READY, _HAPPY_PATH)
        self.assertEqual(first_state, second_state)
        self.assertEqual(first_events, second_events)

    def test_events_carry_command_and_both_states(self) -> None:
        event = dispatch(LifecycleState.READY, Command(CommandName.DISPATCH, WORK_ITEM))
        self.assertEqual(
            (event.work_item, event.command, event.from_state, event.to_state),
            (WORK_ITEM, CommandName.DISPATCH, LifecycleState.READY, LifecycleState.DISPATCHED),
        )


class FailClosedTests(unittest.TestCase):
    def test_every_untabled_pair_fails_closed(self) -> None:
        """Exhaustive matrix: only table-listed pairs succeed; all else raise."""
        for state in sorted(ALL_STATES, key=lambda s: s.value):
            for name in CommandName:
                pair = (state, name)
                if pair in TRANSITIONS:
                    self.assertIs(target_state(state, name), TRANSITIONS[pair])
                else:
                    with self.assertRaises(InvalidTransitionError, msg=str(pair)):
                        target_state(state, name)

    def test_terminal_states_accept_no_commands(self) -> None:
        for state in TERMINAL_EXCEPTION_STATES:
            self.assertEqual(allowed_commands(state), frozenset())
            for name in CommandName:
                with self.assertRaises(InvalidTransitionError):
                    dispatch(state, Command(name, WORK_ITEM))

    def test_happy_path_shortcuts_are_rejected(self) -> None:
        shortcuts: list[tuple[LifecycleState, CommandName]] = [
            (LifecycleState.READY, CommandName.APPROVE),  # skip dispatch+review
            (LifecycleState.READY, CommandName.MERGE),
            (LifecycleState.DISPATCHED, CommandName.OPEN_PR),  # skip implementing
            (LifecycleState.CI_PENDING, CommandName.APPROVE),  # CI not recorded
            (LifecycleState.REVIEW_PENDING, CommandName.MERGE),  # no approval
            (LifecycleState.APPROVED, CommandName.RECORD_MERGE),  # merge not begun
            (LifecycleState.MERGED, CommandName.ADVANCE),  # reconciliation skipped
            (LifecycleState.NEXT_READY, CommandName.DISPATCH),  # cycle boundary
        ]
        for state, name in shortcuts:
            with self.assertRaises(InvalidTransitionError, msg=f"{state} + {name}"):
                dispatch(state, Command(name, WORK_ITEM))

    def test_error_message_names_allowed_commands(self) -> None:
        with self.assertRaises(InvalidTransitionError) as ctx:
            dispatch(LifecycleState.READY, Command(CommandName.APPROVE, WORK_ITEM))
        message = str(ctx.exception)
        self.assertIn("READY", message)
        self.assertIn("APPROVE", message)
        self.assertIn("DISPATCH", message)

    def test_invalid_dispatch_emits_nothing(self) -> None:
        """An invalid command raises instead of returning a partial event."""
        with self.assertRaises(InvalidTransitionError):
            dispatch(LifecycleState.BLOCKED, Command(CommandName.DISPATCH, WORK_ITEM))


class ExceptionPathTests(unittest.TestCase):
    def test_exception_commands_available_from_every_non_terminal_state(self) -> None:
        non_terminal = ALL_STATES - TERMINAL_EXCEPTION_STATES
        for state in non_terminal:
            self.assertTrue(EXCEPTION_COMMANDS <= allowed_commands(state), msg=state.value)

    def test_exception_commands_reach_matching_terminal_state(self) -> None:
        cases = [
            (CommandName.ESCALATE, LifecycleState.ESCALATED),
            (CommandName.BLOCK, LifecycleState.BLOCKED),
            (CommandName.CANCEL, LifecycleState.CANCELLED),
        ]
        for name, target in cases:
            for state in ALL_STATES - TERMINAL_EXCEPTION_STATES:
                self.assertIs(target_state(state, name), target)

    def test_escalation_from_ready_is_a_terminal_dead_end(self) -> None:
        event = dispatch(LifecycleState.READY, Command(CommandName.ESCALATE, WORK_ITEM))
        self.assertIs(event.to_state, LifecycleState.ESCALATED)
        self.assertEqual(allowed_commands(LifecycleState.ESCALATED), frozenset())


class ReachabilityTests(unittest.TestCase):
    def test_every_state_is_reachable_from_ready(self) -> None:
        """No orphan states: the table covers the whole declared state set."""
        seen = {LifecycleState.READY}
        frontier = [LifecycleState.READY]
        while frontier:
            current = frontier.pop()
            for name in allowed_commands(current):
                successor = target_state(current, name)
                if successor not in seen:
                    seen.add(successor)
                    frontier.append(successor)
        self.assertEqual(seen, set(ALL_STATES))

    def test_event_fold_rejects_wrong_from_state(self) -> None:
        event = dispatch(LifecycleState.READY, Command(CommandName.DISPATCH, WORK_ITEM))
        with self.assertRaises(ValueError):
            event.fold(LifecycleState.DISPATCHED)


if __name__ == "__main__":
    unittest.main()
