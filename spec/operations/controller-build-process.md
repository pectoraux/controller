# Controller Build Process — Bootstrap Through Automation

This document is an authoritative operational guide for building the Controller itself. The repository is the only durable source of truth; conversation history is not an implementation dependency.

## Roles

| Role | During bootstrap | After automation |
|---|---|---|
| Human operator | Performs only duties not yet automated; acts as temporary mechanical controller | Product/operator authority and exception handler; no routine message routing |
| Architect | Owns architecture, roadmap, acceptance, semantic review and policy | Same semantic authority; intervenes when judgment/policy is required |
| Z.ai worker | Implements exactly one governed Work Item, tests, opens/updates one PR | Same implementation role, dispatched/resumed by Controller |
| Controller | Capabilities are progressively added by accepted Work Items | Reads repository authority, dispatches/resumes workers, observes GitHub/CI, carries review packets, enforces gates, merges when authorized, reconciles state |
| GitHub/CI | Execution and evidence surface | Same |
| Repository | Sole durable authority | Sole durable authority |

## Automation stages

### Stage 0 — Manual controller / bootstrap

Human performs the full mechanical loop: Architect defines Work Order → human gives it to Z.ai → worker implements/tests/opens PR → human brings state to Architect → Architect reviews → human relays changes if needed → authorized merge → post-merge verification.

### Stage 1 — State-machine automation

The Controller reconstructs repository authority and executes deterministic local lifecycle transitions, but does not yet operate GitHub or Z.ai itself.

### Stage 2 — GitHub observation automation

The Controller observes branches, commits, PRs, CI status, reviews and comments and correlates them to the active Work Item.

Human duty removed: routine PR/CI observation and transcription.

### Stage 3 — Z.ai dispatch/resume automation

The Controller constructs repository-derived worker context and starts/resumes Z.ai against the exact Work Item.

Human duty removed: copying Work Orders/prompts and mechanically deciding same-worker/same-PR resumption.

### Stage 4 — Review/change-loop automation

The Controller carries durable Architect review packets and resumes the worker on `REQUEST_CHANGES` while keeping the same Work Item and PR.

Human duty removed: manually relaying review findings. Semantic Architect review remains an authority function.

### Stage 5 — CI/evidence/retry automation

The Controller watches required checks, classifies retryable failures where policy permits, and routes implementation retries.

Human duty removed: routine CI polling, evidence collection and mechanical retry routing.

### Stage 6 — Merge/reconciliation automation

Only after all merge predicates are satisfied may the Controller perform the authorized merge and reconcile repository machine state.

Human duty removed: mechanical merge clicking and routine post-merge bookkeeping.

Human retains: product/architecture authority, policy changes, contradiction handling and exceptional intervention.

### Stage 7 — End-to-end autonomous governed loop

The Controller safely carries a repository-authorized READY Work Item through dispatch, implementation, PR/CI, Architect review/change iteration, approval, merge, post-merge reconciliation and selection of the next eligible Work Item, including restart recovery and deterministic resumption.

The accepted CTRL-010 dogfood record demonstrates this composed capability, including deliberate lost-state-write recovery, zero second merge mutation, deterministic reconciliation and fail-closed contradiction probes.

Stage 7 remains the active governance stage. CTRL-011 completed the production runtime packaging. CTRL-012 is complete and reconciled as the Browser Control Surface Foundation. CTRL-013 is now the sole active browser-MVP Work Item; CTRL-014 through CTRL-020 remain planned and require separate activation.

## Browser MVP operating model

The MVP is a Chromium browser extension. It does not require a local product checkout, VS Code extension, desktop agent, or hosted web application.

GitHub is the controlled-repository execution/evidence surface. The extension should use supported GitHub authorization/API mechanisms rather than clicking through github.com pages for ordinary repository operations.

Worker and Architect provider UIs are operated through provider-specific browser adapters after human authentication. Provider-specific selectors, interaction sequences, prompt-submission confirmation, hang recovery, and ambiguous-state handling live inside those adapters rather than in the Controller core.

For the MVP Z.ai Worker adapter, the required live interaction is: open/focus `chat.z.ai` → ensure authenticated → select `Agent` → select `GLM-5.3` / model `5.3` → enter the exact governed prompt → send → verify actual submission. If the known submission popup appears, press `Enter` and repeat from Agent/model/prompt/send/verification. All retries are bounded; unknown UI state fails closed.

For a hung Z.ai Worker, the adapter detects the configured no-progress/hung condition, presses the provider `Stop` control, verifies generation stopped, sends the fixed message `continue`, and verifies acceptance. Failure after the bounded recovery policy is a governance hold.

For the MVP ChatGPT Architect adapter, authentication is human-managed and the adapter later delivers Controller-generated review packets to `chatgpt.com`, normalizing only explicit approval/change decisions or an exception/unknown outcome. No response is never approval.

## Normative transition report

At every accepted stage transition the Architect must report:

```text
Stage N active.
You still perform: <manual duties>.
You no longer need to perform: <automated duties>.
The next automation milestone is: <CTRL item or explicit stage-transition condition>.
```

Do not silently move between stages.

## Governed construction loop

The semantic governance order remains:

```text
1. Architect reads repository authority.
2. Identify the exact next eligible Work Item, if one exists.
3. Establish exact base SHA and worker context.
4. Worker implements only the owned surface and opens/updates one PR.
5. Observe PR, CI and evidence.
6. Architect reviews against architecture, roadmap, Work Item and evidence.
7. REQUEST_CHANGES => durable findings and same-worker/same-PR continuation.
8. APPROVE => evaluate the merge predicate independently.
9. Merge only against the exact expected head and only when every predicate is satisfied.
10. Reconcile repository machine state from observed GitHub/repository evidence.
11. Select the next eligible Work Item, if one exists.
```

Approval is not merge authorization by itself. A Work Item is not complete merely because a PR exists.

## Merge/reconciliation safety

The merge predicate requires, at minimum: intended base, exact Work Item identity, one governed PR, exact current head, terminal-success required CI/evidence, no unresolved blocking review/change, Architect approval for that exact head, and active machine state still eligible for merge.

Merge must use the exact expected head and execute at most one mutation attempt. Head drift or any contradiction fails closed. Only observed successful GitHub merge evidence establishes `MERGED`. Reconciliation follows immediately and must be idempotent.

Runtime state must be reconstructible from repository/GitHub evidence. No hidden controller database may become the authoritative source of truth.

## Current operating position

CTRL-001 through CTRL-013 are accepted, merged and reconciled. CTRL-013 — GitHub Browser-App Integration is complete. CTRL-014 — Z.ai Browser Worker Adapter is the next planned item but is **not activated**.

Stage 7 active.
You still perform: product/architecture authority; policy definition/change; semantic Architect review where required; contradiction, safety and exception handling; human authentication at provider sites; and future roadmap/work-order activation.
You no longer need to perform: routine mechanical orchestration already covered by the accepted Controller capabilities, and, after CTRL-014/016, routine supported browser interaction with configured providers.
The next automation milestone is: **CTRL-014 — Z.ai Browser Worker Adapter, pending explicit activation after CTRL-013 reconciliation.**

A fresh session continues by reading, in order: `spec/state/controller-program-state.json`, `spec/roadmap/roadmap.md`, `spec/architecture/controller-architecture.md`, this document, `spec/work-items/<active item>.md`, and `spec/operations/fresh-session-handoff.md`. The exact current `main` SHA must be observed before dispatch. No conversation history is required.
