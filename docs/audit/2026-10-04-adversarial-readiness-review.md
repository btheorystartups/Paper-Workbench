# Mandatory adversarial review and transparent readiness

## Authorization and scope

The user authorized this local implementation in the canonical Paper-Workbench
checkout. Existing dirty changes and historical runs were preserved. Verification
uses synthetic temporary databases, controlled protocol peers and inert artifacts;
there was no new model/manuscript run, paid service, original manuscript edit,
commit, push or deployment. The October 3 frozen pilot still contains 131 files.

## Implementation

- Policy `manuscript-quality-v2-adversarial` requires four independent review roles.
  Three children can run concurrently; adversarial review follows the initial
  specialist wave. Every revision gets fresh independent reviewers. Deferred
  reviews and final integration retain reservations within the original budget.
- Adversarial reports cover every section and claim, and supply exactly five
  structured challenges: proof stress, source entailment, novelty limits, scope
  overclaims and reproducibility. Unknown claims, duplicate/missing criteria and
  unresolved challenges without a matching blocking objection are rejected.
  Supported cited claims require frozen exact passages; finite checks require
  executed receipts. Objections and independent resolution reuse `revision_review`.
- The controller derives a readiness rubric with review/packet hashes, claim
  assessments, challenges, limitations, blockers and publication audit findings.
  It is available in task snapshots, manuscript paths, task UI and exported JSON.
  It does not assign a submission probability or pretend a bounded check proves
  universal correctness or novelty.
- Diagnostic completion, scoped agent checks, human verification/acceptance and
  release eligibility have distinct fields. The agent assessment now says
  `agent_review_grants_publication_approval=false`; actual human approval appears
  in readiness only for an approved, current, ready publication package.
  Existing publication evidence binding determines freshness. Agent passes never
  set source human verification, claim support or AI-text acceptance. Audit labels
  identify pending human source/support decisions explicitly.
- Missing adversarial review, stale candidates/evidence, unresolved objections,
  incomplete handoff and bibliography placeholders remain blockers. Three-role
  historical successes are preserved but do not satisfy the new policy. The
  fourteen-stage diagnostic experiment remains separate from production.

## Verification

- Manuscript quality, Codex worker and publication packages: **93 passed** before
  the final additional adversarial schema assertion.
- Evaluation boundary, desktop workflow, pair, manuscript path, research task API
  and artifact packaging: **75 passed, 1 skipped**. Windows did not grant creation
  of a symlink; the separate junction denial test passed.
- Regression coverage includes paraphrased false absence as a review flag, quoted
  historical corrections, artifact-specific missing reports, historical packet
  scope and accepted diagnostic output with bibliography markers still blocking
  release. New tests cover adversarial-only objections through revision and fresh
  verification, missing/invalid challenges, exact passage support, unchanged human
  fields, stale reports, actual current package approval and approval staleness.
- Focused F/I lint and JavaScript syntax checks passed. FastAPI/Starlette test
  client deprecation warnings remain; no dependency changes were needed.
- Final worker/schema, artifact-package and readiness regression checks: **20
  passed**, including the new model-facing adversarial schema assertion. Across
  the focused suites, **169 distinct tests passed and 1 skipped**.

## Remaining live evidence

The prior three-role live acceptance remains historical evidence. This four-role
workflow has synthetic verification only. A new bounded live acceptance requires
explicit run/budget authorization; adding a mandatory role does not grant more
tokens or time. Historical usage replay confirms some former budgets now stop
before revision because complete four-role re-review cannot be reserved.
