# Host standby diagnosis and bounded runtime diagnostics

## Scope and finding

The user authorized diagnosis and improvements after the single 320,000-token /
2,400-second acceptance attempt. This phase used offline tests and read-only saved
synthetic evidence. No new live attempt or model inference ran.

Task: `8ce0dd24a1954fa7b406027ab4e7d626`. Prior evidence remains in
`C:\Users\brian\AppData\Local\Temp\paper-workbench-length-tool-acceptance-433bd962c4d747e5b92548f818babd7c`.

Windows System events provide a concrete explanation for much of the apparent
reviewer stall:

| UTC | Kernel-Power event | Observation |
| --- | --- | --- |
| 2026-10-05T14:24:29.7273640Z | 506 | Entering connected standby; reason: Lid |
| 2026-10-05T14:39:10.1458658Z | 507 | Exiting connected standby; reason: Lid |
| 2026-10-05T14:40:00.3190755Z | 506 | Entering connected standby; reason: Idle Timeout |

The lid-related standby interval was **880.4185018 seconds** (14 minutes, 40 seconds).
It overlaps almost the entire reviewer streaming interval. The author previously
produced 60 local heartbeats over 301.267 streaming seconds; the reviewers produced
only 7, 6 and 5 over 899.605, 895.110 and 890.383 seconds. All three recorded an error
notification at approximately 14:39:21.822Z, shortly after resume. The task stopped
at 14:39:22.555298Z, before the 2,400-second ceiling.

**Inference:** host suspension strongly contributed to this interruption. It is not
evidence that the workflow needed more tokens or that the manuscript model failed
to reason. The precise provider error subtype remains unrecoverable: that version
discarded the raw runtime error and did not save its structured category. Standby
does not prove a particular HTTP status or exclude an accompanying service fault.

Correction to the prior live report: source and literature did have an `error: 1`
notification in saved progress. Only the proof worker's sanitized failure envelope
was retained before the controller cancelled its siblings. Absence of their own
persisted failure envelope was not absence of a runtime error notification. The
prior report and package were preserved; this note supplies the correction.

Evidence: [power events](2026-10-05-host-standby-events.json),
[saved prior progress](2026-10-05-runtime-diagnostics-prior-progress.json), and
[prior live report](2026-10-05-length-tool-live-acceptance.md).

## Implemented improvements

- Added one shared diagnostic normalizer and strict intake models. Runtime errors
  retain only a known category, valid HTTP status and boolean retry flag when
  available. Unknown categories become `unknown`; messages, additional details,
  arbitrary category names and reasoning text are not retained.
- Added optional per-turn activity snapshots alongside existing stream measurements:
  active-turn notification counts/timing, reasoning delta counts/character totals,
  reasoning-item state, item/usage/tool events and local heartbeat counts/gaps.
  Controller intake binds them to the allocation, thread and turn, rejects invalid
  or regressing values, and bounds retained history. Legacy workers remain supported.
- Added task-view error details, a 30-second heartbeat-gap observation and a
  two-minute observable-progress warning. These are diagnostic flags. A quiet
  stream or open reasoning item does not establish whether computation continues.
  Local heartbeats are not evidence of provider progress.
- Added a live-run instruction to keep the host awake. No power settings were
  changed; the application does not prevent standby or extend the original deadline.
- Clarified that the JSON requirement applies to the **final response**. Bounded
  author turns save the counter descriptor's name, maximum checks and input-schema
  hash with registration provenance, making the advertised counter auditable.

The pinned 0.154.0 experimental app-server schema was generated locally in isolated
temporary storage without authentication or inference. Its structured errors,
reasoning notifications and dynamic-tool contracts informed the allowlist. The
official [App Server documentation](https://learn.chatgpt.com/docs/app-server)
describes those protocol features; the installed schema determines the versioned
field shapes used here.

The prior author's 960-word final output remains admitted, with zero counter
requests. Prompt wording may have discouraged an intermediate tool call; that is
a hypothesis, not a proven cause. The clarification and descriptor receipt do not
prove future invocation. Missing counter invocation alone does not reject a valid
in-range manuscript. Live counter use remains unverified.

## Verification

All storage and worker responses in tests were synthetic. Controlled subprocesses
simulate reviewer errors and a long heartbeat gap without a provider call or a
900-second wait.

- **214 passed:** diagnostic helpers, Codex worker, local transport, research
  transport and task API tests. A subsequent focused rerun of the final helper and
  worker edits also passed **156** tests.
- **21 passed:** focused manuscript tests covering runtime failure/package
  persistence, cancellation, adversarial gating, revision/correction capacity and
  structured length behavior. Combined with the boundary/API suite, **235 distinct
  tests passed**. The new package test verifies error provenance, allocation charging,
  no correction/revision retry, no private error text, and release/agent-check blockers.
- JavaScript syntax and diagnostic rendering checks passed, including escaping,
  legacy empty provenance, warning visibility and no-retry wording.
- Ruff passed for the new diagnostic module. The touched Python set passed with
  `E501` excluded; full Ruff still reports long lines across the accumulated dirty
  patch. Those unrelated formatting changes were not made. Existing FastAPI/
  Starlette deprecation warnings remain.

The synthetic HTTP 503/disconnection in tests is **not** a recovered error from the
historical live attempt. An initial test incorrectly assumed every sibling lacked
terminal usage; controlled siblings can complete first. Its assertion now checks
the failed proof allocation's full reservation and the exact summed ledger charge.

Accepted diagnostic output remains separate from release eligibility. Existing
scientific, adversarial, bibliography and human approval gates were not relaxed.
Unknown terminal usage remains fully charged. Even `willRetry: true` stops this
workflow; it is diagnostic metadata, not authorization for another attempt.

## Preservation and remaining work

All **131 frozen pilot hashes** still match the saved baseline. The prior research
package hash is unchanged. Prior acceptance artifacts were read without modification.
No original manuscript outside the frozen verification inputs, default database or
secret file was accessed. The accumulated dirty checkout was preserved. No commit,
push or deployment occurred.

[Preservation check](2026-10-05-runtime-diagnostics-preservation.json) records the
hash comparison. Application edits are limited to worker diagnostics, controller
intake, the task view, focused fixtures/tests and production documentation.

The full live scientific cycle still requires verification. Recommend one newly
authorized attempt on a host kept awake, retaining the same manuscript model and
comparison parameters before increasing budgets or changing models. Its token/time
ceiling and single-attempt/no-retry boundary must be explicit. This phase did not
consume a new live authorization.

Continue in this chat for that acceptance check because its evidence, active patch
and scope decisions are shared. Retain **gpt-5.6-sol / low** for manuscript execution
to isolate the host interruption and diagnostics changes; no model upgrade is
justified by the current failure evidence. **gpt-6.1-sol / medium** remains sufficient
for closely related code diagnosis if new evidence requires it.
