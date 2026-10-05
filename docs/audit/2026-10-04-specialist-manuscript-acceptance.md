# Specialist manuscript production: implementation and bounded acceptance

Date: 2026-10-04. Project: `C:\Users\brian\Documents\Paper-Workbench`.

This records the first attempt. The newly authorized follow-up and subsequent repairs
are recorded in [the second acceptance report](2026-10-04-specialist-manuscript-acceptance-2.md).

## Outcome

The manuscript-production path and its independent review, revision, release checks,
and call tracing are implemented. Controlled process tests complete the full sequence.
The single authorized live attempt produced a complete **unreviewed expository draft**,
but stopped during the first specialist wave. **Live end-to-end acceptance has not
passed.** No specialist clearance or human publication approval is claimed.

The attempt exposed allocation, receipt persistence, and evidence-binding defects.
These were repaired and checked offline. The saved original task and its stopped
status were retained; no new live task was launched to reset the budget.

## Implemented behavior

- `task_type=manuscript` uses the existing research task, processes and allocation
  ledger. The author drafts/revises; three fresh specialists review the complete
  candidate. At most two revision cycles share the original deadline and token budget.
- Stable section/claim IDs, exact candidate/packet/source versions, whole-document
  coverage, source quotations, actual execution receipts and reviewer identities are
  checked structurally. Semantic entailment, proof adequacy and contribution judgments
  remain explicit specialist assessments, not keyword-based truth decisions.
- Candidate source references enter the existing excerpt/claim evidence graph as
  **asserted, verification-required** links. They never become verified entailments or
  human-accepted prose automatically. Specialist passage locators remain in the reports.
- Objections, responses, independent verification and staleness use `revision_review.py`.
  Scientific hashes exclude the review events themselves; publication evidence includes
  the full review history. The manuscript path and publication audits use one assessment.
- Diagnostic drafts remain exportable. Missing/stale coverage, altered receipts,
  unresolved objections and bibliography markers block clearance and release.
- Evidence availability assertions and corrected historical claims share the existing
  evaluation validation through `evidence_availability.py`. The fourteen-stage desktop
  experiment remains separate from the three-child production default.
- The UI exposes the production mode, optional bounded public searches, review limits,
  worker counts, assessment and downloadable trace. Controller operation traces include
  UTC/elapsed timestamps, role, parent, process/thread/turn identity and call stacks.
  Worker RPC traces exclude request/response bodies, frame locals and exception messages.

## Live case and evidence

Temporary evidence directory:

`C:\Users\brian\AppData\Local\Temp\paper-workbench-advanced-run-e1f1addfac564625b479e06d74972357`

- Task: `ec80483619634fc28cf94113294252af`
- Project: `edc060a9e429400c8efd0bee8174340f`
- Manuscript: `ac6d7da971624b12bc4691790aab9779`
- Model: `gpt-5.6-sol`, low reasoning, pinned local Codex app-server 0.154.0.
- Existing authenticated subscription profile; no paid API key or new service.
- Entire attempt watchdog: 900 seconds including setup; the task received the remaining
  time minus a cancellation margin. Token ceiling: 96,000, best-effort stopping.
- Initial automatic approval review rejected an outer 935-second watchdog. It was
  corrected to include setup within 900 seconds before any model launch. One launch then
  encountered a Windows temporary-directory access error before executing the script;
  the same prepared input was copied into an inherited-access temporary directory.
- One account preflight preceded the task trace. Its successful result was logged; its
  individual timings were not saved. Four subsequent model workers are fully identified
  in the task trace. There was no second live manuscript attempt.

