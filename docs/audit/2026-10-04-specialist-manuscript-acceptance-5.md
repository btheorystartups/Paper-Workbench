# Specialist manuscript acceptance: fifth authorized attempt

Date: 2026-10-04. Canonical project: `C:\Users\brian\Documents\Paper-Workbench`.

## Outcome

The user conditionally requested the last known live acceptance check in this
task. The proposed 180,000-token launch was rejected by automatic approval
review because it exceeded the previously approved 96,000-token ceiling. **No
model call started under the rejected cap.** The one new attempt then ran at
96,000 tokens and 900 seconds, including setup, in a fresh synthetic store:

`C:\Users\brian\AppData\Local\Temp\paper-workbench-advanced-acceptance-6fb326e355a1493a838e9277cd7dd218`

This attempt produced a ten-section, twelve-claim expository draft and three
independent accepted specialist reports. Proof/method and literature/contribution
had no blockers. Source/citation identified **missing passage support for C1 and
C2**. The draft linked each claim to both frozen Ellerman sources, while the
reviewer supplied exact passages from the 2019 source only. The report's prose
asserts that 2010 independently supports the claims, but no 2010 passage is
bound to either assessment. The deterministic per-source requirement therefore
correctly blocked both claims. A review round preserves the findings.

The task ended `limit_reached_partial`, campaign `needs_revision`, and
`agent_checks_complete: false`. It used 69,035 observed tokens, with complete
usage telemetry and no overrun. The remaining 26,965 tokens were below the
28,800-token minimum reserve for a second three-specialist wave, so the
controller sent no author revision or final integration call. The manuscript
has no verified parent handoff and is **not release eligible**. This attempt
again did not exercise the compact final-handoff path.

## Identity, timing, and evidence

- Task `0022f094d163490394b9b496302c2395`; manuscript
  `3e1103e86e6b4ec8907018ed1ab367be`; campaign
  `e9128aa81f504384b0bc2affe558bb75`.
- Existing authenticated subscription profile: `gpt-5.6-sol`, low reasoning;
  no paid API service or credential contents were used.
- Started 10:17:54.346 UTC and saved 10:20:40.978 UTC; 166.633 seconds including
  setup. The same original PDFs passed source-receipt checksum verification.
- One capped Crossref metadata search and the bounded `finite_partitions_v1`
  receipt were recorded. The finite receipt supports only carriers 1–5.

Controller-observed UTC calls:

| Agent / operation | PID | Dispatch | Return | Duration | Tokens |
| --- | ---: | --- | --- | ---: | ---: |
| Author / draft | 44232 | 10:18:07.652 | 10:19:25.600 | 77.948 s | 14,102 |
| Proof and method / audit | 41544 | 10:19:29.306 | 10:20:35.459 | 66.153 s | 18,389 |
| Source and citation / audit | 38052 | 10:19:33.141 | 10:20:30.553 | 57.413 s | 18,171 |
| Literature and contribution / audit | 39864 | 10:19:36.813 | 10:20:36.051 | 59.238 s | 18,373 |

The three specialists overlapped, used distinct model threads, and returned
complete structurally valid reports. The trace has 30 controller events with
span IDs, call-stack frames, dispatches, returns, and worker-close records. All
four PIDs were absent after shutdown. The snapshot, report bodies, preflight
RPC trace, source receipts, and package remain in the temporary folder.

Diagnostic export succeeded in Markdown, LaTeX, HTML, DOCX, BibTeX, PDF, and
JATS; JATS passed the installed 1.3 DTD validator. PDF rendering used
WeasyPrint 70 and MathJax 3.2.2 for 138 expressions. The research-package
SHA-256 is
`6328f14d508f014dfaa825b8620bd2a3d9237e3ae21a9bdcf741b840d1ada111`.
Successful export is diagnostic only and does not clear review objections.

The frozen pilot remained at 131 files, newest write 2026-10-03 17:40:58
local time. No original publication manuscript, PoP checkout, default
database, protected pilot artifact, or earlier acceptance task was edited.
No commit, push, deployment, or additional live attempt occurred.

## Handoff for continued work

This run narrows the remaining first-wave defect. Inspect C1/C2 in the saved
candidate and source reviewer report: each lists two `source_ids` but only one
`passages` source. Decide whether the 2010 excerpt supports each *whole* claim;
if it does, the reviewer must bind a checked exact 2010 quotation. Otherwise,
the author should cite only 2019 or split the claim. Keep deterministic
per-source validation and the unresolved review round intact. Update the
author/reviewer prompts and focused offline tests as warranted. Reuse the
existing revision-review and publication evidence binding rather than adding
a parallel mechanism. No further live task is authorized by this attempt;
automatic approval review rejected the higher cap, so any materially larger
allowance needs explicit user approval.
