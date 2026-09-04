# CTRL-009 — Recovery / Idempotency

Status: `COMPLETE`

## Objective

Implement the Controller's governed recovery boundary for restart, interruption, and partial-progress conditions using only repository authority and existing GitHub evidence. The recovery logic must reconstruct the first incomplete lifecycle step deterministically, resume only already-authorized mechanical work, fail closed on ambiguity or contradiction, and preserve the semantic Architect boundary. It must not introduce a controller database, hidden queue, alternate lifecycle semantics, or autonomous approval/review decisions.

## Authority

- `spec/architecture/controller-architecture.md`
- `spec/roadmap/roadmap.md`
- `spec/state/controller-program-state.json`
- `spec/operations/controller-build-process.md`
- `spec/operations/architect-control-loop.md`
- `spec/governance/review-protocol.md`
- `spec/governance/worker-protocol.md`
- `spec/work-items/CTRL-001.md`
- `spec/work-items/CTRL-002.md`
- `spec/work-items/CTRL-003.md`
- `spec/work-items/CTRL-004.md`
- `spec/work-items/CTRL-005.md`
- `spec/work-items/CTRL-006.md`
- `spec/work-items/CTRL-007.md`
- `spec/work-items/CTRL-008.md`

## Acceptance / implementation record

CTRL-009 implementation was delivered in PR #26. Architect REQUEST_CHANGES findings FZ-CTRL009-001 and FZ-CTRL009-002 were resolved on the same PR. Final exact approved head `56730cb93afda01ef53ca6797b0ccba2408f972c` passed the worker validation transcript: 555/555 tests + 195 subtests, strict mypy 0 issues, ruff/format clean, `controller validate` and `domain` green, external-I/O guard green, and CTRL-009 audit 8/8 PASS. Architect approval was recorded as review `5118433490`; PR #26 was merged at `3d5e573f121c710386881d8db3ee3476c82176e3`.

FZ-CTRL009-001 required that evidence-ahead at READY/DISPATCHED never direct the provider-start paths a second time. The accepted implementation returns `next_step=None` for those cases and added regressions proving the no-replay contract.

FZ-CTRL009-002 required a carried worker session for CHANGES_REQUESTED resume. The accepted implementation now fails closed with `RecoveryMissingReferenceError` when absent and tests the intact resume with an exact carried session binding.

Implementation scope remained confined to the CTRL-009 surface; frozen CTRL-001..CTRL-008 semantics were not changed. Stage remains `STAGE-1-STATE-MACHINE-AUTOMATION`.

## Merge / reconciliation evidence

- Implementation PR: #26
- Exact approved implementation head: `56730cb93afda01ef53ca6797b0ccba2408f972c`
- Merge commit: `3d5e573f121c710386881d8db3ee3476c82176e3`
- Reconciliation checkpoint: this work-order record and machine state were updated from the observed merge and are committed in the reconciliation PR; no implementation semantics are changed by reconciliation.
