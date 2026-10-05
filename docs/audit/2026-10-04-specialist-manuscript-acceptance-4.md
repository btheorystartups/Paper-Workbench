# Specialist manuscript acceptance: fourth authorized attempt

Date: 2026-10-04. Canonical project: `C:\Users\brian\Documents\Paper-Workbench`.

## Outcome

The single newly authorized live attempt produced a complete **diagnostic draft**
and three independent, structurally valid specialist reports. The proof and method
review found no blocking issue. Source and citation found two passage-support
gaps; literature and contribution found a compound claim with misleading source
attribution and substantive process assertions absent from the claim inventory.
The controller opened one review round and preserved all five findings.

The task is `limit_reached_partial`, the campaign is `needs_revision`, and
`agent_checks_complete` is false. The remaining 28,540 tokens were below the
28,800-token protected minimum for a subsequent specialist wave, leaving no
reviewable author-revision grant. No revision or final integration call was sent.
The saved manuscript has unresolved objections and no verified parent handoff;
it is **not release eligible**. This result does not establish that the compact
final-handoff repair from the third attempt works live, because that path was not
reached.

## Isolation, scope, and call trace

The task used a fresh synthetic database and artifact store only:

`C:\Users\brian\AppData\Local\Temp\paper-workbench-advanced-acceptance-0599f5b7e8ff4464bf4e882e968c7870`

- Task `23a71e49417646468258554ea2d4c95b`; manuscript
  `f61f27c5178e45f0b391f4a17412cd6d`; campaign
  `2e476e4911184aee9712420986ba82c4`.
- One-task ceiling: 96,000 tokens, best-effort usage telemetry; 900 seconds
  including setup; at most three concurrent specialists and two revision cycles.
  Actual use was **67,460 tokens** with complete usage telemetry and no overrun.
- Existing authenticated subscription profile: `gpt-5.6-sol`, low reasoning.
  No paid API service or credential contents were used.
- Start 09:56:34.186 UTC; evidence saved 09:59:13.929 UTC;
  159.744 seconds including setup.
- The two original Ellerman PDFs were checksum-verified against the existing
  receipts before the call. The 2010 SHA-256 was
  `f69c4e7cb839f0c751fdac56a12901a0973104ff68a8df34e30392fbb43e5016`;
  the 2019 SHA-256 was
  `e16efb0d97d19e072412fcc28e97c6af50095da6cf8a4465cf15143b41f71f6f`.
  The capped Crossref search returned three metadata records. The controller's
  `finite_partitions_v1` receipt checked 2,959 ordered partition pairs over
  carrier sizes 1–5; this is finite corroboration, not a general proof.

Controller-observed UTC intervals:

| Agent / operation | PID | Dispatch | Return | Duration | Tokens |
| --- | ---: | --- | --- | ---: | ---: |
| Author / draft | 24012 | 09:56:50.816 | 09:57:58.466 | 67.650 s | 13,411 |
| Proof and method / audit | 37100 | 09:58:02.147 | 09:58:55.746 | 53.599 s | 17,938 |
| Source and citation / audit | 45016 | 09:58:05.475 | 09:59:05.039 | 59.564 s | 18,038 |
| Literature and contribution / audit | 44140 | 09:58:07.895 | 09:59:09.309 | 61.414 s | 18,073 |

The three reviewer calls overlapped and used distinct model threads, separate
from the author. The trace has 30 controller events with call-stack frames,
agent and parent IDs, span IDs, dispatches, returns, and worker-close events.
All four worker PIDs were absent after shutdown. The preflight RPC trace is
separate from the four manuscript calls. The original task snapshot was retained.

## Manuscript and review findings

The nine-section, eleven-claim expository draft contains the requested general
proofs, finite-check scope, references, and an explicit correction of the seeded
false statement that equally many partition blocks yield identical function
spaces. The proof specialist reported no blockers within the supplied scope.

The source specialist could not provide passages covering all cited source IDs
for `c_definition` and `c_order`. The former bundles the manuscript's own
Boolean-function-space definition with sourced partition definitions. The
literature specialist separately identified that compound attribution and found
substantive search, proof-audit, and review-history assertions in Section 8 with
no distinct assessable claim IDs. These are genuine review blockers. A draft
with these objections cannot be treated as reviewed or publication ready merely
because it exported successfully.

Diagnostic export succeeded in Markdown, LaTeX, HTML, DOCX, BibTeX, PDF, and
JATS. The PDF has six pages, WeasyPrint 70 and 156 MathJax expressions; its
first and last pages were visually inspected. JATS passed the installed 1.3 DTD
validator. The PDF includes diagnostic support labels and a generated reference
list, so this is not publication layout. The package SHA-256 is
`68053fda0cd6d91f2fd6d01b389b562a63e209989e8c68ede81c92ca1340b486`.

## Offline correction and verification after the attempt

The author prompt now requires exact source support for an entire source-linked
claim, separates sourced material from the author's own definitions and
deductions, and sends controller process details to the research report unless
they belong in the manuscript. It also requires separate claim IDs for any
substantive process assertions retained in the manuscript. The controller now
reports the protected re-review reservation and remaining balance when a
revision cannot be dispatched. An offline controlled-process regression
reproduces this 67,411-token first-wave budget pause and confirms no unreviewed
revision call occurs. The focused manuscript suite passed **42 tests**; Ruff and
`git diff --check` passed. These prompt changes have not been live verified.

The prior protected pilot remained at 131 files, newest write
2026-10-03 17:40:58 local time. No original publication manuscript, PoP
checkout, default database, protected pilot artifact, or earlier acceptance
task was edited. No commit, push, deployment, or additional live attempt was made.

The temporary folder retains the original snapshot, accepted specialist
reports, call traces, frozen source receipts, exported formats, and research
package for review. A future live acceptance attempt requires a **new explicit
budget authorization**. The observed first wave alone used about 67,000 tokens;
a full revision and second three-specialist wave would require a materially
larger cap than this attempt. The exact future usage remains uncertain.
