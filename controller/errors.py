"""Fail-closed error types for the Controller.

Every controller failure raises one of these exceptions and stops. State is
never guessed, silently repaired, or coerced into a valid shape. Callers are
expected to treat any ``ControllerError`` as a hard stop requiring explicit
human/Architect attention, per the frozen architecture's recovery rule.
"""

from __future__ import annotations


class ControllerError(Exception):
    """Base class for all deterministic controller failures."""


class SpecError(ControllerError):
    """A controller repository authority file is missing or malformed.

    Raised when specification/state files cannot be parsed or do not conform
    to the expected schema. This is a structural defect, not a disagreement
    between sources.
    """


class ContradictionError(ControllerError):
    """Controller repository authority sources disagree with each other.

    Raised when separately authoritative files make incompatible claims
    (for example machine state says a work item is READY while the work
    order file says DISPATCHED). Contradictions must stop the controller;
    they must never be auto-repaired.
    """


class InvalidTransitionError(ControllerError):
    """A command is not permitted from the current lifecycle state.

    Raised for any (state, command) pair that is not present in the frozen
    transition table, including commands issued from terminal states.
    """
