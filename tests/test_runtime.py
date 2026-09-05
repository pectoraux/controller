"""Integration tests: the CTRL-011 production controller runtime.

Exercises ``controller/runtime.py`` and the governed CLI commands
against hermetic fixtures — a synthetic controlled repository (the
``tests.util`` builder) plus the deterministic GitHub/Z.ai fakes. No
network, no provider tokens, no external services (the forbidden-surface
guard applies to this file like every other source).

Coverage maps to the CTRL-011 acceptance criteria:

* AC1/CLI: ``--help`` exposes the runtime commands; ``status`` is an
  offline authority/position report; governed commands fail closed
  before any provider I/O when the external process configuration is
  incomplete.
* AC2/AC3 (one-shot cycle): authority is re-verified before any remote
  action; exactly one boundary step runs, routed by the CTRL-009 plan;
  the boundary-validated event is projected through the guarded
  recorder (machine state + work-order ``Status:`` line only); the
  cycle report is the complete structured operator output.
* AC4 (bounded polling): unchanged-evidence cycles sleep with
  multiplicative backoff capped at the configured maximum; advancing
  cycles continue immediately and reset the backoff; the hard cycle
  cap bounds every ``run`` invocation; governance positions end the
  loop cleanly. No busy loop: every OBSERVED cycle is followed by a
  sleep.
* AC5 (restart reconstruction): a fresh runtime instance rebuilds its
  carried references from repository authority plus the externally
  supplied process configuration, and the boundary re-proves the
  session identity from live provider state — no durable session
  database exists (the repository tree gains no new files).
* AC6 (token isolation): provider tokens are read only from the
  process environment, never from files; the masked form is the only
  sanctioned emission; no structured output path can carry a token.
* AC7 (fail closed): malformed/contradictory authority aborts the
  cycle before any provider call; provider failures propagate as the
  frozen typed errors; the recorder refuses cross-item, stale, and
  malformed projections — preflighting BOTH authority surfaces
  read-only before either write so a refusal never splits them
  (review iteration-1), and the reconciliation projection refuses
  typed (never a raw JSON/OS error) on unreadable state, cross-item
  identity, non-reconciling positions, and ledger drift; the CLI
  exits non-zero with a FAIL-CLOSED line.
* AC8 (safety boundaries): the dispatch cycle performs exactly one
  provider mutation (the worker start) and zero GitHub mutations; the
  reporting surface carries method+path only; the runtime performs no
  git operations and no roadmap/stage writes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from controller.authority import verify_authority
from controller.domain import DomainEvent
from controller.errors import (
    ContradictionError,
    ControllerError,
    SpecError,
    ZaiAdapterError,
)
from controller.runtime import (
    GITHUB_TOKEN_ENV,
    ZAI_TOKEN_ENV,
    CallRecord,
    ControllerRuntime,
    CycleStatus,
    RecordingGithubTransport,
    RecordingZaiTransport,
    RuntimeConfiguration,
    RuntimeConfigurationError,
    RuntimeRecorder,
    RuntimeRecorderError,
    RuntimeTokens,
)
from controller.states import LifecycleState
from tests.github_fakes import (
    REPO,
    FakeTransport,
    commit_status,
    pull_request,
    ref,
)
from tests.util import REPO_ROOT, make_repo
from tests.zai_fakes import START_PATH, FakeZaiTransport, worker_session

OWNER = "pectoraux"
WORK_ITEM = "CTRL-011"
BRANCH = "ctrl-011-production-controller-runtime"
ARCHITECT = "pectoraux"
BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
SESSION_ID = "zai-sess-ctrl-011-001"
MERGE_SHA = "c" * 40
PR_NUMBER = 36
REQUIRED_CHECKS = ("ci/tests", "ci/validate")
COMPLETED = tuple(f"CTRL-{i:03d}" for i in range(1, 11))
FIXED_TS = "2026-09-05T00:00:00Z"
AUTOMATION_STAGE = "STAGE-1-STATE-MACHINE-AUTOMATION"

LIST_ALL = f"/repos/{REPO}/pulls?state=all&head={OWNER}:{BRANCH}"
LIST_OPEN = f"/repos/{REPO}/pulls?state=open&head={OWNER}:{BRANCH}"
BRANCH_MAIN = f"/repos/{REPO}/branches/main"
STATUS_PATH = f"/repos/{REPO}/commits/{HEAD_SHA}/status"
REVIEWS_PATH = f"/repos/{REPO}/pulls/{PR_NUMBER}/reviews"

STATE_FILE_REL = "spec/state/controller-program-state.json"
WORK_ORDER_REL = f"spec/work-items/{WORK_ITEM}.md"


# ---------------------------------------------------------------------------
# Injectable clock/sleeper doubles (operator telemetry only, never domain)
# ---------------------------------------------------------------------------


class _FixedClock:
    """Deterministic time source: every timestamp is the fixed value."""

    def now(self) -> str:
        return FIXED_TS


class _RecordingSleeper:
    """Sleep double: records the requested intervals instead of blocking."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _open_pr(**overrides: Any) -> dict[str, object]:
    defaults: dict[str, Any] = {
        "number": PR_NUMBER,
        "title": "CTRL-011 — Production Controller Runtime",
        "head_branch": BRANCH,
        "head_sha": HEAD_SHA,
        "base_branch": "main",
        "base_sha": BASE_SHA,
    }
    defaults.update(overrides)
    return pull_request(**defaults)


def _merged_pr(**overrides: Any) -> dict[str, object]:
    defaults: dict[str, Any] = {
        "state": "closed",
        "merged": True,
        "mergeable_state": None,
        "merge_commit_sha": MERGE_SHA,
    }
    defaults.update(overrides)
    return _open_pr(**defaults)


