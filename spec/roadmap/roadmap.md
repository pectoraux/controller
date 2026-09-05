# Controller Roadmap — Authoritative

This file is the human-readable implementation roadmap. Changes to sequencing, scope, dependencies or acceptance criteria require an explicit architecture/work-order change before implementation.

The repository is the sole source of truth. The bootstrap and automation-stage operating process is defined in `spec/operations/controller-build-process.md`; that document governs how responsibility moves from the human operator to the Controller as roadmap work is accepted.

## Product direction

The Controller is evolving from a proven governed orchestration core into a browser-operated control surface for real AI software delivery. The MVP intentionally operates the controlled repository through GitHub and operates provider websites through a browser extension; it does not require a local product checkout, VS Code integration, or a separate desktop agent.

The primary MVP user journey is:

```text
Connect GitHub
    ↓
Select controlled repository
    ↓
Register Worker (Z.ai) and Architect (ChatGPT)
    ↓
Controller discovers READY Work Item
    ↓
Start Work
    ↓
Browser worker adapter operates chat.z.ai
    ↓
GitHub observes branch / PR / CI
    ↓
Browser Architect adapter operates chatgpt.com
    ↓
Architect APPROVE or REQUEST_CHANGES
    ↓
Controller enforces merge predicate
    ↓
GitHub merge
    ↓
Repository reconciliation
```

## Existing governance foundation

CTRL-001 through CTRL-011 established the repository-authoritative state model, GitHub and Z.ai boundaries, orchestration, CI/evidence gate, Architect review loop, merge/reconciliation, recovery/idempotency, end-to-end dogfood, and production Controller runtime. These capabilities are accepted and remain the governance foundation.

## Roadmap graph

```text
CTRL-001 Foundation & repository authority
        |
        v
CTRL-002 Domain/state model
        |
        +--------------------+
        |                    |
        v                    v
CTRL-003 GitHub adapter   CTRL-004 Z.ai provider boundary
        |                    |
        +---------+----------+
                  v
           CTRL-005 Orchestrator
                  |
                  v
           CTRL-006 CI/evidence gate
                  |
                  v
           CTRL-007 Architect review loop
                  |
                  v
           CTRL-008 Merge + reconciliation
                  |
                  v
           CTRL-009 Recovery/idempotency
                  |
                  v
           CTRL-010 End-to-end dogfood
                  |
                  v
           CTRL-011 Production Controller Runtime
                  |
                  v
           CTRL-012 Browser Control Surface Foundation ✓ COMPLETE
                  |
                  v
           CTRL-013 GitHub Browser-App Integration ✓ COMPLETE
                  |
                  v
           CTRL-014 Z.ai Browser Worker Adapter
                  |
                  v
           CTRL-015 ChatGPT Browser Architect Adapter
                  |
                  v
           CTRL-016 Browser Runtime Composition & Lifecycle UI
                  |
                  v
           CTRL-017 smallapp Live End-to-End Dogfood
                  |
                  v
           CTRL-018 Provider Reliability & Recovery Hardening
                  |
                  v
           CTRL-019 Security, Permissions & Packaging Hardening
                  |
                  v
           CTRL-020 MVP Release
```

## Automation-stage mapping

Stage 0 through Stage 7 remain as previously accepted; Stage 7 is the active governance stage. The browser-provider roadmap below is an execution-surface extension of Stage 7, not a redefinition of its lifecycle, merge, review, or evidence semantics.

```text
Stage 7 — End-to-end autonomous governed loop
        |
        +-- CTRL-012..016 build the browser-operated control surface
        +-- CTRL-017 proves it on pectoraux/smallapp
        +-- CTRL-018 hardens provider reliability/recovery
        +-- CTRL-019 hardens permissions/security/packaging
        +-- CTRL-020 packages the MVP release
```

## Sequencing and authorization rule

Only the active Work Item identified by authoritative machine state is executable. Later roadmap items are planned sequencing, not active authorization. A later item becomes executable only after the preceding item is complete/reconciled and an explicit Architect-governed activation changes repository authority and creates/updates that Work Order.

`CTRL-013` is complete and reconciled. `CTRL-014` is the next planned item but is **not activated or executable**. No Work Item after CTRL-013 is independently authorized.

## Work Item definitions

### CTRL-012 — Browser Control Surface Foundation

