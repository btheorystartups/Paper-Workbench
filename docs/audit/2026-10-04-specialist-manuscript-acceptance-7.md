# Specialist manuscript acceptance: seventh authorized attempt

Date: 2026-10-04. Canonical checkout: `C:\Users\brian\Documents\Paper-Workbench`.

## Outcome and authorization

The request to fix the failures and attempt again authorized one new live task
under the approved 180,000-token / 900-second ceiling, including setup. It used
the existing authenticated subscription profile, `gpt-5.6-sol` / low, and a fresh
synthetic database and artifact store. An initial automatic approval-review
timeout started no process; the tool permitted one retry, which launched this
single attempt. No budget increase or additional live task followed.

The task ended **limit_reached_partial**, with two admitted drafts, one author
revision and six structurally accepted specialist reports. All 15 first-round
comments received author responses and were independently marked resolved in
the second round. The second round raised new review-history and bibliography
inventory objections. Accepted diagnostic output is not release eligibility:
`agent_checks_complete` and `live_handoff_verified` are both false. No final
model integration ran and no publication approval was established.

Usage was **170,863 actual and charged tokens**, with complete usage telemetry,
and **386.473 seconds including setup**. The remaining 9,137 tokens could not
cover a second revision plus the protected 54,000-token specialist re-review
allowance. The controller stopped without starting an unreviewable revision.
Token enforcement remains best effort for in-flight live model calls.

## Preserved evidence and timing

Synthetic run folder:
`C:\Users\brian\AppData\Local\Temp\paper-workbench-advanced-acceptance-f9ef3ba6b68447649e77dfd58fe9378f`.

- Task: `fa95845403d8427894d1f893cd7e71c4`.
- Manuscript: `d2ccfd3158b846c180d892abe534a425`.
- Campaign: `231a2155354a48f69291db33b7f23459`.
- Final candidate SHA-256:
  `596cb6716070ea95d2eb1d88cb30a39d964428f472738117ed511cfb0ff1df87`.
- Research package SHA-256:
  `dfeec71e90dc475ac0478245c3c76eb7d2b9948518fcca52c7914af3de2c6939`.
- Evidence saved at 11:53:16.715 UTC / 18:53:16.715 Bangkok.

Times below are controller-observed UTC on October 4, not server-side queue times.

| Call | Start | End | Seconds | Actual tokens |
| --- | --- | --- | ---: | ---: |
| Author draft | 11:47:19.188 | 11:48:42.425 | 83.236 | 13,570 |
| Proof review 1 | 11:48:47.514 | 11:49:48.538 | 61.024 | 18,028 |
| Source review 1 | 11:48:51.786 | 11:50:16.835 | 85.049 | 19,331 |
| Literature review 1 | 11:48:55.716 | 11:50:15.920 | 80.204 | 19,002 |
| Author revision | 11:50:18.124 | 11:51:44.177 | 86.054 | 31,215 |
| Proof review 2 | 11:51:50.510 | 11:52:41.539 | 51.029 | 21,755 |
| Source review 2 | 11:51:54.782 | 11:52:36.646 | 41.864 | 23,977 |
| Literature review 2 | 11:51:59.182 | 11:53:10.337 | 71.154 | 23,985 |

Both specialist waves overlapped, with three specialists per wave. The author
retained one model thread; all six specialist model threads were distinct from
the author and each other. The saved trace has 51 controller events, operation
spans, call stacks, thread/turn identities and worker RPC timings. All fourteen
recorded wrapper/worker PIDs were absent after shutdown. No author intake or
report correction retry was needed in this attempt.

Diagnostic exports succeeded for Markdown, TeX, HTML, DOCX, BibTeX, PDF and JATS.
PDF used WeasyPrint 70.0 and MathJax 3.2.2 SVG for 119 math expressions. JATS
passed the existing JATS 1.3 archiving DTD check. The export manifest retained
58 audit findings; export success does not clear these or certify scientific
quality. The export receipt is `diagnostic-export-receipt.json` in the run folder.

## Findings and offline corrections

The first reviews caught mixed source attribution in c2/c9, missing individual
partition counts in c8's inventory, and incomplete inventory of the author's
process report. The revision fixed these and all three specialist roles resolved
their original comments: proof 2, source 7, literature 6.

However, expanded c11 now said no independent specialist review had occurred,
although the first specialist wave had already happened. The author prompt
instructed it not to claim independent review had occurred, while the reviewer
prompt demanded accurate review history. The draft operation also received a
contract requesting research/reviewer reports without an explicit instruction
that those were separate final-integration outputs. This contributed to an
unnecessary process-report section and a changing-status assertion in the paper.

The worker instructions now keep draft/revise output limited to manuscript
content, preserve scientific scope and limitations, and omit both positive and
negative workflow-status claims from sections, claim inventories and limitations.
Existing mixed claims retain their stable IDs with an explicit retraction and
supported scientific replacement. Quoted historical corrections are assessed as
corrections rather than repeated current assertions.

Two reviewers also described earlier comments as reviews of the exact current
candidate. The supplied prior-comment records exposed the author's response
candidate hash but omitted the original review candidate hash. `_prior` now
includes `reviewed_candidate_sha256` from the existing immutable revision-review
round. Instructions distinguish that original candidate from
`response.candidate_hash`. This reuses the existing ledger and does not alter
saved comments, response binding, dispositions or scientific hashes. A synthetic
regression checks different original/revised hashes, role filtering and that an
author response alone leaves the objection open.

The literature reviewer additionally demanded scientific claim IDs for ordinary
reference metadata. The frozen manifests contain the cited venues, dates,
pagination, DOIs and versions. Instructions now check that metadata directly
against the manifest during References section coverage. Scientific claims about
what a source establishes still need claim IDs and exact passage support.
Conflicting or unsupported metadata, unresolved bibliography placeholders and
unverified attributions remain blockers. No saved objection was cleared by this
prompt clarification, and frozen metadata is not itself human verification.

These follow-up changes occurred after the live run. They have no live acceptance
evidence yet. Earlier author-intake fixes were present during this attempt; its
draft passed on the first return, so the correction branch was not exercised live.

## Offline verification

After the follow-up edits, all **111 focused tests passed**: manuscript quality
(52), worker boundary (7), desktop evaluation (14), paired evaluation (22), and
publication packages (16). The manuscript-quality suite ran after the historical
candidate field was added. The other four suites exercise the prompt boundary
and unchanged evidence/publication gates. Existing regressions for paraphrased
false absence, quoted corrections, different missing reports, historical packet
scope and bibliography markers remain passing. Two existing Starlette dependency
deprecation warnings appeared in the four-suite run. Ruff on the three modified
Python files and `git diff --check` passed. The broader pre-attempt suite had
already passed 125 tests, including manuscript paths; it was not repeated in full.

## Remaining boundary

A further explicitly authorized live attempt at the approved ceiling is required
to exercise the updated prompts and historical-candidate context, followed by
successful specialist review and final parent handoff. Do not launch another
task by treating this partial outcome as unused authorization. Retain the worker
model for comparison; continue in this thread because the evidence and current
uncommitted changes remain directly relevant.

The protected desktop pilot still contains 131 files, with newest write at
2026-10-03 17:40:58 local time. Original manuscripts, the PoP checkout, default
database and earlier acceptance artifacts were not edited. No commit, push or
deployment occurred.