def _github(
    prs_all: list[dict[str, object]] | None = None,
    extra: dict[str, object] | None = None,
) -> FakeTransport:
    """A fake GitHub with the pre-dispatch observation surface wired."""
    responses: dict[str, object] = {
        LIST_ALL: prs_all if prs_all is not None else [],
        LIST_OPEN: [],
        BRANCH_MAIN: ref("main", BASE_SHA),
    }
    if extra:
        responses.update(extra)
    return FakeTransport(responses)


def _zai(
    start_status: str = "active",
    start_pr: int | None = None,
    start_head: str | None = None,
) -> FakeZaiTransport:
    return FakeZaiTransport(
        {
            START_PATH: worker_session(
                session_id=SESSION_ID,
                repository=REPO,
                work_item=WORK_ITEM,
                base_sha=BASE_SHA,
                pr_number=start_pr,
                head_sha=start_head,
                status=start_status,
            ),
        }
    )


def _config(root: Path, **overrides: Any) -> RuntimeConfiguration:
    defaults: dict[str, Any] = {
        "repo_root": root,
        "repository": REPO,
        "required_checks": REQUIRED_CHECKS,
        "architect_reviewer": ARCHITECT,
        "branch": BRANCH,
        "base_sha": BASE_SHA,
    }
    defaults.update(overrides)
    return RuntimeConfiguration(**defaults)


