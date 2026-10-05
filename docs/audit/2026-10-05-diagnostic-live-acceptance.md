# Live acceptance with sanitized stream diagnostics

## Outcome

The user authorized one attempt at 240,000 tokens / 900 seconds including setup,
using gpt-5.6-sol / low with no automatic retry. It ended
`limit_reached_partial`, with no admitted candidate or specialist dispatch.
No second run was launched.

The first draft contained 796 section-text words and no response entries. Intake
correctly rejected it against explicit 900–1,200 bounds. The author then used its
single correction turn in the retained author context. That turn streamed until
the existing research deadline stopped it; no complete correction return exists.

| Operation | Controller-observed seconds | Recorded actual tokens |
| --- | ---: | ---: |
| First draft, rejected for length | 157.904 | 15,939 |
| Draft correction, stopped by time limit | 632.500 | unknown |

Setup-inclusive launcher elapsed time was **802.647 seconds**, below 900. The
research phase ends before the launch deadline to preserve shutdown/handoff time.
The controller enforced that existing reservation; it did not extend the attempt.

Recorded actual usage was 15,939, which is incomplete. Charged usage remained
**80,000 tokens**, retaining the unfinished correction's full allowance. The
charge is conservative budget accounting, not a measured final model usage total.
No scientific clearance, handoff, human publication approval or release eligibility
was established.

## Diagnostic evidence

During correction, notification and heartbeat counters advanced. Final saved
telemetry reports 15,849 notifications and 157 worker heartbeats at `turn_stream`.
There is no recorded worker failure code or class. The terminal controller reason
is explicitly `time limit reached; further research stopped`.

This attempt therefore did not reproduce the preceding proof worker's generic
stream exception. The new fixed exception codes were not exercised live. It also
did not reach independent review. The evidence establishes a slow/incomplete author
correction, but does not distinguish lengthy output generation from service latency
or prove that a stronger model or higher reasoning effort would help. Notification
counts are not output-token or output-character measurements.

## Verification and preservation

Post-run verification confirmed unchanged implementation hashes, frozen primary PDF
hashes and all 131 October 3 pilot file hashes. All recorded worker PIDs (19568,
20616) and launcher PID 22024 were absent after shutdown. The retained first return
and validation issue are present; no incomplete correction was promoted as a draft.
Recorded allocation usage sums match the ledger, and unfinished usage remains charged.

No original manuscript, default database, credential file, commit, push, upload or
deployment was involved. Live progress probes read only sanitized fields from this
attempt's explicitly authorized temporary synthetic database.

## Output

Folder:
`C:\Users\brian\AppData\Local\Temp\paper-workbench-diagnostic-acceptance-5cf6c1d3b63f4678a5dfa92514476929`

See `snapshot.json`, `quality-assessment.json`, `post-run-verification.json`,
`worker-cleanup-verification.json`, `call-trace.json`, `call-timing-summary.json`,
`readiness-report.json` and `research-package.zip`.

- Task: `3399cba9e2c84063943686b1948feeee`
- Manuscript: `47b4305bff234f81b571719e37d5f565`
- Rejected first return:
  `82a4c47b4d314b573548bed61be4f853fc31f262a9e0555475c92c039211e988`
- Package:
  `8f092770bd2ef6344b4307966f857449c949c8d883841dea9d2b4560ca892ff8`

## Next recommendation

Before another live attempt, examine the author correction's repeated input and
stream-volume instrumentation offline. Compare a bounded fresh correction payload
containing the original draft and exact defects with retained author context, while
preserving source/task binding, one correction, the review ledger and release gates.
Determine whether additional non-content counters or a scoped output bound would
distinguish excessive generation from latency. Do not assume either cause or weaken
the required length merely to obtain a pass.

Keep this follow-up in the current chat because the exact case and shared patch
are directly relevant. gpt-6.1-sol / medium is a reasonable choice for the offline
assessment. A stronger live worker may be worth testing after that preparation,
subject to availability in the dedicated worker profile and new explicit model,
token/time and one-attempt authorization. No further live work is currently authorized.