Build the browser-extension shell and provider abstraction without yet depending on provider-specific automation details. Establish extension lifecycle, Controller integration boundary, provider registry for Workers/Architects, browser-tab discovery primitives, and an operator panel capable of connecting a controlled repository and displaying repository-derived lifecycle state.

Dependency: CTRL-011 complete.

Exit condition: extension loads in a supported Chromium-based browser; provider registrations are durable only as non-authoritative local configuration; Controller authority remains repository-derived; extension can identify a selected controlled repository and render its authoritative Work Item/state.

Status: **COMPLETE / RECONCILED.** Implemented in PR #38 and merged at `951584850609a5804b27348f0e540a80306be7d8` from approved head `0edc3a2c933384a5f52ec3de33cf4794eabac0f7`.

### CTRL-013 — GitHub Browser-App Integration

Integrate GitHub authentication and repository selection into the extension using supported GitHub authorization mechanisms. Establish the repository observation/mutation boundary needed by the existing Controller runtime without moving authority into extension storage.

Dependency: CTRL-012 complete and reconciled.

Status: **COMPLETE / RECONCILED.** Implemented in PR #41 and merged at `cbb40d00c4971d4b8cb9af78d8eb3c4dd179ab99` from approved head `03ce1155673cff69e5ab06401d346ec4aafa9320` (dispatched from base `894b443a8c587d5176659bad4135b319a76bc6fe`).

Exit condition: user can connect GitHub, select `pectoraux/smallapp`, read authoritative state, and invoke Controller-observable GitHub operations with no PAT pasted into the extension UI.

### CTRL-014 — Z.ai Browser Worker Adapter

Implement the first production browser Worker adapter for `chat.z.ai` using supported browser extension mechanisms and live provider UI observations. Human authentication is out of band.

New-session contract:

1. find/open authenticated `chat.z.ai`;
2. select `Agent`;
3. select `GLM-5.3` / model `5.3`;
4. enter the exact Controller-generated governed prompt;
5. send;
6. confirm actual prompt submission rather than trusting the click.

Submission recovery contract:

- a known submission-blocking popup may be dismissed with `Enter`;
- after dismissal, repeat from step 1 so `Agent` and `GLM-5.3` are re-established and the exact prompt is re-entered;
- retries are bounded and configurable;
- unknown dialogs, authentication interruptions or ambiguous UI states fail closed.

Hung-worker recovery contract:

- detect the configured no-progress/hung condition;
- press the provider `Stop` control;
- verify generation stopped;
- send the fixed message `continue`;
- verify the recovery message was accepted;
- otherwise fail closed after bounded attempts.

Dependency: CTRL-013 complete and reconciled.

Status: **PLANNED / NOT ACTIVATED.**

Exit condition: a real browser session can receive an APP-001 handoff, confirm prompt submission, expose worker progress/terminal states, and recover a deliberately hung session without changing repository authority.

### CTRL-015 — ChatGPT Browser Architect Adapter

Implement the Architect browser adapter for `chatgpt.com` using supported browser-extension interaction and live UI observations. Authentication is human-managed. The adapter must deliver Controller-generated review packets, observe the resulting Architect response, and normalize only explicit `APPROVE`, `REQUEST_CHANGES`, or an exception/unknown outcome. No response is never approval.

Dependency: CTRL-014 complete and reconciled.

Status: **PLANNED / NOT ACTIVATED.**

Exit condition: a real review packet can be delivered to the selected Architect conversation and the adapter can distinguish explicit approval/change findings from unknown or blocked states without guessing.

### CTRL-016 — Browser Runtime Composition & Lifecycle UI

Compose the extension, GitHub integration, Z.ai Worker adapter, ChatGPT Architect adapter, and existing Controller runtime into the complete operator flow. Add READY detection, Start Work, worker/review status, retry/recovery telemetry, and fail-closed operator presentation. No new lifecycle or merge predicates are permitted.

Dependency: CTRL-015 complete and reconciled.

Status: **PLANNED / NOT ACTIVATED.**

Exit condition: from the extension, a user can connect services, select a repository, see a READY Work Item, start it, observe the resulting Controller lifecycle, and receive clear governance-hold/error states.

### CTRL-017 — pectoraux/smallapp Live End-to-End Dogfood

