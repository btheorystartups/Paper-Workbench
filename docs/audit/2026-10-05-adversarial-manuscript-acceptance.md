# Four-role manuscript acceptance: partial result and bounded intake fixes

## Authorized attempt and result

The user authorized one fresh attempt at 240,000 tokens and 900 seconds including
setup, using approved host execution and a new temporary output folder, with no
automatic retry. The model workers remained `gpt-5.6-sol` / low on the existing
subscription. Original manuscripts, the default database, the PoP checkout and
the frozen October 3 pilot were not edited. No commit, push or deployment occurred.

**The attempt ended `failed_partial`, not accepted.** It produced one draft and
three accepted specialist reports, but the adversarial report remained invalid
after its one permitted correction. The controller stopped before author revision
or final integration. Agent checks, release eligibility and human publication
approval are false. No second acceptance task was started.

Actual and charged usage were **166,608 tokens**, below 240,000. The host harness
elapsed time was 379.938 seconds. Including initial host-launch setup, elapsed
time was **480.110 seconds**, below 900. Initial staging failed before the harness
started because the host could not read a sandbox-created temporary folder. Inputs
were staged with inherited directory permissions, then copied by the host into
the new run folder. The live deadline retained that initial setup time and was
conservatively earlier than the full authorized deadline.

## Evidence and call order

Run folder:
`C:\Users\brian\AppData\Local\Temp\paper-workbench-adversarial-host-acceptance-ohmid9fv`.

- Task: `4f8fe67638f241aa9c7251efa3ca8a87`.
- Manuscript: `6357b76fc25747588ceac78d402da108`.
- Campaign: `91ab28d938214fa3b9c35807557750c9`.
- Candidate SHA-256: `a4b7fd54299f1af116157ebcfef9c168be02cee61118e816c0b9bfdafa7ccf71`.
- Research ZIP SHA-256: `b2caaa7b87416042c42aaf5ee7f185cca6f05588d6b63ff310849a09ad334efe`.

| Operation | Seconds | Actual tokens | Outcome |
| --- | ---: | ---: | --- |
| Author draft | 64.928 | 13,526 | Admitted, unaccepted AI draft |
| Proof review | 60.315 | 19,505 | Accepted report, scientific blockers |
| Source review | 64.668 | 19,758 | Rejected inventory paths |
| Literature review | 66.696 | 19,872 | Accepted report, scientific blockers |
| Source report correction | 64.383 | 36,321 | Accepted report, scientific blockers |
| Adversarial review | 81.240 | 20,626 | Rejected objection binding and passage sources |
| Adversarial report correction | 62.757 | 37,000 | Rejected objection binding |

The first three reviewers ran concurrently. Corrections retained each original
worker and packet. Adversarial review started after the first wave and source
correction completed. The author and four reviewer identities used five distinct
model threads. All ten recorded wrapper/runtime PIDs were absent after shutdown.
Original report attempts, packet hashes, stack frames, operation/RPC timing,
usage, readiness and the implementation manifest were retained. ZIP integrity
passed and its readiness report correctly denies release and human approval.

## Scientific findings remain unresolved

Reviewers identified a mismatch between inline citations and claim source IDs,
over-attribution of the explicit join/meet naming reversal to a source excerpt
that establishes only an opposite ordering, and an uninventoried implication
that a task-seeded false statement was a documented historical error.

The adversarial reviewer challenged proof boundary cases, source entailment,
novelty limits, scope and reproducibility. It reported proofs and bounded
no-novelty framing as surviving its attempted challenges, while retaining
blocking source, provenance and reproducibility objections. The finite receipt
shows actual controller execution but its packet lacks an independently rerunnable
implementation artifact; the reviewer asked for that artifact or an explicit
limitation. These are scoped reviewer judgments, not publication approval.

## Exact final intake failure

The unresolved `source_entailment` challenge bound objection `O1`. Its `claim_ids`
listed C3, C4 and C9, but O1 targeted only C4. C3 and C9 were discussed as examined
claims rather than unresolved targets. Both returns violated the required binding.
The original diagnostic said only that a blocking objection was required, without
naming the mismatched IDs, so its one correction did not repair this defect.

The source report initially invented pointers to other packet fields rather than
copying paths from the evidence inventory. Its correction repaired those assertions.
The first adversarial return additionally used another frozen source on C4's
negative assessment and on C3's positive assessment. The former is legitimate
counterevidence; the latter cannot establish positive support outside C3's registered
source list. These two uses must remain distinct.

## Local changes after the live attempt

These edits occurred **after** the attempt and do not retroactively validate it:

- Adversarial binding diagnostics now identify the exact check path, criterion,
  linked objection and uncovered claim IDs. Schema and prompt text distinguish
  claims still challenged from all claims examined. Binding remains mandatory.
- Negative (`unresolved` or `contradicted`) assessments may cite exact passages
  from another frozen packet source as counterevidence. Positive support still
  requires the claim's registered sources. Unknown sources and fabricated quotes
  remain rejected; no claim/source inventory or human field is promoted.
- Availability schema and prompt guidance require copying an existing inventory
  path verbatim from the selected current or historical packet scope.

