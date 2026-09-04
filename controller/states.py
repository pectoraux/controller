"""Typed lifecycle states for a governed work item.

The state set is frozen verbatim from ``spec/architecture/controller-architecture.md``
(State machine section)::

    READY -> DISPATCHED -> IMPLEMENTING -> PR_OPEN -> CI_PENDING ->
    REVIEW_PENDING -> CHANGES_REQUESTED -> IMPLEMENTING -> REVIEW_PENDING ->
    APPROVED -> MERGING -> MERGED -> RECONCILING -> COMPLETE -> NEXT_READY

    Terminal exception states: BLOCKED, ESCALATED, CANCELLED.

``NEXT_READY`` marks the boundary of one full cycle: the next work item
begins a new lifecycle at ``READY``. The three terminal exception states
have no outgoing transitions; leaving them is an explicit governed act,
not a runtime transition.
"""

from __future__ import annotations

from enum import Enum


class LifecycleState(str, Enum):
    """Lifecycle state of exactly one governed work item.

    Inherits ``str`` so states serialize losslessly as their own name and
    can be compared against repository machine-state values directly.
    """

    READY = "READY"
    DISPATCHED = "DISPATCHED"
    IMPLEMENTING = "IMPLEMENTING"
    PR_OPEN = "PR_OPEN"
    CI_PENDING = "CI_PENDING"
    REVIEW_PENDING = "REVIEW_PENDING"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    APPROVED = "APPROVED"
    MERGING = "MERGING"
    MERGED = "MERGED"
    RECONCILING = "RECONCILING"
    COMPLETE = "COMPLETE"
    NEXT_READY = "NEXT_READY"
    BLOCKED = "BLOCKED"
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"


#: Happy-path sequence exactly as written in the frozen architecture.
LIFECYCLE_SEQUENCE: tuple[LifecycleState, ...] = (
    LifecycleState.READY,
    LifecycleState.DISPATCHED,
    LifecycleState.IMPLEMENTING,
    LifecycleState.PR_OPEN,
    LifecycleState.CI_PENDING,
    LifecycleState.REVIEW_PENDING,
    LifecycleState.CHANGES_REQUESTED,
    LifecycleState.IMPLEMENTING,
    LifecycleState.REVIEW_PENDING,
    LifecycleState.APPROVED,
    LifecycleState.MERGING,
    LifecycleState.MERGED,
    LifecycleState.RECONCILING,
    LifecycleState.COMPLETE,
    LifecycleState.NEXT_READY,
)

#: Exception states that terminate a lifecycle. No command may leave them.
TERMINAL_EXCEPTION_STATES: frozenset[LifecycleState] = frozenset(
    {
        LifecycleState.BLOCKED,
        LifecycleState.ESCALATED,
        LifecycleState.CANCELLED,
    }
)

#: Every state named by the frozen architecture, lifecycle and exception.
ALL_STATES: frozenset[LifecycleState] = frozenset(LifecycleState)