Run the complete browser-operated governed loop against `pectoraux/smallapp` and `APP-001`. Prove the exact Z.ai first-prompt sequence, bounded submission retry, hang recovery via Stop + `continue`, GitHub PR/CI observation, ChatGPT Architect review, REQUEST_CHANGES continuation where applicable, exact-head merge gating, and deterministic reconciliation.

Dependency: CTRL-016 complete and reconciled.

Status: **PLANNED / NOT ACTIVATED.**

Exit condition: APP-001 reaches COMPLETE from READY using the browser MVP with auditable evidence and no manual mechanical orchestration beyond human authentication and semantic Architect authority.

### CTRL-018 — Provider Reliability & Recovery Hardening

Harden provider adapters against expected transient UI failures, provider latency, tab loss, navigation drift and bounded retry/restart conditions. Add deterministic provider state observations, diagnostics, explicit unknown-state escalation, and regression fixtures based on captured/synthetic provider UI states that do not require real credentials.

Dependency: CTRL-017 complete and reconciled.

Status: **PLANNED / NOT ACTIVATED.**

Exit condition: repeated controlled failure probes are deterministic, bounded and fail closed; recovery never silently crosses Worker/Work Item/session identity.

### CTRL-019 — Security, Permissions & Packaging Hardening

Minimize extension permissions, isolate provider credentials/authentication from Controller data, harden content-script/message boundaries, redact telemetry, review browser-origin trust boundaries, document supported browsers/providers, and create reproducible extension packaging/signing instructions.

Dependency: CTRL-018 complete and reconciled.

Status: **PLANNED / NOT ACTIVATED.**

Exit condition: security/permission audit passes and the extension package can be installed reproducibly with a documented upgrade path.

### CTRL-020 — MVP Release

Package the browser extension plus Controller runtime as the first usable Pectoraux MVP. Publish operator documentation, installation/configuration procedure, supported provider matrix, known limitations, and a recovery playbook. The MVP remains GitHub-backed and browser-provider-driven; no local checkout or VS Code integration is required.

Dependency: CTRL-019 complete and reconciled.

Status: **PLANNED / NOT ACTIVATED.**

Exit condition: a fresh user/session can install, connect GitHub, register Z.ai and ChatGPT, select a repository, start a READY Work Item, supervise/operate the provider browsers through the extension, and reach a reconciled completion without relying on conversation history.

## Post-MVP direction

The following capabilities are strategic direction, not current authorization:

```text
MVP  →  multiple Worker/Architect providers
     →  richer GitHub App/webhook integration
     →  team/project/work-item dashboards
     →  hosted control-plane option
     →  provider API adapters where supported
     →  stronger audit/search/history surfaces
     →  controlled parallel Work Items where explicitly safe
```

Each post-MVP capability requires its own architecture/work-order activation. None is implied by CTRL-020 completion.

## Human/operator progression

The human remains product/architecture authority and exception handler. For the browser MVP, the human additionally performs one-time provider authentication in the provider UI and retains semantic Architect authority. Routine mechanical provider interaction—opening/focusing sessions, selecting the intended model/tab, sending governed prompts, bounded retry, hang recovery, and carrying review packets—is progressively automated by CTRL-014 through CTRL-016.

## Completion definition

The current Stage-7 governance definition remains satisfied by CTRL-009 recovery/idempotency and CTRL-010 end-to-end dogfood in the Controller itself. The new roadmap reaches MVP completion when CTRL-012 through CTRL-020 have been reviewed, merged, reconciled and CTRL-017 has proven the browser-operated loop on `pectoraux/smallapp` / `APP-001`.

## Explicit exclusions

- Do not import WorkflowOS's roadmap or implementation.
- Do not rebuild WorkflowOS's workflow engine or authoring system.
- Do not make browser extension state authoritative over repository state.
- Do not put provider passwords or raw authentication credentials in extension storage or Work Orders.
- Do not bypass CAPTCHAs, anti-bot controls, provider security mechanisms, rate limits, or other protective measures.
- Do not use undocumented private provider APIs merely to avoid supported browser interaction.
- Do not automate merge on insufficient evidence or unresolved architectural contradiction.
- Do not silently change lifecycle, merge, review, or evidence predicates while implementing the browser MVP.
- Do not introduce an authoritative Controller database.
- Do not require a local product-repository checkout for the MVP.