Offline replay against the unchanged original bytes preserves both adversarial
rejections, now explicitly naming C3/C9 at `/adversarial_checks/1/claim_ids`.
The first return's negative C4 counterevidence is accepted, while its out-of-list
positive C3 passage remains invalid. Historical quality/readiness receipts were
not overwritten; replay results are a separate diagnostic artifact.

## Verification and remaining boundary

Manuscript-quality and worker regression tests: **82 passed**, including five new
tests for actionable binding diagnostics and negative frozen counterevidence.
Focused F/I lint passed. The frozen pilot still contains 131 files.
Supplementary worker, desktop evidence-intake, pair and publication regressions:
**63 passed** (ten worker tests overlap the first suite), giving **135 distinct
focused tests passed** after the local changes. Existing FastAPI/Starlette test
client deprecation warnings remain. No additional model call was used for testing.

The workflow correctly failed closed, retained the partial draft and denied release.
Its successful live acceptance remains incomplete: no revised candidate or final
independent clearance was produced. A future attempt needs fresh authorization;
do not automatically repeat it or increase its budget. Before another run, review
the complete frozen brief for source-attribution/provenance/reproducibility scope
and use the improved intake messages. The two format-correction turns consumed
73,321 tokens; any next run's forecast must account for correction overhead and
complete independent re-review before choosing or approving another ceiling.
Continue in this thread because these
findings, prepared case and active implementation are closely related.

## Follow-up review: recommended next scope

The user requested review and advice on how to proceed. No additional live run
or implementation was authorized by that review request. The following is a
concrete proposed offline follow-up, not completed work.

### Budget finding

The existing `_revision_budget` was replayed against the seven recorded final
allocations, assuming the same 166,608 tokens already spent. These are conditional
planner results, not forecasts that a future run will reproduce this usage:

| Ceiling | Re-review reserve | Minimum author grant | Available author grant | Revision admitted |
| --- | ---: | ---: | ---: | --- |
| 240,000 | 140,874 | 40,000 | 0 | No |
| 300,000 | 151,652 | 50,000 | 0 | No |
| 360,000 | 163,652 | 60,000 | 22,740 | No |
| 420,000 | 175,652 | 70,000 | 70,740 | Yes |

Thus fixing the last report binding alone would not have completed this attempt.
The two format-correction turns used 73,321 tokens (44.0% of recorded usage).
They retain the first review's conversation and resend the entire packet. This
adds context to corrections; total recorded usage is not a dollar-cost measurement.
The planner also uses those correction-turn totals to forecast a fresh independent
re-review. Its per-role floor and author minimum scale with the overall ceiling,
so increasing that ceiling increases required reservations as well. Simply
requesting 420,000 tokens is not the recommended remedy or a success guarantee.

### Four bounded implementation items

1. **Make report corrections use fresh, explicit context.** Keep the same logical
   reviewer/worker and one-correction maximum, but give a fresh model thread the
   immutable packet, original rejected report and exact defects. Link old/new
   thread identities and preserve original receipts and scientific objections.
   Reset only per-thread usage tracking; never reset the task ledger or deadline.
2. **Plan a complete cycle from actual inputs and operation type.** Distinguish
   initial review, format repair, author revision and independent re-review.
   Estimate grants from frozen prompt size and observed relevant operations with
   margins, rather than using repair-context totals as ordinary fresh-review cost
   or raising minimum grants solely because the total ceiling rises. Reserve
   repair capacity and final handoff explicitly; never lend future protected
   capacity to a correction. Exhaustion still returns a partial result.
3. **Supply reproducibility evidence.** Bind the reviewed allowlisted verification
   implementation, dependencies, exact invocation and expected deterministic output
   into the evidence packet/package. Reuse `manuscript_verification`; do not clone
   its scientific routine or execute manuscript-supplied scripts. Keep the finite
   execution receipt separate from a general mathematical proof.
4. **Clarify the acceptance brief.** Identify the false assertion as task-supplied,
   preserving its explicit refutation and counterexample without implying a prior
   publication. Require source-specific attribution and splitting of compound
   source claims where necessary. Keep independent reviewers responsible for
   entailment; do not replace them with semantic keyword heuristics.

### Required verification and authorization boundary

Use synthetic storage and controlled workers to verify preserved evidence/identity,
one-correction limits, cumulative charged usage, stale report rejection, accurate
re-review forecasts, reproducible routine output and unchanged release/human gates.
Retain the existing revision ledger, publication binding and four mandatory roles.
Replay the saved rejected reports without promoting their historical status.

After this offline follow-up, prepare a new explicit token/time forecast for one
complete correction and re-review cycle, then seek fresh authorization for exactly
one live acceptance attempt. No paid service, secret/default-database access,
original manuscript edit, commit, push or deployment is included. Continue in this
thread because the active decisions and saved evidence are directly relevant.
The current Sol-Light supervision is suitable for the bounded implementation;
retain `gpt-5.6-sol` / low manuscript workers for comparability unless separately
approved. No claim of dollar savings or account-cache behavior is made.
