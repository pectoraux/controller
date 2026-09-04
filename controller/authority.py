"""Repository authority loading, validation, and state reconstruction.

The controller repository is the only durable source of truth. This module
reads it and *only* it: machine state JSON, the referenced work-order file,
and the existence of referenced specification documents. There is no
controller database, cache, or sidecar — :func:`reconstruct` derives the
controller's runtime projection purely from repository files, so an
equivalent repository always reconstructs an equivalent controller state
(restart-safe by construction).

Fail-closed policy:

* Malformed/missing files raise :class:`controller.errors.SpecError`.
* Disagreement between authoritative sources (machine state vs work order
  status, machine state vs frozen architecture rules) raises
  :class:`controller.errors.ContradictionError`.
* Nothing is defaulted, guessed, or silently repaired.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from controller.errors import ContradictionError, SpecError
from controller.states import LifecycleState

#: Location of machine state, relative to the repository root.
STATE_FILE = "spec/state/controller-program-state.json"

#: Directory containing work-order files, relative to the repository root.
WORK_ITEMS_DIR = "spec/work-items"

#: The only machine-state schema this controller understands.
SUPPORTED_SCHEMA_VERSION = "0.1"

#: Non-negotiable rules asserted by the frozen architecture. The machine
#: state file must affirm every one of them; a missing or false rule means
#: the repository contradicts its own architecture and must fail closed.
REQUIRED_RULES: tuple[str, ...] = (
    "repositoryIsSourceOfTruth",
    "controllerRuntimeStateIsReconstructible",
    "onePrPerWorkItem",
    "workerCannotMerge",
    "failClosedOnContradiction",
    "humanOperatorIsTemporaryMechanicalController",
    "architectMustAnnounceAutomationStage",
)

_HEADING_RE = re.compile(r"^#\s+([A-Z]+-\d+)\b", re.MULTILINE)
_STATUS_RE = re.compile(r"^Status:\s*`([A-Z_]+)`\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ProgramState:
    """Validated projection of ``spec/state/controller-program-state.json``."""

    schema_version: str
    repository: str
    roadmap: str
    architecture: str
    build_process: str
    active_work_item: str
    status: LifecycleState
    automation_stage: str
    completed: tuple[str, ...]
    rules: Mapping[str, bool]
    next_action: str


@dataclass(frozen=True)
class ControllerState:
    """Runtime projection of the active work item's lifecycle.

    Deliberately tiny: this is the *reconstructible* part of the controller.
    Everything else the controller knows is re-derived from repository
    files on every start. Equality is by value, so two restarts against an
    unchanged repository produce equal states.
    """

    work_item: str
    lifecycle: LifecycleState


def _require_mapping(data: object, context: str) -> Mapping[str, object]:
    if not isinstance(data, dict):
        raise SpecError(f"{context}: expected a JSON object")
    return data


def _require_str(data: Mapping[str, object], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{context}: field '{key}' must be a non-empty string")
    return value


def _require_str_list(data: Mapping[str, object], key: str, context: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SpecError(f"{context}: field '{key}' must be a list of strings")
    return tuple(value)


def _require_rules(data: Mapping[str, object], context: str) -> Mapping[str, bool]:
    value = data.get("rules")
    if not isinstance(value, dict):
        raise SpecError(f"{context}: field 'rules' must be an object")
    rules: dict[str, bool] = {}
    for rule_key, rule_value in value.items():
        if not isinstance(rule_key, str) or not isinstance(rule_value, bool):
            raise SpecError(f"{context}: 'rules' entries must be string-to-boolean")
        rules[rule_key] = rule_value
    for required in REQUIRED_RULES:
        if required not in rules:
            raise ContradictionError(
                f"{context}: machine state omits architecture rule '{required}'"
            )
        if not rules[required]:
            raise ContradictionError(
                f"{context}: machine state contradicts frozen architecture rule "
                f"'{required}' (expected true, found false)"
            )
    return rules


def _parse_lifecycle(value: str, context: str) -> LifecycleState:
    try:
        return LifecycleState(value)
    except ValueError:
        raise SpecError(f"{context}: '{value}' is not a known lifecycle state") from None


def load_program_state(repo_root: Path) -> ProgramState:
    """Load and structurally validate the machine-state JSON.

    Raises :class:`SpecError` for missing files, bad JSON, missing/mistyped
    fields, unknown lifecycle values, or referenced specification paths
    that do not exist. Raises :class:`ContradictionError` when the asserted
    rules contradict the frozen architecture.
    """
    state_path = repo_root / STATE_FILE
    context = str(state_path)
    if not state_path.is_file():
        raise SpecError(f"{context}: machine state file is missing")
    try:
        text = state_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecError(f"{context}: unreadable ({exc})") from exc
    try:
        raw: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SpecError(f"{context}: invalid JSON ({exc})") from exc

    data = _require_mapping(raw, context)

    schema_version = _require_str(data, "schemaVersion", context)
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise SpecError(
            f"{context}: unsupported schemaVersion '{schema_version}' "
            f"(expected '{SUPPORTED_SCHEMA_VERSION}')"
        )

    referenced = {
        "roadmap": _require_str(data, "roadmap", context),
        "architecture": _require_str(data, "architecture", context),
        "buildProcess": _require_str(data, "buildProcess", context),
    }
    for field_name, relative_path in referenced.items():
        if not (repo_root / relative_path).is_file():
            raise SpecError(
                f"{context}: field '{field_name}' references missing file '{relative_path}'"
            )

    status_value = _require_str(data, "status", context)
    rules = _require_rules(data, context)

    return ProgramState(
        schema_version=schema_version,
        repository=_require_str(data, "repository", context),
        roadmap=referenced["roadmap"],
        architecture=referenced["architecture"],
        build_process=referenced["buildProcess"],
        active_work_item=_require_str(data, "activeWorkItem", context),
        status=_parse_lifecycle(status_value, context),
        automation_stage=_require_str(data, "automationStage", context),
        completed=_require_str_list(data, "completed", context),
        rules=rules,
        next_action=_require_str(data, "nextAction", context),
    )


def load_work_item_status(repo_root: Path, work_item: str) -> LifecycleState:
    """Read a work-order file and return its declared ``Status:`` state.

    Raises :class:`SpecError` when the file is missing, lacks a parseable
    heading/Status line, or declares an unknown state. Pure parsing — no
    cross-checking happens here.
    """
    work_item_path = repo_root / WORK_ITEMS_DIR / f"{work_item}.md"
    context = str(work_item_path)
    if not work_item_path.is_file():
        raise SpecError(f"{context}: work-order file is missing")
    text = work_item_path.read_text(encoding="utf-8")

    heading = _HEADING_RE.search(text)
    if heading is None:
        raise SpecError(f"{context}: no 'WORK-ID — title' heading found")
    if heading.group(1) != work_item:
        raise SpecError(
            f"{context}: heading declares work item '{heading.group(1)}', expected '{work_item}'"
        )

    status = _STATUS_RE.search(text)
    if status is None:
        raise SpecError(f"{context}: no 'Status: `STATE`' line found")
    return _parse_lifecycle(status.group(1), context)


def verify_authority(repo_root: Path) -> ProgramState:
    """Load machine state and cross-check it against the work order file.

    This is the full fail-closed validation pass. In addition to the
    structural checks in :func:`load_program_state`, it requires that the
    active work item's declared status agrees with machine state — the two
    independently authoritative sources must not disagree.

    Raises :class:`ContradictionError` on any disagreement.
    """
    program = load_program_state(repo_root)
    work_item_status = load_work_item_status(repo_root, program.active_work_item)
    if work_item_status != program.status:
        raise ContradictionError(
            f"contradictory authority: machine state says {program.active_work_item} "
            f"is {program.status.value}, but its work order says "
            f"{work_item_status.value}"
        )
    return program


def reconstruct(repo_root: Path) -> ControllerState:
    """Reconstruct controller runtime state from repository authority.

    The reconstruction path used on every start/restart. No database, no
    memory of prior processes: the repository alone determines the result.
    """
    program = verify_authority(repo_root)
    return ControllerState(work_item=program.active_work_item, lifecycle=program.status)
