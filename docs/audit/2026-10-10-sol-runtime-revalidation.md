# Sol runtime revalidation — 2026-10-10

## Canonical checkout and scope

The canonical project is `C:\Users\brian\Documents\Paper-Workbench`, at
`5d82170` with the existing uncommitted Sol/runtime changes retained. The counter,
worker, RPC, compatibility and runtime-test sources match the saved live source
commit `f1b27b3` after normalizing Windows line endings. This phase did not replace
the dirty checkout or import the later changes in the acceptance clone.

This follow-up adds an offline math-PDF preflight to
`scripts/research_live_acceptance.py`. It runs before database initialization and
model dispatch, so a missing export runtime is detected before an allowance is
spent. Its focused regression injects the known renderer failure and verifies
that no database or data directory is created. The test isolates environment and
import-path changes. The capability document now describes Sol transport and the
partial live outcome rather than the superseded GPT-5.5-only compatibility status.

## Preserved live evidence

The October 6 attempt is recorded in
`2026-10-06-sol-live-acceptance.md`. Its single-run authorization was consumed:
179,638 reported tokens, two successful counter calls, an exact 934-word final
receipt, four distinct Astra specialist threads, bounded search receipts and
finite verification. Scientific objections and insufficient revision capacity
stopped the controller before revision/handoff. It is not a release acceptance.

The recovered `run/manuscript-live.zip` was rechecked read-only: ZIP CRC passed,
and all 37 manifest entries matched their sizes and SHA-256 hashes. Package hash:

`f309343d4cdfe523cfef16392f3176c3a5fc45d36cbf9b73e7e1872e8b3f9850`

The package remains in
`C:\Users\brian\Documents\Codex\2026-10-06\in-c-users-brian-documents-paper\outputs\sol-acceptance-58dcfea2d064`.
No authenticated inference, external search, pilot rerun, original-manuscript edit, secret access,
default-database access, commit, push or deployment occurred in this phase.
Tests used synthetic temporary storage. The frozen desktop pilot retains 131
files and its latest modification time of October 3 at 17:40:58.

## Offline verification

- 182 focused counter, runtime exposure, worker, manuscript-length and model-policy
  tests passed. The runtime tests use the pinned CLI and a synthetic loopback
  provider; they do not dispatch authenticated inference.
- The new export-preflight regression passed after its final edit.
- The separate desktop evidence-intake and workflow run passed all 28 tests.
- Interpreter checks resolved both `workbench` and the research worker to the
  canonical checkout's `src`, rather than the saved acceptance clone.
- A real synthetic math render returned an 11,358-byte PDF using WeasyPrint with
  one math expression.
- `uv lock --check --offline` passed using the existing portable uv executable
  with a dedicated temporary cache; 98 packages resolved.
- Ruff import/fatal/syntax rules and `git diff --check` passed.
- The full offline suite finished on October 11: 1,024 passed, one skipped and
  two failed in 1,535.41 seconds, with two FastAPI/Starlette deprecation warnings.
  `test_polling_waits_before_retrieve` stopped with an uncertain synthetic
  transport outcome before a create response was journaled; its underlying
  cause was not established. `test_unconfigured_live_executor_and_invalid_limits_fail_closed`
  saw launcher settings leaked by the original version of the new test. That
  process had collected the test before its environment/import-path isolation
  was added. The corrected launcher test, the entire API module and the polling
  regression module then passed together: 13 tests in 45.18 seconds, with the
  same two warnings. The full suite was not rerun after the isolation edit;
  the initial broad run is not recorded as a green result.

## Remaining integration discovered during revalidation

The saved acceptance clone is now at `741e2d7`, with additional uncommitted
manuscript work beyond the live source commit:

`C:\Users\brian\Documents\Codex\2026-10-06\in-c-users-brian-documents-paper\work\paper-workbench-commit`

Its dirty files include budget/usage handling, output checkpoints, continuation,
editorial closure, evidence packaging, math escaping integrity, intentional
literature comparisons and retryable stream handling. The October 7 audit at
`docs/audit/2026-10-07-manuscript-audit-integrity-and-coverage.md` describes part
of this work. These changes have not been reconciled into the canonical checkout;
do not copy the clone wholesale or erase either dirty state.

Related saved tasks confirm that the later manuscript review wave was closed
without accepted specialist reports. A local 5,408-word manuscript correction
was subsequently prepared in
`C:\Users\brian\Documents\Codex\2026-10-08\manuscript-blocker-repair\outputs\candidate-v2`.
That task reports local checks and preserved originals, not specialist approval
or Workbench readiness. Its future review budget is a proposal, not an unused
authorization. This runtime phase did not independently validate that candidate.

### Offline reconciliation handoff

Continue in the canonical checkout. Read this audit, capture both dirty baselines,
and compare the saved clone's changes against `741e2d7`. Reconcile relevant
software improvements in small reviewable groups, preserving the current Sol
transport, exact receipts, restricted workers, shared budget/deadline semantics,
four specialist roles, evidence binding and release blockers. Reuse existing
revision-review and publication evidence mechanisms. Run focused tests with the
canonical virtualenv and an explicit repository import path, then broader checks
when justified. Update capability and workflow documentation to describe what
was actually integrated and verified.

Scope is local reversible software integration and offline synthetic tests. Keep
PoP, frozen pilot artifacts, historical outputs, original manuscripts, secrets
and default databases untouched. No inference, manuscript agents, external
searches, spending, commits, pushes, deployment or destructive cleanup. New live
acceptance needs a concrete target and separate explicit budget authorization.
