# Specialist manuscript acceptance: sixth authorized attempt

Date: 2026-10-04. Canonical checkout: `C:\Users\brian\Documents\Paper-Workbench`.

## Outcome and authorization

The user explicitly approved the increase to 180,000 tokens. One new live task
ran with that ceiling, a 900-second deadline including setup, the existing
authenticated subscription profile, `gpt-5.6-sol` / low, and a fresh synthetic
database and artifact store. No budget escalation was blocked in this attempt.

The author returned a ten-section, fourteen-claim draft, but claim `c13` put
the real literature-search receipt `search-1` in `verification_ids`. That field
admits executed verification receipts only; the allowed ID was
`finite_partitions_v1`. Draft intake correctly rejected the reference before
applying the manuscript graph. The controller had no author correction step
at this boundary, so the task ended `failed_partial` with its generic validation
failure reason. No specialist was dispatched, no candidate was admitted, and
no final handoff or release eligibility was established. The raw author output
is retained in the parent's report; it has not received scientific review.

The attempt used **13,807 tokens**, with complete usage telemetry, and
**83.167 seconds including setup**. It did not approach either approved limit.
The larger allowance is therefore not the cause of this stop.

## Preserved evidence

Synthetic run folder:
`C:\Users\brian\AppData\Local\Temp\paper-workbench-advanced-acceptance-27e7e2a22689489c8cd71a208c9a8a03`.

- Task: `8f5af0cb364844ebbe4ddf73e02f6be0`.
- Bangkok time (UTC+7): attempt started 18:12:25.296; author dispatched
  18:12:35.879 and returned 18:13:47.729; evidence saved 18:13:48.462.
- The author call lasted 71.849 seconds. Its wrapper PID was 24152 and worker
  PID 43732; both were absent after shutdown. The trace contains 12 controller
  events, call-stack frames, the model thread/turn identity and RPC timings.
- Original PDFs passed the existing source checksum checks. Search and finite
  verification receipts were retained. The real search receipt was misclassified
  by the author, not fabricated or promoted by the controller.
- Research-package SHA-256:
  `2c6856f437100a02abb1c34fe18aa179c566a7c5900e68e94fed6b7353db8ecc`.

No manuscript exports were generated from this rejected candidate. A read-only
offline replay identified exactly `/claims/12/verification_ids` and confirmed
unchanged hashes for the saved database, snapshot, quality assessment, package
and call trace. Replay output is at
`C:\Users\brian\AppData\Local\Temp\paper-workbench-draft-intake-offline-9f739664355a4124a6081e33cdb9004a\replay-result.json`.

## Offline repair

Author instructions now explicitly distinguish search receipts from executed
verification receipts. Search history belongs in scoped prose and uses an empty
`verification_ids` list unless an actual verification receipt applies.

Draft preflight now collects controlled diagnostics for unknown source or
verification IDs, prohibited novelty, lost revision IDs, and missing author
responses before any graph mutation. The author may correct these controller
intake defects once on the same worker. The correction receives all detected
defects together and must return a complete candidate. Both raw attempts,
hashes, spans and rejection diagnostics are retained.

The correction shares the original author grant and task deadline. It cannot
borrow the protected specialist-review allowance, start a new task or reset the
budget. Repeated invalid output or insufficient allowance ends partial. Only
the dedicated preflight exception is repairable: arbitrary errors during graph
application are not silently retried. Reviewer independence, existing revision
dispositions, evidence binding and release blockers remain in force.

Five new synthetic cases check batching before graph mutation (with and without
an existing candidate), successful same-worker repair, a repeated invalid draft,
and exhaustion of the original author allowance. The focused suite passed
**125 tests** in 206.14 seconds across manuscript quality, the worker boundary,
desktop and paired evaluation workflows, publication packages and manuscript
paths. It retained the historical evidence and bibliography-blocker regressions.
Two existing Starlette dependency deprecation warnings were emitted. Ruff and
`git diff --check` passed. These are offline results, not a successful live run.

## Remaining work

This attempt's original state is preserved. The repair is verified offline only;
it was not present during the live run. No second live attempt was started.
A further explicitly authorized attempt at the already approved 180,000-token /
900-second limits is needed to exercise corrected intake, specialist reviews,
any necessary revision, and final parent handoff together. Retain the worker
model for comparability and continue in this thread because the current
uncommitted repair and evidence are directly relevant.

The frozen pilot still has 131 files and its newest write is 2026-10-03
17:40:58 local time. No original manuscript, PoP checkout, default database,
protected pilot or prior acceptance task was edited. No commit, push or
deployment occurred.
