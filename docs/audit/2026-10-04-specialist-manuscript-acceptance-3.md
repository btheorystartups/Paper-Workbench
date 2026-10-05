# Specialist manuscript acceptance: third authorized attempt

Date: 2026-10-04. Canonical project: `C:\Users\brian\Documents\Paper-Workbench`.

## Outcome

The newly authorized live attempt produced an **unreviewed, diagnostic expository
manuscript** and completed all three independent specialist reviews on its frozen
candidate. Each returned a structurally valid report covering all nine sections and
twelve inventoried claims. No blocking objection or report correction was required.
The campaign records `agent_checks_complete`.

The **task remains `limit_reached_partial`**. An optional final parent integration
turn used 27,699 observed tokens against 27,535 remaining and did not return its
summary. `live_handoff_verified` is false; no human publication approval is claimed.
Under the current release assessment, the completed agent checks remain visible,
while the unfinished task is an explicit publication blocker.

The manuscript is a bounded exposition of finite-partition Boolean-function
spaces, with proofs of refinement/reversed inclusion, a separating-function
converse, counting and intersection formulas, and an explicit counterexample to
the seeded historical false claim. It makes no novelty or performance claim.
The supplied primary evidence covers selected pages only, and one capped search
cannot establish comprehensive literature coverage.

## Isolation and allowance

One fresh task used a new synthetic temporary database and artifact store:

`C:\Users\brian\AppData\Local\Temp\paper-workbench-advanced-acceptance-6505546c53dd4b409b672fd77b195ae5`

- Task: `1d8d71fe68d74379b22c5c4ffc4ba820`.
- Project: `8544cb1ad797416d980845b5bb09ccb2`.
- Manuscript: `a97af41e3d624f34959f281e42abc684`.
- One task ceiling: 96,000 tokens, best-effort telemetry; 900 seconds including setup;
  three simultaneous specialists; at most two manuscript revision cycles.
- Model: `gpt-5.6-sol`, low reasoning, existing authenticated local Codex app-server
  subscription profile. No paid API service or credential contents were used.
- The attempt began at 09:31:45.787 UTC and finished saving evidence at
  09:34:48.428 UTC, 182.642 seconds including setup.
- The frozen pilot still has 131 files, newest modification 2026-10-03 17:40:58
  local time. No original publication manuscript, PoP checkout, default database,
  frozen pilot artifact, or prior acceptance task was edited. No commit, push or
  deployment occurred in this phase.

The same two checked Ellerman excerpts supplied bounded primary evidence:
2010 original PDF page 7 (journal page 291), SHA-256
`f69c4e7cb839f0c751fdac56a12901a0973104ff68a8df34e30392fbb43e5016`;
and 2019 arXiv v1 PDF pages 2–3, SHA-256
`e16efb0d97d19e072412fcc28e97c6af50095da6cf8a4465cf15143b41f71f6f`.
The one Crossref query returned three capped metadata results. The controller's
allowlisted `finite_partitions_v1` routine checked 2,959 ordered partition pairs
for carrier sizes 1–5 and retained its passed-within-scope receipt. Neither source
metadata nor finite checks were treated as general proof.

## Who was called and when

Times are UTC on 2026-10-04. Durations are controller-observed intervals.

| Role / operation | PID | Dispatch | Return or stop | Duration | Observed tokens |
| --- | ---: | --- | --- | ---: | ---: |
| Author / draft | 18560 | 09:31:56.283 | 09:33:03.509 | 67.227 s | 13,405 |
| Proof and method / audit | 34116 | 09:33:07.363 | 09:34:09.212 | 61.849 s | 18,292 |
| Source and citation / audit | 18780 | 09:33:11.590 | 09:34:16.369 | 64.779 s | 18,364 |
| Literature and contribution / audit | 19628 | 09:33:15.798 | 09:34:20.165 | 64.367 s | 18,404 |
| Same author / integrate | 18560 | 09:34:20.819 | 09:34:47.493 | 26.674 s | 27,699; stopped |

