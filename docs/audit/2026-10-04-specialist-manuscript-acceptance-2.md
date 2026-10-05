# Specialist manuscript acceptance: second authorized attempt

Date: 2026-10-04. Canonical project: `C:\Users\brian\Documents\Paper-Workbench`.

## Outcome

**Live end-to-end acceptance remains incomplete.** The one newly authorized attempt
produced a 930-word expository candidate with eight sections and ten tracked claims.
It stopped after the proof reviewer returned a structurally invalid evidence assertion.
The source and contribution reviewers were interrupted; neither returned a final report.
The candidate has no specialist clearance or human publication approval.

The earlier allocation failure did not recur: this proof review used 17,678 tokens
within its 24,000-token grant. This is one observation, not a performance benchmark.
The first attempt and this attempt retain their original failed/partial states.

## Authorization and isolation

The user explicitly allowed one additional live attempt and asked to batch related
corrections. Limits remained 96,000 tokens, 900 seconds including setup, at most three
simultaneous specialist workers and two manuscript revision cycles. The worker model
was unchanged: `gpt-5.6-sol`, low reasoning, local Codex app-server 0.154.0, through
the existing authenticated subscription profile.

All manuscript/task data used a new synthetic temporary database and artifact store:

`C:\Users\brian\AppData\Local\Temp\paper-workbench-advanced-acceptance-d2b4a20cc8704ed9ae02e0944e80e3f5`

- Task: `31bb13438e2648459ae96d961072269e`
- Manuscript: `a91e800577a54939b40a9e2b18f1930b`
- Started: 09:09:23.118 UTC. Task stopped: 09:11:54.279 UTC.
- Finished saving the evidence: 09:11:57.028 UTC; 153.912 seconds including setup.
- No default database, secret file, original publication manuscript, PoP checkout,
  or frozen pilot artifact was edited. The pilot still has 131 files, newest write
  2026-10-03 17:40:58 local time.
- No commit, push, deployment, additional live attempt or paid API call was made.

## Corrections batched before the attempt

1. Production review packets carry full structured sections once, avoiding a duplicate
   rendered manuscript. Every section has an exact inventory path and checksum.
   Existing evaluation packets keep their original format.
2. Frozen source snapshots now include author, year, venue, DOI and URL. Intake metadata
   is evidence for review, not automatic verification. The fixture's checked metadata
   was set before creating the task; only the two primary excerpts were source inputs.
3. Prompts ask reviewers to collect related actionable corrections in a single pass
   and authors to address all supplied comments in one revision.
4. Final handoff prose is bounded and cannot replace the reviewed candidate.
5. The harness records setup RPC timing, frozen inputs, source checksums and implementation
   hashes. The old primary PDFs/excerpts were copied without modifying them.

The finite-partition case retained the same mathematics and explicitly false historical
claim. It used Ellerman's 2010 primary PDF page 7 (journal page 291) and 2019 arXiv v1
pages 2–3. One actual Crossref query returned three discovery records. The executed
`finite_partitions_v1` receipt passed 2,959 ordered partition pairs over sizes 1–5.
Both search and verification receipts survived database reload this time. These finite
checks do not establish the general theorems.

## Agent calls and timing

Times are UTC. Durations are controller-observed dispatch-to-return/stop intervals.

| Role / operation | Worker PID | Dispatch | Return or stop | Duration | Reported tokens |
| --- | ---: | --- | --- | ---: | ---: |
| Author / draft | 19880 | 09:09:40.183 | 09:10:50.629 | 70.447 s | 13,550 |
| Proof/method / audit | 2424 | 09:10:55.846 | 09:11:51.169 | 55.323 s | 17,678 |
| Source/citation / audit | 28624 | 09:11:00.413 | 09:11:54.248 | 53.835 s | Unavailable |
| Literature/contribution / audit | 8668 | 09:11:04.627 | 09:11:54.263 | 49.636 s | Unavailable |

All four model threads were distinct. The three specialist calls overlapped. There are
30 controller events and four worker-close records; all four PIDs were absent after
shutdown. No author revision or final integration turn occurred.

The preliminary preflight also has five traced calls: initialize, configuration read,
account read, rate-limit read and model listing. Their RPC durations total 3.594 seconds.
This is not total setup or model-execution time. Worker traces retain function names,
file paths, line numbers and model thread/turn identities without request bodies,
credentials or frame locals.

