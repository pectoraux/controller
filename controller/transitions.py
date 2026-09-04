"""Deterministic, fail-closed lifecycle transition rules.

The transition table is the frozen architecture's state machine expressed
as data. One lifecycle command advances exactly one state; the three
exception commands (ESCALATE/BLOCK/CANCEL) are valid from any non-terminal
state and land in their matching terminal exception state. Terminal states
accept no commands at all. Any (state, command) pair not present in the
table raises :class:`controller.errors.InvalidTransitionError` — the
controller never guesses, skips, or coerces.

Design note (explicit, for audit): the architecture document specifies the
happy-path chain and the change loop, and names BLOCKED/ESCALATED/CANCELLED
as *terminal exception* states without specifying their entry points. This
module makes the minimal deterministic choice consistent with the worker
protocol (stop/escalate from any state) and the safety gate: exception
commands are admitted from every non-terminal state. Narrowing or widening
this is an architecture decision, not a runtime one.
"""

from __future__ import annotations

from collections.abc import Mapping

from controller.commands import (
    Command,
    CommandName,
    Event,
)
from controller.errors import InvalidTransitionError
from controller.states import (
    TERMINAL_EXCEPTION_STATES,
    LifecycleState,
)

#: Happy-path and change-loop transitions, keyed by (state, command).
#: Derived directly from the architecture state machine.
_CORE_TRANSITIONS: dict[tuple[LifecycleState, CommandName], LifecycleState] = {
    (LifecycleState.READY, CommandName.DISPATCH): LifecycleState.DISPATCHED,
    (LifecycleState.DISPATCHED, CommandName.BEGIN_IMPLEMENTATION): LifecycleState.IMPLEMENTING,
    (LifecycleState.IMPLEMENTING, CommandName.OPEN_PR): LifecycleState.PR_OPEN,
    (LifecycleState.PR_OPEN, CommandName.AWAIT_CI): LifecycleState.CI_PENDING,
    (LifecycleState.CI_PENDING, CommandName.RECORD_CI_SUCCESS): LifecycleState.REVIEW_PENDING,
    (LifecycleState.REVIEW_PENDING, CommandName.REQUEST_CHANGES): LifecycleState.CHANGES_REQUESTED,
    (
        LifecycleState.CHANGES_REQUESTED,
        CommandName.RESUME_IMPLEMENTATION,
    ): LifecycleState.IMPLEMENTING,
    (LifecycleState.REVIEW_PENDING, CommandName.APPROVE): LifecycleState.APPROVED,
    (LifecycleState.APPROVED, CommandName.MERGE): LifecycleState.MERGING,
    (LifecycleState.MERGING, CommandName.RECORD_MERGE): LifecycleState.MERGED,
    (LifecycleState.MERGED, CommandName.RECONCILE): LifecycleState.RECONCILING,
    (LifecycleState.RECONCILING, CommandName.RECORD_RECONCILIATION): LifecycleState.COMPLETE,
    (LifecycleState.COMPLETE, CommandName.ADVANCE): LifecycleState.NEXT_READY,
}

#: Where each exception command lands, from any non-terminal state.
_EXCEPTION_TARGETS: Mapping[CommandName, LifecycleState] = {
    CommandName.ESCALATE: LifecycleState.ESCALATED,
    CommandName.BLOCK: LifecycleState.BLOCKED,
    CommandName.CANCEL: LifecycleState.CANCELLED,
}


def _build_table() -> dict[tuple[LifecycleState, CommandName], LifecycleState]:
    """Compose the complete frozen transition table.

    Core lifecycle transitions plus exception transitions from every
    non-terminal state. Terminal exception states get no outgoing edges.
    """
    table = dict(_CORE_TRANSITIONS)
    for state in LifecycleState:
        if state in TERMINAL_EXCEPTION_STATES:
            continue
        for command, target in _EXCEPTION_TARGETS.items():
            table[(state, command)] = target
    return table


#: The complete, immutable transition table.
TRANSITIONS: Mapping[tuple[LifecycleState, CommandName], LifecycleState] = _build_table()


def allowed_commands(state: LifecycleState) -> frozenset[CommandName]:
    """Return every command accepted from ``state``.

    Terminal exception states return an empty set — the lifecycle is over
    and only an explicit governed act (outside this machine) can restart it.
    """
    return frozenset(command for (s, command) in TRANSITIONS if s == state)


def target_state(state: LifecycleState, command: CommandName) -> LifecycleState:
    """Return the deterministic successor state, or fail closed.

    Raises :class:`InvalidTransitionError` when the pair is absent from the
    frozen table. This is the single enforcement point for transition
    validity.
    """
    try:
        return TRANSITIONS[(state, command)]
    except KeyError:
        allowed = ", ".join(sorted(c.value for c in allowed_commands(state))) or "none"
        raise InvalidTransitionError(
            f"command {command.value} is not valid from state {state.value} "
            f"for any work item (allowed: {allowed})"
        ) from None


def dispatch(current: LifecycleState, command: Command) -> Event:
    """Validate ``command`` against ``current`` and emit the resulting event.

    This is the command/event boundary's single entry point. Pure and
    deterministic: equal ``(current, command)`` inputs always produce equal
    events. Invalid pairs raise; nothing is emitted, no state changes.
    """
    successor = target_state(current, command.name)
    return Event(
        work_item=command.work_item,
        command=command.name,
        from_state=current,
        to_state=successor,
    )
