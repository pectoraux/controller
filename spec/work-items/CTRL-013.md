# CTRL-013 — GitHub Browser-App Integration

Status: `COMPLETE`

## Authorization

CTRL-013 was the sole executable Work Item after CTRL-012 completion. It was dispatched from exact `main` base `894b443a8c587d5176659bad4135b319a76bc6fe` (the CTRL-013 activation merge) and implemented in PR #41 across two Architect review iterations. Architect approval was recorded against exact reviewed head `03ce1155673cff69e5ab06401d346ec4aafa9320` (comment 5551932732); the PR was merged once, producing merge commit `cbb40d00c4971d4b8cb9af78d8eb3c4dd179ab99`.

Automation stage: `STAGE-7-END-TO-END-AUTONOMOUS-GOVERNED-LOOP`.

## Completion record

CTRL-013's GitHub Browser-App Integration was reviewed and accepted. The implementation established, inside the extension package only: the OAuth device-flow identity (RFC 8628 public-client path; no PAT entry field anywhere; placeholder client-id sentinel failing closed as `AUTHORIZATION_NOT_CONFIGURED`; session-only access token confined to the identity closure — never persisted, messaged or logged; single minimal `public_repo` scope), repository discovery with accessibility-gated selection and canonical `owner/name` identity (including `pectoraux/smallapp`, live-verified), the typed observation surface field-compatible with the accepted Python adapter (`controller/github.py`: repository/default branch, branch head, typed pull requests tolerating GitHub's documented shape variants as observed evidence, reviews, comments, combined commit status) plus branch/PR correlation as typed outcomes, and exactly the three Controller-authorized mutation transports (`CreateBranch` explicit-SHA, `OpenPullRequest` with the one-PR rule and base identity gate, `MergePullRequest`) with in-transport gates and zero predicate duplication.

The review iterations materially shaped the accepted merge boundary: iteration 1 removed the authorization substitute (caller-supplied identity fields plus a live session no longer reach the merge POST), and iteration 2 removed the extension-side governance evaluator entirely (`mergeAuthorization.js` deleted; no active-work-item predicate, no review/approval predicate, no hard-coded Architect identity). `MergePullRequest` at the message surface now fails closed as `RUNTIME_AUTHORIZATION_UNAVAILABLE` with zero network — the runtime-authorization handoff is deliberately not composed until CTRL-016, and no second authorization mechanism was invented. The pure client transport performs only structural validation (mirroring `_as_merge_request`) plus exactly one merge POST carrying the frozen merge method and the exact-head SHA pin, with zero reads — GitHub's own refusals surface as typed `MUTATION_REFUSED`, never re-decided locally.

The implementation deliberately did **not** implement provider-specific Z.ai or ChatGPT DOM automation (CTRL-014/CTRL-015 scope), did not compose the browser runtime (CTRL-016 scope), did not add provider automation, and did not change any lifecycle/merge/review/evidence predicate, any `controller/` module, or any other `spec/` document (audit-proven byte-identical to the dispatched base).

## Evidence

- Implementation PR: #41 (branch `ctrl-013-github-browser-app`, base `894b443a8c587d5176659bad4135b319a76bc6fe`).
- Implementation head: `0fbdaf680c666a17dfc32df3ec93fa5c80267703`; review iteration-1 correction head `099d189`; review iteration-2 correction head `ee654b6` (branch tip `03ce1155673cff69e5ab06401d346ec4aafa9320` including the delivery dashboard records).
- Architect approval: comment 5551932732 (2026-09-05T12:49:51Z) at the exact reviewed head `03ce1155673cff69e5ab06401d346ec4aafa9320` against the unchanged dispatched base; REQUEST_CHANGES iterations at comments 5551517415 and 5551829016.
- Merge commit: `cbb40d00c4971d4b8cb9af78d8eb3c4dd179ab99` (2026-09-05T12:49:56Z).
- Worker-reported extension suite: `node --test 'extension/tests/**/*.test.js'` — 153/153 pass at the reviewed head.
- Worker-reported Python suite: 651 passed + 209 subtests.
- Worker-reported mypy strict: 0 issues in 38 source files.
- Worker-reported ruff check/format: clean.
- Worker-reported `python3 -m controller validate/domain/status --repo .`: exit 0 (CTRL-013 READY, STAGE-7, completed x12 at implementation time).
- Worker-reported `scripts/audit_ctrl_013.sh 894b443a8c587d5176659bad4135b319a76bc6fe`: PASS, 8/8.
- Worker-reported Chromium real-load probe: 17/17 live checks — MV3 service worker registered, popup rendered, placeholder authorization failing closed, mutation gating with zero network, live typed observations of `pectoraux/controller` and `pectoraux/smallapp`, authority projection pinned at `main@894b443`, and the fabricated-identity `MergePullRequest` live refusal proof.

The live GitHub branch contained exactly the CTRL-013 implementation surface plus the established mechanical real-repository test-pin advancement; every `controller/` module and every other `spec/` document was byte-identical to base (audit-proven). The PR was approved on the live head and merged exactly once.

## Reconciliation

Observed implementation merge evidence:

```text
PR: #41
base: main @ 894b443a8c587d5176659bad4135b319a76bc6fe
approved head: 03ce1155673cff69e5ab06401d346ec4aafa9320
merge: cbb40d00c4971d4b8cb9af78d8eb3c4dd179ab99
```

Reconciliation updates this Work Order and machine state to `COMPLETE`, records CTRL-013 in the completed ledger, preserves Stage 7, and activates no successor. CTRL-014 is only planned and requires a separate explicit governance activation after reconciliation.

No runtime implementation semantics are changed by this reconciliation checkpoint.