class RuntimeFixture(unittest.TestCase):
    """Shared fixture: a synthetic controlled repository + injectable
    runtime construction (fresh transports, clock, and sleeper per test).

    Each ``_repo`` call materializes a distinct repository directory
    under the test's temporary base, so one test can observe several
    independent runtimes (restart reconstruction, determinism)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self._repo_count = 0

    def _repo(
        self, status: str = "READY", *, work_item_status: str | None = None, **state_overrides: Any
    ) -> Path:
        self._repo_count += 1
        overrides: dict[str, Any] = {
            "repository": REPO,
            "automationStage": AUTOMATION_STAGE,
            "completed": list(COMPLETED),
        }
        overrides.update(state_overrides)
        return make_repo(
            self.base / f"repo-{self._repo_count}",
            status=status,
            work_item=WORK_ITEM,
            state_overrides=overrides,
            work_item_status=work_item_status,
        )

    def _runtime(
        self,
        root: Path,
        github: FakeTransport | None = None,
        zai: FakeZaiTransport | None = None,
        sleeper: _RecordingSleeper | None = None,
        **config_overrides: Any,
    ) -> tuple[ControllerRuntime, FakeTransport, FakeZaiTransport, _RecordingSleeper]:
        github = github if github is not None else _github()
        zai = zai if zai is not None else _zai()
        sleeper = sleeper if sleeper is not None else _RecordingSleeper()
        runtime = ControllerRuntime(
            configuration=_config(root, **config_overrides),
            github_transport=github,
            zai_transport=zai,
            clock=_FixedClock(),
            sleeper=sleeper,
        )
        return runtime, github, zai, sleeper

    def _state_json(self, root: Path) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads((root / STATE_FILE_REL).read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# AC6 — provider-token isolation
# ---------------------------------------------------------------------------


class TokenIsolationTests(unittest.TestCase):
    """Tokens: environment-only construction, masked display, no emission."""

    ENV = {GITHUB_TOKEN_ENV: "gh-live-token-1", ZAI_TOKEN_ENV: "zai-live-token-1"}

    def test_from_environment_reads_the_process_mapping(self) -> None:
        tokens = RuntimeTokens.from_environment(self.ENV)
        self.assertEqual(tokens.github_token, "gh-live-token-1")
        self.assertEqual(tokens.zai_token, "zai-live-token-1")

    def test_missing_github_token_fails_closed(self) -> None:
        env = dict(self.ENV)
        del env[GITHUB_TOKEN_ENV]
        with self.assertRaises(RuntimeConfigurationError) as ctx:
            RuntimeTokens.from_environment(env)
        self.assertIn(GITHUB_TOKEN_ENV, str(ctx.exception))
        self.assertIn("never repository files", str(ctx.exception))

    def test_missing_zai_token_fails_closed(self) -> None:
        env = dict(self.ENV)
        del env[ZAI_TOKEN_ENV]
        with self.assertRaises(RuntimeConfigurationError) as ctx:
            RuntimeTokens.from_environment(env)
        self.assertIn(ZAI_TOKEN_ENV, str(ctx.exception))

    def test_masked_form_emits_no_token_material(self) -> None:
        tokens = RuntimeTokens.from_environment(self.ENV)
        masked = tokens.masked()
        self.assertNotIn("gh-live-token-1", " ".join(masked.values()))
        self.assertNotIn("zai-live-token-1", " ".join(masked.values()))
        self.assertIn("redacted", masked[GITHUB_TOKEN_ENV])

    def test_report_mutations_carry_method_and_path_only(self) -> None:
        record = CallRecord(method="POST", path=START_PATH)
        self.assertTrue(record.is_mutation)
        self.assertEqual((record.method, record.path), ("POST", START_PATH))

    def test_configuration_rejects_empty_policy_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(RuntimeConfigurationError):
                _config(root, required_checks=())
            with self.assertRaises(RuntimeConfigurationError):
                _config(root, architect_reviewer="")

    def test_configuration_rejects_degenerate_poll_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for bad in (
                {"poll_interval_seconds": 0.0},
                {"poll_backoff_multiplier": 0.5},
                {"poll_max_seconds": 1.0, "poll_interval_seconds": 60.0},
                {"max_cycles": 0},
            ):
                with self.assertRaises(RuntimeConfigurationError):
                    _config(root, **bad)


# ---------------------------------------------------------------------------
# AC2/AC3/AC8 — one-shot governed cycle
# ---------------------------------------------------------------------------


class OneShotDispatchCycleTests(RuntimeFixture):
    """The READY dispatch cycle: authority first, one boundary step, the
    guarded projection, the structured report, exactly one mutation."""

    def test_dispatch_cycle_advances_and_projects_the_event(self) -> None:
        root = self._repo("READY")
        runtime, github, zai, _ = self._runtime(root)
        report = runtime.run_one_cycle()

        self.assertIs(report.status, CycleStatus.ADVANCED)
        self.assertEqual(report.work_item, WORK_ITEM)
        self.assertEqual(report.repository, REPO)
        self.assertEqual(report.lifecycle_before, "READY")
        self.assertEqual(report.lifecycle_after, "DISPATCHED")
        self.assertEqual(report.boundary_invoked, "ORCHESTRATOR")
        self.assertEqual(report.recovery_next_step, "DISPATCH")
        self.assertEqual(report.event_command, "DISPATCH")
        self.assertEqual(
            report.mutations,
            (f"POST {START_PATH}",),
        )

        # The governed recording: machine state + work-order Status line.
        state = self._state_json(root)
        self.assertEqual(state["status"], "DISPATCHED")
        order = (root / WORK_ORDER_REL).read_text(encoding="utf-8")
        self.assertIn("Status: `DISPATCHED`", order)
        # Authority remains verifiable after the projection.
        program = verify_authority(root)
        self.assertEqual(program.active_work_item, WORK_ITEM)

        # AC8: exactly one provider mutation (the worker start), and the
        # GitHub side is read-only in this cycle.
        self.assertEqual(len(zai.calls), 1)
        self.assertEqual(zai.calls[0][0], START_PATH)
        self.assertEqual(github.calls_matching("POST", "/repos/"), [])
        self.assertEqual(github.calls_matching("PUT", "/repos/"), [])
        self.assertTrue(all(c[0] == "GET" for c in github.calls))

        # The worker session is carried in memory only (AC5).
        session = runtime._references.worker_session  # noqa: SLF001
        self.assertIsNotNone(session)
        self.assertEqual(session.session_id, SESSION_ID)  # type: ignore[union-attr]

    def test_report_serializes_deterministically(self) -> None:
        root_a = self._repo("READY")
        root_b = self._repo("READY")
        report_a = self._runtime(root_a)[0].run_one_cycle()
        report_b = self._runtime(root_b)[0].run_one_cycle()
        self.assertEqual(report_a.serialize(), report_b.serialize())
        self.assertEqual(report_a.human_summary(), report_b.human_summary())

    def test_serialize_shape_is_the_operator_contract(self) -> None:
        root = self._repo("READY")
        report = self._runtime(root)[0].run_one_cycle()
        value = report.serialize()
        self.assertIsInstance(value, dict)
        for key in (
            "cycle",
            "timestamp",
            "work_item",
            "repository",
            "lifecycle_before",
            "recovery",
            "boundary_invoked",
            "outcome",
            "event",
            "lifecycle_after",
            "mutations",
            "status",
            "guidance",
        ):
            self.assertIn(key, value)
        self.assertEqual(value["timestamp"], FIXED_TS)
        event = cast(dict[str, object], value["event"])
        self.assertEqual(event["from_state"], "READY")
        self.assertEqual(event["to_state"], "DISPATCHED")

    def test_second_cycle_begins_implementation_after_reproof(self) -> None:
        root = self._repo("READY")
        runtime, _, zai, _ = self._runtime(root)
        runtime.run_one_cycle()
        zai.calls.clear()
        report = runtime.run_one_cycle()

        self.assertIs(report.status, CycleStatus.ADVANCED)
        self.assertEqual(report.event_command, "BEGIN_IMPLEMENTATION")
        self.assertEqual(report.lifecycle_before, "DISPATCHED")
        self.assertEqual(report.lifecycle_after, "IMPLEMENTING")
        # The provenance re-proof identifies the worker through exactly
        # one provider start (FZ-CTRL005-002 fork guard).
        self.assertEqual(len(zai.calls), 1)
        self.assertEqual(zai.calls[0][0], START_PATH)
        self.assertEqual(self._state_json(root)["status"], "IMPLEMENTING")

    def test_projection_touches_only_the_two_authority_surfaces(self) -> None:
        root = self._repo("READY")
        before = _tree_snapshot(root)
        self._runtime(root)[0].run_one_cycle()
        after = _tree_snapshot(root)
        # No new files (no durable session database, AC5/AC8).
        self.assertEqual(sorted(before), sorted(after))
        changed = {path for path in before if before[path] != after[path]}
        self.assertEqual(
            changed,
            {STATE_FILE_REL, WORK_ORDER_REL},
        )


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# ---------------------------------------------------------------------------
# AC3 — boundary routing follows the frozen recovery plan
# ---------------------------------------------------------------------------


class BoundaryRoutingTests(RuntimeFixture):
    """The runtime invokes the boundary the plan names — never its own
    policy: EVIDENCE_GATE at CI_PENDING, REVIEW_LOOP observation at
    REVIEW_PENDING without a decision, ARCHITECT_GOVERNANCE at COMPLETE."""

    def _ci_fixture(self) -> FakeTransport:
        return _github(
            prs_all=[_open_pr()],
            extra={
                LIST_OPEN: [_open_pr()],
                STATUS_PATH: commit_status(
                    "pending",
                    [("ci/tests", "pending"), ("ci/validate", "pending")],
                ),
            },
        )

    def test_ci_pending_routes_to_the_evidence_gate_and_polls(self) -> None:
        root = self._repo("CI_PENDING")
        runtime, github, zai, _ = self._runtime(root, github=self._ci_fixture())
        report = runtime.run_one_cycle()

        self.assertEqual(report.boundary_invoked, "EVIDENCE_GATE")
        self.assertIs(report.status, CycleStatus.OBSERVED)
        self.assertIsNone(report.event_command)
        # The gate is read-only: statuses observed (once by the recovery
        # classification, once by the gate itself), zero mutations.
        self.assertTrue(all(c[0] == "GET" for c in github.calls))
        self.assertEqual(zai.calls, [])
        self.assertEqual(len(github.calls_matching("GET", STATUS_PATH)), 2)

    def test_review_pending_without_decision_observes_and_polls(self) -> None:
        root = self._repo("REVIEW_PENDING")
        github = _github(
            prs_all=[_open_pr()],
            extra={
                LIST_OPEN: [_open_pr()],
                STATUS_PATH: commit_status("success", []),
                REVIEWS_PATH: [],
            },
        )
        runtime, github, zai, _ = self._runtime(root, github=github)
        report = runtime.run_one_cycle()

        self.assertEqual(report.boundary_invoked, "REVIEW_LOOP")
        self.assertIs(report.status, CycleStatus.OBSERVED)
        self.assertIsNone(report.event_command)
        self.assertIn("no Architect decision", report.guidance)
        self.assertEqual(zai.calls, [])
        self.assertEqual(github.calls_matching("POST", "/repos/"), [])

    def test_complete_position_reports_governance_and_makes_no_calls(self) -> None:
        root = self._repo("COMPLETE")
        github = _github(prs_all=[_merged_pr()])
        runtime, github, zai, _ = self._runtime(root, github=github)
        report = runtime.run_one_cycle()

        self.assertIs(report.status, CycleStatus.COMPLETED)
        self.assertIsNone(report.boundary_invoked)
        self.assertIsNone(report.event_command)
        self.assertEqual(report.mutations, ())
        self.assertIn("Architect-side governance", report.guidance)
        self.assertEqual(zai.calls, [])
        self.assertTrue(all(c[0] == "GET" for c in github.calls))


# ---------------------------------------------------------------------------
# AC4 — bounded polling with backoff
# ---------------------------------------------------------------------------


class BoundedPollingTests(RuntimeFixture):
    """The long-running mode never busy-loops: every unchanged-evidence
    cycle sleeps; backoff multiplies to the configured cap; advancing
    cycles reset it; the cycle cap bounds every invocation."""

    def _observing_runtime(
        self, root: Path, sleeper: _RecordingSleeper, **overrides: Any
    ) -> ControllerRuntime:
        runtime, _, _, _ = self._runtime(root, sleeper=sleeper, **overrides)
        return runtime

    def test_unchanged_evidence_cycles_back_off_to_the_cap(self) -> None:
        # DISPATCHED without a carried session reference: the
        # orchestrator's step is a pure observation (AwaitingWorker).
        root = self._repo("DISPATCHED")
        sleeper = _RecordingSleeper()
        runtime = self._observing_runtime(
            root,
            sleeper,
            poll_interval_seconds=4.0,
            poll_backoff_multiplier=2.0,
            poll_max_seconds=10.0,
            max_cycles=4,
        )
        reports = runtime.run()

        self.assertEqual(len(reports), 4)
        self.assertTrue(all(r.status is CycleStatus.OBSERVED for r in reports))
        # Sleeps sit BETWEEN observation cycles; intervals double, capped
        # at 10; no trailing sleep when the cap ends the invocation.
        self.assertEqual(sleeper.sleeps, [4.0, 8.0, 10.0])

    def test_advancing_cycle_runs_immediately_and_resets_backoff(self) -> None:
        root = self._repo("READY")
        sleeper = _RecordingSleeper()
        runtime = self._observing_runtime(
            root,
            sleeper,
            poll_interval_seconds=4.0,
            poll_backoff_multiplier=2.0,
            poll_max_seconds=10.0,
            max_cycles=4,
        )
        reports = runtime.run()
        # Cycle 1 dispatches (ADVANCED, continues immediately, no sleep);
        # cycle 2 proves the session and begins implementation (ADVANCED);
        # IMPLEMENTING with no PR yet observes (AwaitingPullRequest) and
        # polls — the sleep separates the observation cycles only.
        self.assertEqual(
            [r.status for r in reports],
            [
                CycleStatus.ADVANCED,
                CycleStatus.ADVANCED,
                CycleStatus.OBSERVED,
                CycleStatus.OBSERVED,
            ],
        )
        self.assertEqual(sleeper.sleeps, [4.0])

    def test_run_stops_cleanly_on_governance_completion(self) -> None:
        root = self._repo("COMPLETE")
        github = _github(prs_all=[_merged_pr()])
        sleeper = _RecordingSleeper()
        runtime, _, _, _ = self._runtime(root, github=github, sleeper=sleeper)
        reports = runtime.run()
        self.assertEqual(len(reports), 1)
        self.assertIs(reports[0].status, CycleStatus.COMPLETED)
        self.assertEqual(sleeper.sleeps, [])

    def test_cycle_cap_bounds_the_invocation(self) -> None:
        root = self._repo("DISPATCHED")
        sleeper = _RecordingSleeper()
        runtime = self._observing_runtime(root, sleeper, max_cycles=2)
        reports = runtime.run()
        self.assertEqual(len(reports), 2)
        self.assertEqual(sleeper.sleeps, [60.0])


# ---------------------------------------------------------------------------
# AC5 — restart reconstruction
# ---------------------------------------------------------------------------


class RestartReconstructionTests(RuntimeFixture):
    """A fresh runtime process reconstructs everything from repository
    authority + external process configuration + live provider evidence;
    no durable session database exists."""

    def test_fresh_instance_resumes_from_external_configuration(self) -> None:
        root = self._repo("READY")
        # Process A: the dispatch cycle (the session exists only in A's
        # memory; nothing durable is written beyond the event projection).
        runtime_a, _, _, _ = self._runtime(root)
        report_a = runtime_a.run_one_cycle()
        self.assertEqual(report_a.event_command, "DISPATCH")

        # Process B: a completely fresh runtime — no shared state — whose
        # operator configuration carries the session identity and the
        # dispatch base reconstructed from the delivery transcript.
        runtime_b, github_b, zai_b, _ = self._runtime(
            root, session_id=SESSION_ID, base_sha=BASE_SHA, branch=BRANCH
        )
        report_b = runtime_b.run_one_cycle()

        self.assertIs(report_b.status, CycleStatus.ADVANCED)
        self.assertEqual(report_b.event_command, "BEGIN_IMPLEMENTATION")
        self.assertEqual(report_b.lifecycle_before, "DISPATCHED")
        self.assertEqual(report_b.lifecycle_after, "IMPLEMENTING")
        # The boundary re-proved the session identity through exactly one
        # provider start call (the request-form session is a reference,
        # never proof — FZ-CTRL005-002).
        self.assertEqual([c[0] for c in zai_b.calls], [START_PATH])
        self.assertEqual(self._state_json(root)["status"], "IMPLEMENTING")

    def test_restart_writes_no_session_database(self) -> None:
        root = self._repo("READY")
        self._runtime(root)[0].run_one_cycle()
        snapshot_after_a = _tree_snapshot(root)
        self._runtime(root, session_id=SESSION_ID)[0].run_one_cycle()
        snapshot_after_b = _tree_snapshot(root)
        # The file set never grows: no session store, no cache, no
        # sidecar (the repository is the only durable truth).
        self.assertEqual(sorted(snapshot_after_a), sorted(snapshot_after_b))
        self.assertEqual(
            {p for p in snapshot_after_a if snapshot_after_a[p] != snapshot_after_b[p]},
            {STATE_FILE_REL, WORK_ORDER_REL},
        )

    def test_fresh_instance_without_session_reference_awaits(self) -> None:
        root = self._repo("DISPATCHED")
        runtime, _, zai, _ = self._runtime(root)
        report = runtime.run_one_cycle()
        # No session identity supplied: the orchestrator's step is the
        # pure AwaitingWorker observation — never a guessed start.
        self.assertIs(report.status, CycleStatus.OBSERVED)
        self.assertEqual(zai.calls, [])
        self.assertIn("session", report.guidance)


# ---------------------------------------------------------------------------
# AC7 — fail-closed behavior
# ---------------------------------------------------------------------------


class FailClosedCycleTests(RuntimeFixture):
    """Contradictions abort before any provider call; provider failures
    propagate as the frozen typed errors; nothing is retried or guessed."""

    def test_malformed_authority_aborts_before_any_provider_call(self) -> None:
        root = self._repo("READY")
        (root / STATE_FILE_REL).write_text("{not json", encoding="utf-8")
        runtime, github, zai, _ = self._runtime(root)
        with self.assertRaises(SpecError):
            runtime.run_one_cycle()
        self.assertEqual(github.calls, [])
        self.assertEqual(zai.calls, [])

    def test_contradictory_authority_aborts_before_any_provider_call(self) -> None:
        root = self._repo("READY", work_item_status="DISPATCHED")
        runtime, github, zai, _ = self._runtime(root)
        with self.assertRaises(ContradictionError):
            runtime.run_one_cycle()
        self.assertEqual(github.calls, [])
        self.assertEqual(zai.calls, [])

    def test_missing_correlation_references_fail_closed(self) -> None:
        root = self._repo("READY")
        runtime, github, zai, _ = self._runtime(root, branch=None, base_sha=None)
        with self.assertRaises(ControllerError):
            runtime.run_one_cycle()
        self.assertEqual(zai.calls, [])

    def test_provider_failure_propagates_unretried(self) -> None:
        root = self._repo("READY")
        zai = FakeZaiTransport(raise_for={START_PATH: ZaiAdapterError("provider unavailable")})
        runtime, _, zai, _ = self._runtime(root, zai=zai)
        with self.assertRaises(ZaiAdapterError):
            runtime.run_one_cycle()
        # One attempt, zero automatic retry (fail closed, AC7).
        self.assertEqual(len(zai.calls), 1)


class RecorderGuardTests(RuntimeFixture):
    """The governed recording refuses every ambiguous projection.

    Review iteration-1 regressions: every refusal must leave BOTH
    authority surfaces byte-identical (the recorder preflights the
    machine state and the work-order Status line read-only before
    either write), and the reconciliation projection refuses — typed,
    never a raw JSON/OS error — on malformed records, unreadable state,
    cross-item identity, non-reconciling positions, and ledger drift.
    """

    def _event(self, work_item: str, from_state: str, to_state: str) -> DomainEvent:
        return DomainEvent(
            work_item=work_item,
            command=None,  # type: ignore[arg-type]
            from_state=LifecycleState(from_state),
            to_state=LifecycleState(to_state),
        )

    def _bytes(self, root: Path, relative: str) -> bytes:
        return (root / relative).read_bytes()

    # -- project_event: refusal leaves BOTH surfaces unchanged ---------------

    def test_cross_item_projection_is_refused(self) -> None:
        root = self._repo("READY")
        state_before = self._bytes(root, STATE_FILE_REL)
        recorder = RuntimeRecorder()
        with self.assertRaises(RuntimeRecorderError):
            recorder.project_event(root, self._event("CTRL-002", "READY", "DISPATCHED"))
        self.assertEqual(self._bytes(root, STATE_FILE_REL), state_before)

    def test_stale_from_state_is_refused(self) -> None:
        root = self._repo("READY")
        state_before = self._bytes(root, STATE_FILE_REL)
        recorder = RuntimeRecorder()
        with self.assertRaises(RuntimeRecorderError):
            recorder.project_event(root, self._event(WORK_ITEM, "DISPATCHED", "IMPLEMENTING"))
        self.assertEqual(self._bytes(root, STATE_FILE_REL), state_before)

    def test_unreadable_machine_state_is_refused(self) -> None:
        root = self._repo("READY")
        (root / STATE_FILE_REL).write_text("[]", encoding="utf-8")
        order_before = self._bytes(root, WORK_ORDER_REL)
        recorder = RuntimeRecorder()
        with self.assertRaises(RuntimeRecorderError):
            recorder.project_event(root, self._event(WORK_ITEM, "READY", "DISPATCHED"))
        self.assertEqual(self._bytes(root, WORK_ORDER_REL), order_before)

    def test_stale_work_order_status_refuses_with_zero_projection_writes(self) -> None:
        """The review iteration-1 headline regression: the work order's
        Status line moved (or was never aligned) while the machine state
        stayed — the projection is refused and NEITHER surface is
        written (the old recorder substituted blindly after already
        mutating the machine state)."""
        root = self._repo("READY", work_item_status="DISPATCHED")
        state_before = self._bytes(root, STATE_FILE_REL)
        order_before = self._bytes(root, WORK_ORDER_REL)
        recorder = RuntimeRecorder()
        with self.assertRaises(RuntimeRecorderError) as ctx:
            recorder.project_event(root, self._event(WORK_ITEM, "READY", "DISPATCHED"))
        self.assertIn("two authority surfaces disagree", str(ctx.exception))
        self.assertEqual(self._bytes(root, STATE_FILE_REL), state_before)
        self.assertEqual(self._bytes(root, WORK_ORDER_REL), order_before)

    def test_missing_work_order_status_line_refuses_without_any_write(self) -> None:
        root = self._repo("READY")
        order_path = root / WORK_ORDER_REL
        order_path.write_text(
            f"# {WORK_ITEM} — Synthetic Test Item\n\nNo status line at all.\n",
            encoding="utf-8",
        )
        state_before = self._bytes(root, STATE_FILE_REL)
        order_before = self._bytes(root, WORK_ORDER_REL)
        recorder = RuntimeRecorder()
        with self.assertRaises(RuntimeRecorderError) as ctx:
            recorder.project_event(root, self._event(WORK_ITEM, "READY", "DISPATCHED"))
        self.assertIn("lost its Status line", str(ctx.exception))
        self.assertEqual(self._bytes(root, STATE_FILE_REL), state_before)
        self.assertEqual(self._bytes(root, WORK_ORDER_REL), order_before)

    def test_malformed_work_order_status_line_refuses_without_any_write(self) -> None:
        root = self._repo("READY")
        order_path = root / WORK_ORDER_REL
        order_path.write_text(
            f"# {WORK_ITEM} — Synthetic Test Item\n\nStatus: READY\n\nSynthetic work order body.\n",
            encoding="utf-8",
        )
        state_before = self._bytes(root, STATE_FILE_REL)
        recorder = RuntimeRecorder()
        with self.assertRaises(RuntimeRecorderError) as ctx:
            recorder.project_event(root, self._event(WORK_ITEM, "READY", "DISPATCHED"))
        self.assertIn("malformed Status line", str(ctx.exception))
        self.assertEqual(self._bytes(root, STATE_FILE_REL), state_before)

    def test_ambiguous_status_lines_refuse_without_any_write(self) -> None:
        root = self._repo("READY")
        order_path = root / WORK_ORDER_REL
        order_path.write_text(
            f"# {WORK_ITEM} — Synthetic Test Item\n\nStatus: `READY`\n\n"
            "Synthetic body.\n\nStatus: `DISPATCHED`\n",
            encoding="utf-8",
        )
        state_before = self._bytes(root, STATE_FILE_REL)
        recorder = RuntimeRecorder()
        with self.assertRaises(RuntimeRecorderError) as ctx:
            recorder.project_event(root, self._event(WORK_ITEM, "READY", "DISPATCHED"))
        self.assertIn("ambiguous authority surface", str(ctx.exception))
        self.assertEqual(self._bytes(root, STATE_FILE_REL), state_before)

    def test_unreadable_work_order_refuses_with_machine_state_unchanged(self) -> None:
        """The split-surface regression: the old recorder mutated the
        machine state first and failed on the work order read afterward;
        the preflight ordering refuses with the machine state intact."""
        root = self._repo("READY")
        (root / WORK_ORDER_REL).unlink()
        state_before = self._bytes(root, STATE_FILE_REL)
        recorder = RuntimeRecorder()
        with self.assertRaises(RuntimeRecorderError) as ctx:
            recorder.project_event(root, self._event(WORK_ITEM, "READY", "DISPATCHED"))
        self.assertIn("unreadable", str(ctx.exception))
        self.assertEqual(self._bytes(root, STATE_FILE_REL), state_before)

    def test_event_projection_writes_both_surfaces_coherently(self) -> None:
        """The happy path after the preflight reordering: one event moves
        the machine state and the work-order Status line together, and
        the whole tree stays authority-verifiable."""
        root = self._repo("READY")
        recorder = RuntimeRecorder()
        recorder.project_event(root, self._event(WORK_ITEM, "READY", "DISPATCHED"))
        state = self._state_json(root)
        self.assertEqual(state["status"], "DISPATCHED")
        self.assertIn("Status: `DISPATCHED`", (root / WORK_ORDER_REL).read_text(encoding="utf-8"))
        verify_authority(root)

    # -- project_reconciliation: typed, coherent, no partial write ------------

    def _reconciliation_record(self, **overrides: Any) -> dict[str, Any]:
        record: dict[str, Any] = {
            "work_item": WORK_ITEM,
            "completed_before": list(COMPLETED),
            "completed_after": list(COMPLETED) + [WORK_ITEM],
        }
        record.update(overrides)
        return record

    def test_malformed_reconciliation_ledger_is_refused(self) -> None:
        root = self._repo("RECONCILING")
        state_before = self._bytes(root, STATE_FILE_REL)
        recorder = RuntimeRecorder()
        with self.assertRaises(RuntimeRecorderError):
            recorder.project_reconciliation(root, {"completed_after": "CTRL-001"})
        self.assertEqual(self._bytes(root, STATE_FILE_REL), state_before)

    def test_reconciliation_without_identity_is_refused(self) -> None:
        root = self._repo("RECONCILING")
        state_before = self._bytes(root, STATE_FILE_REL)
        recorder = RuntimeRecorder()
        with self.assertRaises(RuntimeRecorderError) as ctx:
            recorder.project_reconciliation(root, self._reconciliation_record(work_item=None))
        self.assertIn("does not name its completed work item", str(ctx.exception))
        self.assertEqual(self._bytes(root, STATE_FILE_REL), state_before)

    def test_reconciliation_malformed_completed_before_is_refused(self) -> None:
        root = self._repo("RECONCILING")
        state_before = self._bytes(root, STATE_FILE_REL)
        recorder = RuntimeRecorder()
        with self.assertRaises(RuntimeRecorderError) as ctx:
            recorder.project_reconciliation(
                root, self._reconciliation_record(completed_before="CTRL-001")
            )
        self.assertIn("completed-before ledger is malformed", str(ctx.exception))
        self.assertEqual(self._bytes(root, STATE_FILE_REL), state_before)

    def test_reconciliation_unreadable_machine_state_is_typed(self) -> None:
        root = self._repo("RECONCILING")
        recorder = RuntimeRecorder()
        record = self._reconciliation_record()
        # Invalid JSON, a non-object, and a missing file each surface the
        # typed recorder error — never a raw JSONDecodeError/OSError.
        (root / STATE_FILE_REL).write_text("not json at all", encoding="utf-8")
        with self.assertRaises(RuntimeRecorderError):
            recorder.project_reconciliation(root, record)
        (root / STATE_FILE_REL).write_text("[]", encoding="utf-8")
        with self.assertRaises(RuntimeRecorderError):
            recorder.project_reconciliation(root, record)
        (root / STATE_FILE_REL).unlink()
        with self.assertRaises(RuntimeRecorderError):
            recorder.project_reconciliation(root, record)

    def test_reconciliation_cross_item_identity_is_refused(self) -> None:
        root = self._repo("RECONCILING")
        state_before = self._bytes(root, STATE_FILE_REL)
        recorder = RuntimeRecorder()
        with self.assertRaises(RuntimeRecorderError) as ctx:
            recorder.project_reconciliation(root, self._reconciliation_record(work_item="CTRL-002"))
        self.assertIn("cross-item recording is refused", str(ctx.exception))
        self.assertEqual(self._bytes(root, STATE_FILE_REL), state_before)

    def test_reconciliation_position_not_reconciling_is_refused(self) -> None:
        root = self._repo("MERGED")
        state_before = self._bytes(root, STATE_FILE_REL)
        recorder = RuntimeRecorder()
        with self.assertRaises(RuntimeRecorderError) as ctx:
            recorder.project_reconciliation(root, self._reconciliation_record())
        self.assertIn("fail closed, never overwrite", str(ctx.exception))
        self.assertEqual(self._bytes(root, STATE_FILE_REL), state_before)

    def test_reconciliation_ledger_drift_is_refused(self) -> None:
        root = self._repo("RECONCILING")
        state_before = self._bytes(root, STATE_FILE_REL)
        recorder = RuntimeRecorder()
        drifted = self._reconciliation_record(completed_before=list(COMPLETED)[:-1])
        with self.assertRaises(RuntimeRecorderError) as ctx:
            recorder.project_reconciliation(root, drifted)
        self.assertIn("drifted from the record's derivation basis", str(ctx.exception))
        self.assertEqual(self._bytes(root, STATE_FILE_REL), state_before)

    def test_reconciliation_projects_only_the_completed_ledger(self) -> None:
        root = self._repo("RECONCILING")
        recorder = RuntimeRecorder()
        before = self._state_json(root)
        recorder.project_reconciliation(root, self._reconciliation_record())
        after = self._state_json(root)
        self.assertEqual(after["completed"], list(COMPLETED) + [WORK_ITEM])
        # Nothing else moved: no stage change, no next-item activation,
        # no status/identity change — the ledger is the only projection.
        for key in ("automationStage", "activeWorkItem", "status", "nextAction"):
            self.assertEqual(after[key], before[key])
        verify_authority(root)


# ---------------------------------------------------------------------------
# AC1 — the CLI surface
# ---------------------------------------------------------------------------


def _run_controller(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    import os

    merged = dict(os.environ)
    for var in (GITHUB_TOKEN_ENV, ZAI_TOKEN_ENV):
        merged.pop(var, None)
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "controller", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=60,
        check=False,
        env=merged,
    )


class CliSurfaceTests(unittest.TestCase):
    """--help, offline status, and fail-closed-before-network semantics."""

    def test_help_exposes_the_runtime_commands(self) -> None:
        result = _run_controller("--help")
        self.assertEqual(result.returncode, 0)
        for command in ("validate", "domain", "status", "cycle", "run"):
            self.assertIn(command, result.stdout)

    def test_cycle_help_documents_the_governed_flags(self) -> None:
        result = _run_controller("cycle", "--help")
        self.assertEqual(result.returncode, 0)
        for flag in (
            "--required-checks",
            "--architect-reviewer",
            "--base-sha",
            "--session-id",
            "--json",
        ):
            self.assertIn(flag, result.stdout)

    def test_status_reports_the_real_repository_offline(self) -> None:
        result = _run_controller("status", "--repo", str(REPO_ROOT))
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("controller status: OK", result.stdout)
        self.assertIn("active work item: CTRL-013", result.stdout)
        self.assertIn("lifecycle state: COMPLETE", result.stdout)
        self.assertIn("owning boundary (frozen routing): ARCHITECT_GOVERNANCE", result.stdout)
        self.assertIn("STAGE-7-END-TO-END-AUTONOMOUS-GOVERNED-LOOP", result.stdout)

    def test_cycle_without_external_tokens_fails_closed_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            result = _run_controller(
                "cycle",
                "--repo",
                str(root),
                "--required-checks",
                "ci/tests",
                "--architect-reviewer",
                ARCHITECT,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL-CLOSED", result.stderr)
        self.assertIn(GITHUB_TOKEN_ENV, result.stderr)

    def test_run_without_external_tokens_fails_closed_before_network(self) -> None:
        result = _run_controller(
            "run",
            "--repo",
            str(REPO_ROOT),
            "--required-checks",
            "ci/tests",
            "--architect-reviewer",
            ARCHITECT,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL-CLOSED", result.stderr)

    def test_cycle_with_malformed_authority_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            (root / STATE_FILE_REL).write_text("{broken", encoding="utf-8")
            result = _run_controller(
                "cycle",
                "--repo",
                str(root),
                "--required-checks",
                "ci/tests",
                "--architect-reviewer",
                ARCHITECT,
                env={
                    GITHUB_TOKEN_ENV: "x" * 40,
                    ZAI_TOKEN_ENV: "y" * 40,
                },
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL-CLOSED", result.stderr)

    def test_run_with_degenerate_poll_configuration_fails_closed(self) -> None:
        result = _run_controller(
            "run",
            "--repo",
            str(REPO_ROOT),
            "--required-checks",
            "ci/tests",
            "--architect-reviewer",
            ARCHITECT,
            "--poll-interval",
            "0",
            env={
                GITHUB_TOKEN_ENV: "x" * 40,
                ZAI_TOKEN_ENV: "y" * 40,
            },
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL-CLOSED", result.stderr)


# ---------------------------------------------------------------------------
# AC8 — structural safety guards
# ---------------------------------------------------------------------------


class RecordingTransportTests(unittest.TestCase):
    """The mutation proof surface records method+path and passes through."""

    def test_github_recording_transport_wraps_calls(self) -> None:
        inner = FakeTransport({"/x": {"ok": True}, "/y": {"ok": True}, "/z": {"ok": True}})
        recording = RecordingGithubTransport(inner)
        value = recording.get_json("/x")
        self.assertEqual(value, {"ok": True})
        recording.post_json("/y", {"a": 1})
        recording.put_json("/z", {"b": 2})
        self.assertEqual(
            [(c.method, c.path) for c in recording.calls],
            [("GET", "/x"), ("POST", "/y"), ("PUT", "/z")],
        )
        self.assertEqual(
            [c.method for c in recording.calls if c.is_mutation],
            ["POST", "PUT"],
        )

    def test_zai_recording_transport_wraps_calls(self) -> None:
        inner = FakeZaiTransport({"/w": {"ok": True}})
        recording = RecordingZaiTransport(inner)
        value = recording.post_json("/w", {"a": 1})
        self.assertEqual(value, {"ok": True})
        self.assertEqual([(c.method, c.path) for c in recording.calls], [("POST", "/w")])


class RuntimeSafetySurfaceTests(unittest.TestCase):
    """The runtime source itself stays inside the CTRL-011 authority."""

    SOURCE = (REPO_ROOT / "controller" / "runtime.py").read_text(encoding="utf-8")

    def test_runtime_performs_no_git_or_roadmap_operations(self) -> None:
        for forbidden in (
            "import subprocess",
            "roadmap.md",
            "architecture.md",
            "automationStage",
        ):
            self.assertNotIn(forbidden, self.SOURCE)

    def test_runtime_calls_no_transport_directly_outside_recorders(self) -> None:
        # The only transport call sites are the recording wrappers'
        # pass-throughs; every governed mutation flows through the
        # accepted boundaries' own adapters.
        import re

        put_sites = [line for line in self.SOURCE.splitlines() if re.search(r"\.put_json\(", line)]
        self.assertEqual(put_sites, ["        return self._inner.put_json(path, payload)"])

    def test_no_token_material_in_source(self) -> None:
        for literal in ("ghp_", "github_pat_", "BEGIN PRIVATE KEY"):
            self.assertNotIn(literal, self.SOURCE)


if __name__ == "__main__":
    unittest.main()