There were four distinct model threads; the three specialist calls overlapped.
The three reviewer reports were accepted before the last author call. They found
no fabricated review-history statement, unsupported primary-source attribution,
proof gap or novelty claim within the provided scope. The call trace has 33
controller events, call stacks, worker PID/thread/turn identities and five
preflight RPC timings. The preflight RPC calls total 2.798 seconds, separate from
setup and model execution. All four PIDs were absent after shutdown.

The ledger records **96,164 observed tokens**, 164 above the nominal ceiling.
The executor used best-effort usage notifications and stopped when the final
turn exceeded its allocation. `usage_complete` is false because that turn
returned no final result. The stopped task and its original snapshot were
preserved; no second live task was started to recover the final summary.

## Offline corrections after the attempt

1. The final parent input previously repeated the complete draft, full task
   contract and all three full reviewer reports. The parent already had its draft
   in the persistent thread. The revised handoff sends the candidate hash, IDs,
   title and limitations, plus each report's immutable hash, role, summary,
   per-claim status, objections, resolutions and blockers. Full originals remain
   in the campaign and agent records. On **this exact saved input**, the supplied
   final prompt decreased from 13,113 to 3,056 estimated input tokens (48,681
   to 10,355 UTF-8 payload bytes). This is an offline comparison, not a claim
   that a later live model turn will use a known total. A 1,000-token unused
   allowance margin was also added for best-effort telemetry.
2. Review completion and release eligibility are now separate. If the manuscript
   task has not completed its final handoff, its quality assessment retains
   `agent_checks_complete: true` for the three valid reviewers but adds an
   explicit release blocker. The manuscript path and publication audit follow
   that blocker. A fresh read of this saved partial task returned
   `publication_ready: false` and
   `manuscript-quality-incomplete: manuscript production task has not completed
   its final handoff`. The saved original snapshot is unmodified.
   The same blocker applies if a task reaches `completed` without its recorded
   parent integration and child handoff receipts.
3. Final task synthesis now refreshes its quality status after the task reaches
   its terminal state, so a completed task does not retain an in-progress
   blocker and a partial task does not conceal one.

These corrections have **offline verification only**. The user authorized one
live attempt, which was consumed by the run above.

## Manuscript and export verification

The draft has nine sections, twelve explicit claims and 892 body words. I read
its general proofs, corrected counterexample, search-scope statement and
references. The reports assessed the complete candidate, including the
distinction between finite checks and general proofs. Their consensus is
evidence for human review, not a substitute for human mathematical judgment.

Diagnostic export succeeded in Markdown, LaTeX, HTML, DOCX, BibTeX, PDF and JATS.
The BibTeX contains both checked Ellerman entries with title, author, year and DOI.
The PDF has five pages, WeasyPrint 70, and 106 MathJax expressions; its first and
last pages were visually inspected. JATS passed the installed 1.3 DTD validator.
The draft still has diagnostic support labels and a duplicate generated reference
list, so it is not publication layout.

The post-attempt focused suite passed **79 tests** covering the manuscript workflow,
evidence binding and publication gates, including new partial-task release and
compact-handoff assertions. Ruff and `git diff --check` passed. Previously
verified worker, API, desktop and paired-workflow regressions were not needlessly
rerun. No full repository suite was claimed in this phase.

After adding the missing-handoff receipt gate, the focused manuscript suite passed
**41 tests**, including both partial-state and completed-without-handoff release
cases. This overlaps the 79-test batch and is not an additional distinct-test count.

## Evidence and remaining acceptance

The temporary directory retains `snapshot.json`, `quality-assessment.json`,
`call-trace.json`, `call-timing-summary.json`, `preflight-call-trace.json`,
`acceptance-summary.json`, the original and post-repair implementation manifests,
`post-repair-prompt-comparison.json`, `post-repair-release-assessment.json`,
the source/receipt files, diagnostic manuscript exports, and
`research-package.zip`. The ZIP SHA-256 is
`36cd199c9fc701d3fa9ab02e3e225b754ac8bd1598a49ffb374d9104687e4fb9`.

Full live acceptance now needs one further explicitly authorized bounded attempt
to verify the compact parent integration, terminal task completion and release
blocker behavior together. That later attempt should use the same original
manuscript-free synthetic case and budget unless the user changes the scope.
This chat contains the relevant code, evidence and authorization history;
continuing here avoids rediscovery.
