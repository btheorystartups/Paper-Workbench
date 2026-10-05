# Live acceptance after the author response contract fix

## Result

One user-confirmed attempt ran at 240,000 tokens / 900 seconds including setup,
using gpt-5.6-sol / low, a fresh temporary synthetic store and no automatic retry.
The attempt ended `failed_partial` after 228.950 seconds. No further run started.

The first draft was 849 words and correctly rejected. Its sole bounded correction
was 1,079 words with `responses=[]`, and was admitted. Thus this attempt exercised
the previously failing length-correction and empty-response contract successfully.
Three specialist workers started; no specialist report was accepted. The proof
worker recorded `ValueError` at `turn_stream`, after successful thread and turn
start RPCs. The controller stopped and closed the other workers. Adversarial review
and final integration were not reached. Scientific clearance, human publication
approval and release eligibility remain false.

Recorded actual usage was 45,762 tokens. Charged usage was 156,009, including full
reservations for unfinished specialist calls whose final usage receipts are missing.
Recorded actual usage is therefore not a complete measurement of consumption.
The ledger retained unknown usage rather than releasing that capacity.

## Verification

Deterministic post-run checks recorded one admitted draft, zero accepted reports,
three dispatched specialists, complete author receipts, incomplete reviewer receipts,
matching recorded usage sums, and charged usage below the authorized ceiling.
Implementation and primary PDF hashes were unchanged. All 131 frozen October 3
pilot files retained their baseline hashes. All recorded worker PIDs and launcher
PID 20224 were absent after shutdown. No original manuscript, default database,
credential file, commit, push, upload or deployment was involved.

The generic stream exception is insufficient to distinguish a runtime/model error,
rerouting, unsupported item type, invalid delta, oversized output, authentication
change or unsuccessful turn completion. Retained sanitized progress counters and
RPC metadata establish the boundary, but do not establish the specific cause.
Do not infer that manuscript reasoning, token exhaustion or the new author schema
caused this failure. No proof-review result exists to support such a conclusion.

## Preserved evidence

Folder:
`C:\Users\brian\AppData\Local\Temp\paper-workbench-response-acceptance-efada5e865264d7ba23fa96eaabd4129`

See `snapshot.json`, `quality-assessment.json`, `readiness-report.json`,
`post-run-verification.json`, `worker-cleanup-verification.json`, `call-trace.json`,
`call-timing-summary.json` and `research-package.zip`. The post-run verifier handles
missing actual receipts as unknown; it does not count them as terminal zero usage.

- Task: `4266c7b8b76f47dd860b20927041e715`
- Manuscript: `90fd71aa52134eddaf0c29185b0c84ae`
- Candidate: `9f2a4cd041d7d7b0e95a970e3a1be2f058b69fc7a27a1ba7c914ca41de367223`
- Package: `05f11af8162ffdc655f05227047ffb7153b3eb1b74d9eeed1fd226c976d3f62c`

## Next recommendation

Before another live attempt, add narrowly allowlisted failure reason codes for the
worker stream branches and retain them in controller provenance. Test those branches
offline with controlled events, without storing raw error messages or inspecting
authentication stores. This is an observability gap, not yet evidence for a higher
model or effort setting. Keep the follow-up in this chat; gpt-6.1-sol / low is suitable
for the bounded offline change. A later live attempt needs fresh explicit token/time
authorization and should preserve the same comparison model until evidence justifies
changing it.