Inputs were a synthetic partition/function-algebra specification and bounded primary
excerpts: Ellerman's 2010 paper, original PDF page 7 (journal page 291), and the 2019
arXiv version, PDF pages 2–3. The original PDFs, selected-page locators and checksums
are retained in the temporary directory. No complete-paper access was inferred from
these excerpts. See the [2010 author-hosted paper](https://ellerman.org/Davids-Stuff/Maths/Logic-of-Partitions-Reprint.pdf)
and [2019 version record](https://arxiv.org/abs/1906.04539v1).

One Crossref query, `Ellerman logic partitions Boolean operations`, completed with a
three-result cap. Its real receipt distinguishes metadata/abstract access from the
supplied primary passages. This was not a comprehensive novelty search. Crossref's
[public API documentation](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
was checked before this bounded read.

The allowlisted routine actually checked all partitions for carrier sizes 1–5:
1, 2, 5, 15 and 52 partitions, totaling **2,959 ordered partition pairs**. It checked
refinement versus function-space inclusion, cardinality, intersection/common coarsening,
and the seeded counterexample. The execution artifact is retained despite the campaign
receipt persistence defect described below. Finite checks are not a general proof.

## Who was called, when, and what happened

Times below are UTC on October 4. Durations are controller-observed call intervals,
not server queue or reasoning time. All four model threads were distinct. The three
specialists overlapped; their starts were staggered by worker setup/account checks.

| Role | PID | Dispatch | Return/stop | Duration | Reported tokens | Result |
| --- | ---: | --- | --- | ---: | ---: | --- |
| Coordinating author | 32492 | 08:15:30.561 | 08:16:54.741 | 84.18 s | 13,494 | Complete draft returned |
| Proof/method | 43364 | 08:16:59.637 | 08:18:13.257 | 73.62 s | 19,555 | Exceeded 16,000-token phase grant |
| Source/citation | 1836 | 08:17:04.460 | 08:18:13.280 | 68.82 s | Not received | Stopped with the task |
| Literature/contribution | 40508 | 08:17:09.307 | 08:18:13.295 | 63.99 s | Not received | Stopped with the task |

The task stopped at 08:18:13.312. It retained **33,049 reported tokens plus 32,000
estimated tokens** for the two interrupted reviews: 65,049 charged to the ledger.
Usage was incomplete; 33,049 is not a measurement of all consumed model tokens.
Best-effort in-flight usage can exceed an individual grant before telemetry arrives.

There are 30 controller events, four observed model-turn starts and four worker-close
receipts. All four recorded worker PIDs were absent after shutdown. The parent was not
called for final integration after the specialist stop.

The operation chain is `run_task → manuscript_quality_runner.execute → _author /
_audit_wave → Runner.send → AgentProcess.send`, followed in each worker by
`CodexResearchWorker.run → request → StdioCodexClient.request`. The trace records the
actual function filenames/line numbers. RPC receipts cover initialization, config and
account reads, rate-limit read, model listing, thread creation and turn start. Individual
turn-start acknowledgements took approximately 0.009–0.076 seconds; this does not
measure the subsequent model execution time.

Inspect `call-trace.json`, `call-timing-summary.json`, `snapshot.json` (per-agent RPC
provenance), `quality-assessment.json`, `primary-source-receipts.json`, and
`research-package.zip` in the temporary directory. The result ZIP SHA-256 is
`c0dc4b9c3d0d945bbe19d3c6ad4c95ac44287ed19f217a32fe5a4e5b8f9077ba`.

## Defects found and repaired

1. **Specialist grant too small.** The fixed one-sixth grant rejected the proof review
   despite available task capacity. Specialist grants now use up to one-quarter each,
   bounded by one-third of the remaining task capacity. Required review takes priority
   over optional later revisions/synthesis. The global ledger and ceiling are unchanged.
2. **Receipt omitted from persisted campaign.** A shared mutable JSON list prevented an
   ORM update from recording the executed finite check, even though its content-addressed
   artifact existed and the author received it. Receipt collections now use independent
   copies. A database-reload regression covers search and verification receipts together.
   Historical task evidence was not silently rewritten to appear successful.
3. **Candidate labels mistaken for database IDs.** The full publication basis followed
   local `c1`–`c10` labels as database claim keys, blocking diagnostic export. It now
   resolves candidate-local labels through the manuscript's explicit map, only within
   that manuscript's campaign/task/agent records. Ordinary graph identities are unchanged.
4. **Diagnostic preservation.** Every dispatched specialist packet is now saved before
   the call. Early cancellation avoids creating an agent; terminal tracing includes
   failed spawns and stopped calls. Existing compute receipts must still have current
   approved inputs; stale plans cannot count as passed evidence.

The source bindings added for future candidates do not retrofit the preserved live
draft. Its human-readable References section is present, but its BibTeX file is empty
because the earlier candidate had no excerpt/claim citation links. This is a diagnostic
limitation, not a complete bibliographic export or an approved release.

## Verification

- Full repository run: **683 passed, 1 skipped, 2 failed** in 1,477 seconds. One failure
  was the console-script test invocation omitting the root `app.py` from the import
  path; it passed with the repository root on `PYTHONPATH` / module invocation. The
  other was a removed worker-module `AgentReport` export; compatibility was restored.
  Both failed cases passed their explicit rerun.
- After the repairs, the focused manuscript, evidence-binding, publication, worker and
  research-API suite passed **77 tests**. Three additional final regressions passed,
  followed by four receipt/contract tests including current versus stale compute inputs.
  A further controlled-process regression successfully returned three 19,555-token
  specialist reports inside the unchanged 96,000-token task ceiling.
  Counts overlap; they must not be added into a single invented full-suite total.
- The complete run included **14 desktop-workflow and 22 paired-workflow tests**, all
  passing. These retain the false-absence paraphrase, quoted correction, different
  missing artifact, historical packet scope and accepted-output/bibliography blockers.
- Controlled real-process tests exercise the complete revision and re-review cycle,
  three simultaneous children, distinct reviewer identities, full packet preservation,
  release/path agreement, cancellation, stale content, source changes, fabricated
  receipts, quotation errors and missing coverage. Offline fixtures never count as
  live manuscript evidence.
- Ruff, JavaScript syntax validation and `git diff --check` passed.
- The saved diagnostic draft exported Markdown, LaTeX, HTML, DOCX, BibTeX, PDF and JATS.
  PDF: four pages, WeasyPrint 70.0, 100 MathJax expressions; first/last pages visually
  inspected. JATS passed the existing 1.3 DTD validation. The empty BibTeX limitation is
  recorded above. No publication approval was fabricated to make these exports work.

## Boundaries and remaining acceptance

All tests used synthetic temporary databases/artifact stores. No original manuscript,
default database, secret file, frozen desktop artifact or PoP checkout was edited.
The protected pilot still contains 131 files. No commit, push or deployment occurred
in this implementation phase.

One new bounded live acceptance attempt is still required to verify the repaired
allocation and receipt paths with completed specialist reports. The approved plan
authorized one attempt; further model execution requires a new explicit allowance.
Continue in the same chat because the remaining work directly uses this trace and
these fixes. Original publication manuscripts should wait until that acceptance passes
and a specific manuscript/question and research budget are selected.
