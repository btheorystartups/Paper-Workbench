# One live acceptance attempt with structured length bounds

## Result

**Acceptance failed safely before specialist dispatch.** The length gate rejected
an 811-word first draft. The sole permitted correction reached 1,045 words, within
the required inclusive 900–1,200 range, but invented a reviewer-response identifier
`manuscript_length`. No specialist comments existed; the expected response inventory
was empty. The existing exact response-inventory check rejected that return.

The user confirmed one new attempt at **240,000 tokens / 900 seconds including
setup**, with no automatic retry. No second attempt was launched.

| Check | Result |
| --- | --- |
| Workflow state | failed_partial |
| Actual / charged tokens | 45,212 / 45,212 of 240,000 |
| Setup-inclusive launcher elapsed time | 154.674 seconds of 900 |
| Model / effort | gpt-5.6-sol / low |
| Author returns / bounded corrections | 2 / 1 |
| Accepted candidates / specialist reports | 0 / 0 |
| Specialist agents dispatched | 0 |
| Agent checks / final handoff | incomplete / not verified |
| Human publication approval / release eligibility | false / false |
| Code / frozen primary PDF hash changes during run | none / none |
| Frozen October 3 pilot | 131 files; no hash changes |
| Recorded worker and launcher PIDs still running | none |

The launcher used a new temporary synthetic database and artifact store. It reused
the prior frozen public source excerpts and PDFs with checksum verification. No
original manuscript, default database or credential file was inspected or edited.
No commit, push, deployment or upload was performed.

## Calls and retained evidence

| Operation | Tokens | Controller-observed seconds | Rejection |
| --- | ---: | ---: | --- |
| draft | 15,781 | 60.949 | manuscript_length: 811 words |
| draft_correction | 29,431 | 72.342 | responses: invented comment ID |

Both calls belong to the same logical author and retained author model context.
Each has a distinct span and terminal actual-usage receipt. The correction reused
the remaining original author allowance and original deadline. Allocation receipts
sum to the charged total. Both raw returns and their hashes were retained; neither
was saved as an accepted candidate. Function-level call stacks, RPC timing, model
thread/turn identities and worker PIDs remain in the private diagnostic output.

The failure therefore establishes the live length gate, bounded author correction,
response-inventory enforcement and rejection-before-review behavior. It does **not**
live-verify version 2 reviewer bindings, reviewer repair reservations, deferred
re-review, ambiguous-report release blocking or final integration. Those paths retain
the prior 168 focused offline-test results; this failed attempt is not substituted
for their missing live evidence.

## Deterministic diagnosis

A zero-model-call replay reproduced exactly the original two issue codes. A copy
of the 1,045-word return with `responses=[]` passed structural draft validation.
This copy was never promoted or sent for review. Original artifacts were not changed.
Structural validation does not establish scientific adequacy or publication approval.

The correction prompt asks for required comment responses but does not explicitly
distinguish controller validation issue codes from independent reviewer comment IDs.
The author treated the length issue code as a comment identifier. The response gate
is correct; weakening it or accepting this return would conceal the protocol error.

## Reviewable next correction

A bounded offline follow-up should:

1. Include a controller-derived `expected_response_ids` list in the shared author
   payload. Derive it only from supplied prior reviewer comments, and use the same
   payload for revision forecasts and actual calls.
2. Explicitly require `responses=[]` when that list is empty. State that
   `draft_corrections` codes and paths are validation diagnostics, not comment IDs;
   fixing them does not create a reviewer response.
3. Include expected, missing and unexpected response IDs in validation diagnostics.
   Keep exact binding, the existing single correction and the original budget/deadline.
4. Regress the observed length-correction case and a real reviewer revision. Verify
   that valid reviewer responses remain required and invented responses still fail
   before graph mutation. Then review the concrete patch before another live attempt.

No production code was changed during this verification phase. A future live
attempt requires a new explicit token/time authorization after the offline correction;
the unused balance of this attempt is not authorization for a retry.

## Output

Temporary folder:
`C:\Users\brian\AppData\Local\Temp\paper-workbench-length-acceptance-49d2c0ed236740a48fb55da5fbc41284`

Key files: `snapshot.json`, `quality-assessment.json`, `readiness-report.json`,
`post-run-verification.json`, `worker-cleanup-verification.json`, `offline-replay.json`,
`call-trace.json`, `call-timing-summary.json`, `rejected-draft-0.md`,
`rejected-draft-1.md`, and `research-package.zip`. The Markdown previews are clearly
labeled rejected diagnostic drafts and are not publication candidates.

- Task: `4998cf928425408199c9e92349407438`
- Manuscript: `055b7a7c97dc4af8a8658599330d9b3e`
- First return SHA-256:
  `92af261bb7fb88a90ad7b46856586f83b8d437e15ccbc04bba283035f07decbf`
- Corrected return SHA-256:
  `c55c55aae113d8c210dbf323e783005a04473ec87b93c8ee9ad9178390c39dab`
- Package SHA-256:
  `dcb8fd4c30a0e93dbe79901b2a23e6b3828fade232f3036a9d55f61a5798d5f4`

Continue the small offline correction in this chat because the exact retained case
and current patch are directly relevant. gpt-6.1-sol / low is a reasonable choice
for that scoped change; no fresh thread or broader model review is needed first.