The task ledger contains **31,228 reported tokens plus 48,000 estimated/reserved tokens**
for the two interrupted reviews, totaling **79,228 charged tokens**. Usage is incomplete.
The reported subtotal must not be described as all tokens consumed.

## Defects discovered and repaired offline

### Output schema omitted the exact availability scope rule

The proof reviewer returned `packet_scope: "current packet"`; the validator required
`"current"` or a supplied historical packet hash. The schema had permitted any string.
The schema now exposes and enforces those exact alternatives and SHA-256 forms.

Offline replay of a copy with only that scope spelling normalized exposed a second
defect: one purported exact quotation contained inserted ellipses. The original report
remains invalid and unchanged. Prompts/schema now explicitly require a contiguous
quotation with whitespace-only normalization. The validator still rejects shortened,
paraphrased or wrong-source quotations.

### First invalid report cancelled the rest of the wave

The controller previously raised on the first returned report defect and cancelled
the sibling reviewers. It now gathers independent coverage, passage, receipt and
availability defects together, preserving their field paths and controlled messages.

It finishes the first wave before allowing each affected specialist **one report
correction turn** on the same packet and existing worker. All correction calls use the
original task budget/deadline; they create no additional agents and do not reset the
manuscript revision allowance. Rejected returns, hashes, validation issues and call-span
links remain available. A second invalid return stops with an explicit partial outcome.
Identity/packet-integrity failures and budget/deadline stops remain fail-closed.

This correction behavior has been verified with controlled offline workers, including
exhausted remaining capacity. It has **not** yet been exercised in a new live attempt.

### Author claimed reviews that had not occurred

Section `s7_finite_check` says independent proof, source and contribution reviews had
already reached conclusions. These statements preceded the actual specialist calls and
are unsupported. The draft is preserved with this defect recorded in the offline
diagnostic; it was not silently rewritten into an accepted manuscript.

Author instructions now forbid claiming independent review or publication approval,
and reviewers are explicitly asked to check review-history claims as well as mathematics.
Actual review status remains controller-owned, outside author prose. This is a semantic
review responsibility; prompt changes do not prove all such statements will be caught.

## Verification and exports

- Before the live attempt: **79 focused tests passed**, covering manuscript production,
  worker contracts, research API, desktop workflow and paired evaluation.
- Post-attempt correction batch: **44 tests passed**, including whole-wave collection,
  successful correction and repeated rejection.
- Final manuscript, worker, evidence-binding and publication regression batch:
  **84 passed** in 154.29 seconds (two existing dependency deprecation warnings).
  This includes a correction-budget exhaustion case that dispatches no extra call.
- Ruff and `git diff --check` passed.
- The pre-run evaluation regressions retain paraphrased false absence, quoted corrections,
  different missing reports, historical packet scope, and accepted diagnostic output
  with a bibliography marker still blocked from release.
- Diagnostic export succeeded for Markdown, LaTeX, HTML, DOCX, BibTeX, PDF and JATS.
  Both `ellerman2010` and `ellerman2019` appear in BibTeX with author/year/title/DOI.
- PDF: five pages, WeasyPrint 70, 113 MathJax expressions. First and last pages were
  visually inspected; equations, references and verification-required labels rendered.
  JATS passed the existing 1.3 DTD validator. Diagnostic annotations and duplicate
  narrative/generated reference sections remain; this is not a publication layout.

The full repository suite was not repeated; its earlier results and resolved failures
remain documented in the first acceptance report. All current tests use synthetic stores.

## Evidence and next acceptance

The temporary directory contains `snapshot.json`, `quality-assessment.json`,
`call-trace.json`, `call-timing-summary.json`, `preflight-call-trace.json`,
`implementation-manifest.json`, `post-repair-implementation-manifest.json`,
`frozen-input-manifest.json`, `offline-validation-diagnostic.json`,
`diagnostic-export-receipt.json`, the original/excerpt receipts, draft and exports.
The result ZIP SHA-256 is
`1b74ed52f6d225f3193f30c7fd5c17a87b970d48dedc532f2e1ecb86d386dad0`.

A further live acceptance attempt needs a new explicit allowance: the one authorized
attempt is consumed even though it stopped before the ceiling. Continue in this chat
to reuse the exact failures, constraints and traces. Keep original manuscripts out of
the test until live review/revision/handoff acceptance passes.

The user later authorized one more attempt. Its reviewed manuscript, final handoff
limit and offline repairs are documented in [the third acceptance report](2026-10-04-specialist-manuscript-acceptance-3.md).
