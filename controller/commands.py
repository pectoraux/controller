"""Typed command/event boundary — the internal seam for future adapters.

This module defines the closed vocabulary crossing the controller's edge:
external surfaces (the GitHub adapter of CTRL-003 and the Z.ai adapter of
CTRL-004, both *future* work) will translate their observations into
:class:`Command` values, and consume :class:`Event` values as the
controller's authoritative reaction. The boundary is intentionally
adapter-free in CTRL-001: only the contract and the deterministic
dispatch/validation semantics live here.

Determinism rules:

* Commands and events carry no timestamps, UUIDs, or random data.
* :func:`controller.transitions.dispatch` is a pure function of
  ``(current state, command)``; the same pair always yields an equal event.
* Event equality is by value, so replay/fold order plus repository content
  fully determine controller runtime state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from controller.states import LifecycleState


class CommandName(str, Enum):
    """Closed set of commands the controller boundary accepts.

    The first group drives the happy-path lifecycle defined by the frozen
    architecture. The second group (ESCALATE/BLOCK/CANCEL) is **reserved
    vocabulary only**: the architecture names the terminal exception states
    but authorizes no transitions into them, so these commands have no
    entries in the frozen transition table and fail closed from every
    state. Granting them transitions is an explicit architecture decision
    reserved to a future work order.
    """

    DISPATCH = "DISPATCH"
    BEGIN_IMPLEMENTATION = "BEGIN_IMPLEMENTATION"
    OPEN_PR = "OPEN_PR"
    AWAIT_CI = "AWAIT_CI"
    RECORD_CI_SUCCESS = "RECORD_CI_SUCCESS"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    RESUME_IMPLEMENTATION = "RESUME_IMPLEMENTATION"
    APPROVE = "APPROVE"
    MERGE = "MERGE"
    RECORD_MERGE = "RECORD_MERGE"
    RECONCILE = "RECONCILE"
    RECORD_RECONCILIATION = "RECORD_RECONCILIATION"
    ADVANCE = "ADVANCE"

    ESCALATE = "ESCALATE"
    BLOCK = "BLOCK"
    CANCEL = "CANCEL"


#: Reserved exception commands. Present in the vocabulary for the boundary
#: seam, but no transitions into the terminal exception states are
#: authorized by the frozen architecture: dispatching any of these fails
#: closed from every state. Entry policy is deferred to architecture.
EXCEPTION_COMMANDS: frozenset[CommandName] = frozenset(
    {
        CommandName.ESCALATE,
        CommandName.BLOCK,
        CommandName.CANCEL,
    }
)


@dataclass(frozen=True)
class Command:
    """An inbound request to advance one work item's lifecycle.

    ``work_item`` is the repository work-order identifier (for example
    ``"CTRL-001"``). A command is a request, never a guarantee: it is only
    honored if the frozen transition table permits it from the current
    state. Everything else fails closed.
    """

    name: CommandName
    work_item: str


@dataclass(frozen=True)
class Event:
    """The deterministic outcome of an accepted command.

    Events are the controller's only state-changing currency. Future
    adapters persist/relay them; the core remains a pure function. An event
    records which command produced it and the exact from/to state pair, so
    a fold of events over an initial state reproduces runtime state without
    any database.
    """

    work_item: str
    command: CommandName
    from_state: LifecycleState
    to_state: LifecycleState

    def applies_to(self, state: LifecycleState) -> bool:
        """Return whether this event is the successor of ``state``."""
        return self.from_state == state

    def fold(self, state: LifecycleState) -> LifecycleState:
        """Project ``state`` through this event.

        Pure projection used for replay. It performs no validation of its
        own beyond the from-state check: callers folding a trusted event
        history pass the state they believe preceded the event, and a
        mismatch raises rather than guesses.
        """
        if not self.applies_to(state):
            raise ValueError(
                f"event {self.command.value} for {self.work_item} leaves "
                f"{self.from_state.value}, not {state.value}"
            )
        return self.to_state
