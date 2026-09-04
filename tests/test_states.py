"""Unit tests: typed lifecycle states match the frozen architecture."""

from __future__ import annotations

import unittest

from controller.states import (
    ALL_STATES,
    LIFECYCLE_SEQUENCE,
    TERMINAL_EXCEPTION_STATES,
    LifecycleState,
)

#: The exact state set spelled out by spec/architecture/controller-architecture.md.
_ARCHITECTURE_STATES = {
    "READY",
    "DISPATCHED",
    "IMPLEMENTING",
    "PR_OPEN",
    "CI_PENDING",
    "REVIEW_PENDING",
    "CHANGES_REQUESTED",
    "APPROVED",
    "MERGING",
    "MERGED",
    "RECONCILING",
    "COMPLETE",
    "NEXT_READY",
    "BLOCKED",
    "ESCALATED",
    "CANCELLED",
}

_ARCHITECTURE_HAPPY_PATH = [
    "READY",
    "DISPATCHED",
    "IMPLEMENTING",
    "PR_OPEN",
    "CI_PENDING",
    "REVIEW_PENDING",
    "CHANGES_REQUESTED",
    "IMPLEMENTING",
    "REVIEW_PENDING",
    "APPROVED",
    "MERGING",
    "MERGED",
    "RECONCILING",
    "COMPLETE",
    "NEXT_READY",
]


class LifecycleStateTests(unittest.TestCase):
    def test_state_set_matches_architecture_exactly(self) -> None:
        self.assertEqual({state.value for state in ALL_STATES}, _ARCHITECTURE_STATES)
        self.assertEqual(len(ALL_STATES), 16)

    def test_happy_path_sequence_matches_architecture_order(self) -> None:
        self.assertEqual(
            [state.value for state in LIFECYCLE_SEQUENCE],
            _ARCHITECTURE_HAPPY_PATH,
        )

    def test_terminal_exception_states_are_declared(self) -> None:
        self.assertEqual(
            {state.value for state in TERMINAL_EXCEPTION_STATES},
            {"BLOCKED", "ESCALATED", "CANCELLED"},
        )
        self.assertTrue(TERMINAL_EXCEPTION_STATES <= ALL_STATES)

    def test_states_round_trip_through_their_values(self) -> None:
        for state in ALL_STATES:
            self.assertIs(LifecycleState(state.value), state)
            self.assertEqual(state.value, state.name)
            # str-mixin: states compare equal to their wire representation.
            self.assertEqual(state, state.value)

    def test_terminal_states_are_not_on_the_happy_path(self) -> None:
        self.assertEqual(set(LIFECYCLE_SEQUENCE) & TERMINAL_EXCEPTION_STATES, set())


if __name__ == "__main__":
    unittest.main()
