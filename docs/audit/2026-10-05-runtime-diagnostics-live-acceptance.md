# Runtime-diagnostics live acceptance

## Authorization and outcome

The user authorized another attempt after the offline diagnosis. This attempt
retained the previously stated **320,000 tokens / 2,400 seconds including setup**,
**gpt-5.6-sol / low**, one scientific revision cycle, four mandatory reviewer roles
and three concurrent review slots. There was one host launch and no automatic retry.

Outcome: **`failed_partial`** at author intake, with stop reason
`author draft still invalid after one bounded correction; evidence retained`.

| Author return | Section-text words | Controller seconds | Actual tokens | Outcome |
| --- | ---: | ---: | ---: | --- |
| Initial draft | 820 | 298.208 | 31,965 | Rejected below 900-word minimum |
| Single configured intake correction | 893 | 321.007 | 39,929 | Rejected; seven words below minimum |

Both returns used the native final JSON schema successfully and had empty response
metadata. Their saved intake issue lists contain only `manuscript_length`. Both
rejected drafts are preserved; neither was applied as an accepted manuscript.
**Accepted drafts: 0. Accepted reports: 0. Specialists dispatched: 0.** No scientific
revision, independent re-review, adversarial report or final model integration ran.
Agent checks, human publication approval, release eligibility and live diagnostic
handoff verification remain false.

## Counter and runtime observations

Each author return records **zero counter requests**, zero receipts and no matching
check. The fresh correction's model provenance records registration of
`check_manuscript_length`, maximum four checks, input-schema SHA-256
`063dd76f97667f02532b6b2183d2638f6145177dcf217824333440531fd92a90`.
Registration plus a successful native JSON return does not establish actual tool
invocation or that the model saw/used the tool as intended. The final-response prompt
clarification did not establish reliable counting on this attempt. Model compliance
and a dynamic-tool/structured-output interaction remain possible explanations;
the saved evidence does not discriminate them.

The deterministic controller count independently agreed with the worker's final
counter calculation for both returns. The gate correctly preserved the inclusive
900–1,200 range. There was no tolerance adjustment, automatic padding or extra call.
The fresh-correction time-admission guard was exercised: it admitted the configured
correction with 400.543 seconds required against 1,555.366 research seconds remaining.
That receipt does not establish capacity for an unobserved reviewer/revision cycle.

The new activity telemetry persisted for both model turns with separate allocation,
thread and turn bindings. Streaming lasted 296.264 and 319.581 seconds; first text
arrived after 109.799 and 118.117 seconds. Local heartbeat counts were 59 and 63,
with maximum gaps of **5.016398** and **5.015393 seconds**. No long local heartbeat
gap or runtime error was recorded. There were zero reasoning deltas; that does not
establish absence of reasoning or computation. A scoped Windows System read found
no Kernel-Power 506/507 events during the setup/run interval.

Thus this observed failure is an author length-contract failure. It supplies no
evidence of token/time exhaustion or a repeat of the prior standby interruption.
Structured runtime-error categories remain controlled-test verified; this attempt
had no error with which to exercise them live. Reviewer progress diagnostics and
the full scientific cycle were not exercised because author admission failed.

## Limits, evidence and cleanup

The conservative setup clock began at **2026-10-05T16:07:24Z**, including a 180-second
reserve for initial inspection. The outer deadline was **16:47:24Z**. Host launch
was recorded at **16:12:31.1602252Z**. Saved completion reported **950.264297 seconds**
including the conservative reserve, within the 2,400-second ceiling. That figure
overstates the unmeasured initial inspection if it used less than the reserved time.

**Actual and charged usage both equal 71,894 tokens.** Both allocations have terminal
actual telemetry, and their sum matches the ledger. No missing review usage was
estimated because no reviewer was launched. The first allowance was 106,666 tokens;
the correction used its remaining 74,701-token allowance. No confirmed controller
charge exceeded the ceiling.

Fresh synthetic output only:
`C:\Users\brian\AppData\Local\Temp\paper-workbench-runtime-diagnostics-acceptance-7291e6a36fe841f08585f0cee4800c5a`.

Saved artifacts include launch/approval receipts, frozen inputs and implementation
hashes, snapshot, rejected drafts and issues, quality/readiness, call stacks/timing,
counter/activity summaries, package, preservation verification and process cleanup.

- Task: `a73138e8c2b146e68d3d94d9d5626b05`.
- Manuscript: `1739acc0c8b8475d9738f8a78137b769`.
- Initial draft SHA-256: `c49db725a5056e4594ac410c11db845107d642f6f5ec4b8572a78ba17c209a69`.
- Correction SHA-256: `911b0a1189bbbf23143931315eca2ab9cead1b26946d3b2f3a9030df6e34537e`.
- Package SHA-256: `1c0864f1a76b2f88a5d2296c64097f9cef50c089fbc89ab0b5ed66ea042f198d`.
- Launcher PID **46944** and worker/runtime PIDs **16164**, **40816** confirmed absent.
- Implementation hashes, both frozen primary PDFs and all **131 pilot hashes** unchanged.
- Prior acceptance package hash unchanged.

No application code changed during the live phase; the prior **235 distinct offline
tests** remain its verification baseline. Tests were not repeated solely to repeat
that evidence. Existing dirty work was preserved. Only new synthetic storage and
this local report were written. No default database, secret file or original
manuscript was accessed; normal existing authenticated worker use was covered by
the live authorization. No commit, push or deployment occurred.

## Recommended next phase

Prioritize a bounded offline investigation of why no counter request occurs with
the advertised dynamic tool and native final schema. Use the pinned runtime's
protocol/schema and controlled fixtures to review capability exposure, request
routing and finalization; then prepare a concrete author-contract change if the
evidence supports one. Avoid relaxing the scientific/length gates or adding padding.
Do not recommend another token/time increase: this failure used only 71,894 tokens
and completed well before the deadline.

Continue in this chat because the active patch and latest receipts are needed;
**gpt-6.1-sol / medium** is sufficient for that offline phase. Any additional live
counter probe or acceptance run needs new explicit authorization, including limits.
This attempt's authorization is consumed. No further live run has been started.
