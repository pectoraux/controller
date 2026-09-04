"""Shared test utilities: synthetic repository fixtures.

Fixtures are fully local and deterministic — no network, no credentials,
no external services. They build a minimal controller-repository tree with
the same shape as the real one so authority validation can be exercised
hermetically.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: Real repository root (the parent of the tests/ directory).
REPO_ROOT = Path(__file__).resolve().parents[1]

#: The seven non-negotiable architecture rules, all affirmed.
_ALL_RULES_TRUE: dict[str, bool] = {
    "repositoryIsSourceOfTruth": True,
    "controllerRuntimeStateIsReconstructible": True,
    "onePrPerWorkItem": True,
    "workerCannotMerge": True,
    "failClosedOnContradiction": True,
    "humanOperatorIsTemporaryMechanicalController": True,
    "architectMustAnnounceAutomationStage": True,
}


def canonical_state(**overrides: Any) -> dict[str, Any]:
    """Return a valid machine-state dict, with shallow overrides applied."""
    state: dict[str, Any] = {
        "schemaVersion": "0.1",
        "repository": "pectoraux/controller-test",
        "roadmap": "spec/roadmap/roadmap.md",
        "architecture": "spec/architecture/controller-architecture.md",
        "buildProcess": "spec/operations/controller-build-process.md",
        "activeWorkItem": "CTRL-001",
        "status": "READY",
        "automationStage": "STAGE-0-MANUAL-CONTROLLER",
        "completed": [],
        "rules": dict(_ALL_RULES_TRUE),
        "nextAction": "synthetic test authority",
    }
    state.update(overrides)
    return state


def make_repo(
    base: Path,
    *,
    status: str = "READY",
    work_item: str = "CTRL-001",
    state_overrides: dict[str, Any] | None = None,
    work_item_status: str | None = None,
) -> Path:
    """Materialize a synthetic controller repository under ``base``.

    ``work_item_status`` defaults to ``status`` so the tree is internally
    consistent; passing a different value produces a deliberately
    contradictory authority tree for fail-closed tests.
    """
    root = base / "repo"
    (root / "spec/state").mkdir(parents=True, exist_ok=True)
    (root / "spec/roadmap").mkdir(parents=True, exist_ok=True)
    (root / "spec/architecture").mkdir(parents=True, exist_ok=True)
    (root / "spec/operations").mkdir(parents=True, exist_ok=True)
    (root / "spec/work-items").mkdir(parents=True, exist_ok=True)

    state = canonical_state(status=status, active_work_item=work_item)
    if state_overrides is not None:
        state.update(state_overrides)
        if "status" in state_overrides and work_item_status is None:
            work_item_status = str(state_overrides["status"])
    (root / "spec/state/controller-program-state.json").write_text(
        json.dumps(state, indent=2) + "\n", encoding="utf-8"
    )

    # Referenced authority documents: existence is what the loader checks.
    for relative in (
        "spec/roadmap/roadmap.md",
        "spec/architecture/controller-architecture.md",
        "spec/operations/controller-build-process.md",
    ):
        (root / relative).write_text("# synthetic authority stub\n", encoding="utf-8")

    declared = work_item_status if work_item_status is not None else status
    (root / f"spec/work-items/{work_item}.md").write_text(
        f"# {work_item} — Synthetic Test Item\n\n"
        f"Status: `{declared}`\n\nSynthetic work order body.\n",
        encoding="utf-8",
    )
    return root


def write_state(root: Path, state: dict[str, Any]) -> None:
    """Overwrite the machine-state JSON of a synthetic repository."""
    (root / "spec/state/controller-program-state.json").write_text(
        json.dumps(state, indent=2) + "\n", encoding="utf-8"
    )
