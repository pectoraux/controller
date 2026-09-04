"""Deterministic, fail-closed lifecycle transition rules.

The transition table is the frozen architecture's state machine expressed
as data. Every entry below is directly derivable from the architecture
document's state machine section: the happy-path chain and its embedded
review change loop (``REVIEW_PENDING -> CHANGES_REQUESTED ->
IMPLEMENTING``). One lifecycle command advances exactly one state.

Exception-state entry policy (review iteration 1, CTRL-001):

    The architecture names BLOCKED, ESCALATED and CANCELLED as *terminal
    exception states* but defines no transitions into them. The governance
    documents use "escalate" only as worker/architect/recovery *behavior*,
    never as lifecycle semantics. Therefore no entry transitions are
    authorized here: the three exception states are declared (part of the
    typed state set) but unreachable through this machine, and the
    ESCALATE/BLOCK/CANCEL commands fail closed from every state. Adding
    entry transitions is an explicit architecture decision reserved to a
    future work order; this module must not invent them.

Any (state, command) pair not present in the table raises
:class:`controller.errors.InvalidTransitionError` — the controller never
guesses, skips, or coerces.
"""

from __future__ import annotations

from collections.abc import Mapping

from controller.commands import Command, CommandName, Event
from controller.errors import InvalidTransitionError
from controller.states import LifecycleState

#: The complete transition table: exactly the transitions derivable from
#: the frozen architecture state machine. No exception-state entries.
TRANSITIONS: Mapping[tuple[LifecycleState, CommandName], LifecycleState] = {
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
    validity — including the reserved exception commands, which have no
    authorized transitions at all.
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
