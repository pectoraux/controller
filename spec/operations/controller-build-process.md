# Controller Build Process — Bootstrap Through Automation

This document is an authoritative operational guide for building the Controller itself. It explains how the project is bootstrapped before the Controller exists, how responsibility migrates from the human operator to the Controller, and exactly when that migration occurs.

## Source-of-truth rule

The repository remains the only durable source of truth. This document, the authoritative roadmap, frozen architecture, work orders, and machine state must contain everything needed for the next Architect to resume the build. Conversation history is not an implementation dependency.

## The bootstrap problem

The Controller cannot initially orchestrate its own construction because it does not exist yet. Therefore the human operator temporarily performs the Controller's mechanical orchestration role while the Architect and Z.ai worker continue to perform their distinct roles.

This is intentional. The Controller is built using the same governed work-item process that it will eventually automate.

## Roles

| Role | Responsibility during bootstrap | Responsibility after automation |
|---|---|---|
| Human operator | Routes Work Orders/prompts between Architect and Z.ai, starts the next governed step, relays review results, observes/requests actions | Product owner/operator; initiates or authorizes governed runs; no longer acts as message router |
| Architect | Defines/freeze architecture, roadmap and acceptance; reviews PRs; requests changes or approves | Same semantic authority; reviews only when policy says human/Architect judgment is required |
| Z.ai worker | Implements exactly one governed Work Order, tests, pushes branch/PR, responds to review findings | Same implementation role, dispatched by Controller |
| Controller | Does not yet exist; its future responsibilities are performed manually by the human operator | Reads repository authority, dispatches/resumes workers, observes GitHub/CI, carries review packets, retries, enforces gates, merges only when policy permits, reconciles state |
| GitHub/CI | Execution and evidence surface | Same |
| Repository | Sole durable authority | Sole durable authority |

## Automation stages

The migration is incremental. The human operator must be told when a stage has been reached and what work they no longer need to perform manually.

### Stage 0 — Manual controller / bootstrap

**Controller capability:** none.

The human performs the Controller's mechanical loop:

```text
Architect defines/freeze Work Order
        ↓
Human gives Work Order to Z.ai
        ↓
Z.ai implements + tests + opens/updates PR
        ↓
Human brings implementation state to Architect
        ↓
Architect reviews
        ↓
┌─────────────── REQUEST_CHANGES ───────────────┐
│                                               ↓
│                                      Human gives review
│                                      packet back to Z.ai
│                                               │
│                                      Z.ai fixes PR
│                                               │
└───────────────────────────────────────────────┘
        ↓
APPROVE + CI/evidence/gates satisfied
        ↓
Human performs/authorizes merge according to policy
        ↓
Human verifies post-merge state and advances to next Work Order
```

**Human job:** perform all orchestration and routing. The Architect still owns semantic decisions; Z.ai still owns implementation.

**Exit condition:** CTRL-001 and subsequent controller capabilities progressively automate parts of this loop. Do not claim Stage 0 is over merely because the first controller code exists.

### Stage 1 — State-machine automation

**First target:** CTRL-001.

The Controller can reconstruct repository authority and execute deterministic local lifecycle transitions, but cannot yet operate GitHub or Z.ai itself.

**Human job:** still performs external dispatch/review routing, but can use the Controller's persisted state machine as the canonical orchestration model rather than maintaining the lifecycle mentally.

**Exit condition:** the controller's state machine and reconstruction tests are accepted and merged.

### Stage 2 — GitHub observation automation

Target capability: GitHub adapter/observation.

The Controller can observe branches, PRs, commits, reviews and CI and correlate them to the active Work Order.

**Human job removed:** manually checking and transcribing basic PR/CI state.

**Human still performs:** Z.ai dispatch, Architect review, and governed merge decisions.

### Stage 3 — Z.ai dispatch/resume automation

Target capability: Z.ai adapter.

The Controller constructs a repository-derived worker context and starts/resumes Z.ai against the exact Work Order and PR.

**Human job removed:** copying Work Orders/prompts to Z.ai and manually deciding how to resume the same worker/PR.

**Human still performs:** semantic Architect review and exceptional intervention.

### Stage 4 — Review/change-loop automation

Target capability: durable Architect review packets plus worker resumption.

The Controller detects `REQUEST_CHANGES`, persists the review packet, and supplies the exact findings to Z.ai for the next iteration.

**Human job removed:** manually relaying review comments/findings to Z.ai.

**Human still performs:** the actual Architect review when semantic judgment is required.

### Stage 5 — CI/evidence/retry automation

Target capability: CI/evidence gate.

The Controller watches required checks, classifies retryable failures where policy permits, and resumes the worker for implementation failures.

**Human job removed:** routine CI polling, evidence collection, and mechanical retry routing.

**Human still performs:** unresolved/ambiguous failures and governance exceptions.

### Stage 6 — Merge/reconciliation automation

Target capability: merge + post-merge reconciliation.

Only after all merge predicates are satisfied may the Controller perform an authorized merge and reconcile repository machine state.

**Human job removed:** mechanical merge clicking and routine post-merge bookkeeping.

**Human still retains:** authority to define/change policy and intervene in contradictions or unsafe conditions.

### Stage 7 — End-to-end autonomous governed loop

Target capability: recovery/idempotency + dogfood.

The Controller can safely take a repository-authorized READY Work Order through:

```text
READY
 → dispatch
 → implementation
 → PR
 → CI/evidence
 → Architect review
 → change loop
 → approval
 → merge
 → post-merge reconciliation
 → next eligible Work Order
```

including restart recovery and deterministic resumption.

**Human job:** product/architecture authority and exception handler rather than mechanical orchestrator.

## What the human should expect at each transition

The Architect must explicitly announce the current automation stage in its state report and explain the operator's remaining manual duties. The following language is normative:

```text
Stage N active.
You still perform: <manual duties>.
You no longer need to perform: <automated duties>.
The next automation milestone is: <CTRL item>.
```

Do not silently move between stages. The stage must be supported by accepted repository state and the roadmap/work-item completion evidence.

## Exact construction loop

While the Controller is incomplete, every Work Order is executed as follows:

```text
1. Architect reads repository truth.
2. Architect identifies the exact next eligible Work Order.
3. Human operator sends the repository-resolved Work Order to Z.ai.
4. Z.ai verifies base SHA, implements only the owned surface, tests, and opens/updates one PR.
5. Human operator brings the PR state/evidence to the Architect.
6. Architect reviews against frozen architecture, roadmap, Work Order and CI/evidence.
7. If REQUEST_CHANGES, Architect creates a durable review packet.
8. Human operator sends that exact packet to Z.ai.
9. Z.ai updates the same PR and reruns required checks.
10. Repeat steps 5–9 until APPROVE or ESCALATE.
11. Once merge predicates are satisfied, the human performs the currently-authorized merge action.
12. Verify post-merge state and reconcile repository machine state.
13. Architect identifies the next eligible Work Order.
14. Repeat.
```

As Controller capabilities are accepted, replace only the steps that the repository says are automated. Never skip a governance gate merely because a controller feature exists.

## Non-negotiable boundaries

- The human operator is not the product's source of truth; the repository is.
- The Controller is not the architecture authority.
- Z.ai cannot approve or merge its own work.
- An Architect approval is not equivalent to an unconditional merge command.
- A green CI result does not override roadmap or architecture contradiction.
- A Work Order is not complete merely because a PR exists.
- The Controller must fail closed when repository authority and GitHub state disagree.
- The Controller must not import or recreate another product's roadmap or workflow engine.

## Current bootstrap position

CTRL-001 through CTRL-009 are accepted, merged, and reconciled: CTRL-001 (PR #1, merge `0f8e3a749d4dde587c4c81c8b4d250ae2205ff37`), CTRL-002 (PR #4, merge `4dc8387eff1d48039c235727976e1aef33d0bc97`), CTRL-003 (PR #7, merge `7cc340375dcd9768d986b1245303d7006f54fbf1`), CTRL-004 (PR #11, merge `c873b467fc7f4381f7c213723a69071eb9953168`), CTRL-005 (PR #14, merge `3e5ad4bc35186aaec5548cc1e06d6f27b7534a17`), CTRL-006 (PR #17, merge `fbc4e41c0fab05f14fa1d4cb8f989a71d7c05ab5`), CTRL-007 (PR #20, merge `a0392aa0e07772518638f506d755bd9d90d9dc4e`), CTRL-008 (PR #23, merge `e733e37a1ecf7a86c12e3baac0fd325c5806aaa4`; reconciliation PR #24, merge `51b683ee608abc300ddff3a7e32ca0323f8eab5e`), and CTRL-009 (PR #26, merge `3d5e573f121c710386881d8db3ee3476c82176e3`). Repository machine state records all nine in `completed`. The automation stage remains **Stage 1 — State-machine automation**; completion of CTRL-009 does not silently advance the stage.

Stage 1 active.
You still perform: defining/freezing Work Orders, routing implementation/review interactions while later policies remain manual, performing currently-authorized merges, and reconciling post-merge authority until those duties are explicitly automated by later accepted work.
You no longer need to perform: maintaining work-item lifecycle/domain state manually; CTRL-005 supplies the deterministic orchestration boundary, CTRL-006 supplies deterministic CI/evidence classification and retry-request handoff, CTRL-007 supplies deterministic Architect-review observation plus durable review packets and same-worker/same-PR handoff requests, and CTRL-009 supplies deterministic restart/interruption classification and idempotent recovery direction without taking semantic authority or executing worker resumes.
The next automation milestone is: **CTRL-010 — End-to-end dogfood**. CTRL-010 is the next roadmap item but is not yet defined, frozen, or eligible. Stage 1 remains active until an explicit stage transition is supported by accepted repository evidence.
