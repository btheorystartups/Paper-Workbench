# Offline author response contract follow-up

## Implementation

The preceding live attempt rejected an 811-word first draft, then a 1,045-word
correction with an invented `manuscript_length` reviewer response. That retained
attempt remains unchanged and was not retried.

The shared author payload now carries `expected_response_ids`, derived solely from
prior reviewer comments. Drafting before independent review supplies an empty list.
The actual author call and revision budget forecast reuse that payload; validation
uses the same inventory. Prompts explicitly distinguish controller validation codes
and paths from reviewer comment IDs.

The live worker's structured output schema now constrains response count to the
inventory size. For nonempty inventories, comment IDs are restricted to the supplied
IDs. Empty inventories require zero response entries, without using an invalid empty
enum. Schema defaults for older callers without the explicit inventory are preserved.
The controller still checks exact coverage and duplicate IDs; schema constraints do
not establish scientific adequacy. This uses supported array bounds and enums from
[official OpenAI documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

Validation diagnostics now name expected, missing and unexpected IDs. Unknown
responses still reject before graph mutation. The one-correction policy, author
context, independent review ledger, publication binding and original budget/deadline
are unchanged. No new retry, model call, default database access or external write
is included in this offline phase.

## Verification

Focused verification covers the controlled 811-to-1,045-word correction with an empty
response inventory; preservation of both returns; acceptance followed by all four
controlled specialist reports; rejection of invented validation-code responses before
graph mutation; real adversarial reviewer responses and independent closure; missing
reviewer response diagnostics; and draft/revision output schemas for empty and nonempty
inventories. Existing bounded author correction and forecast regressions also run.

**25 distinct focused tests passed**, including six new regressions. The three existing
reviewer-revision and missing-response cases were also rerun after strengthening their
assertions. Python F/I lint and Git diff checks passed. No claim of live acceptance
is made for this patch. The previous 168-test suite remains the earlier baseline;
this phase uses targeted checks for the changed surface rather than another paid run.

## Why 180,000 succeeding did not imply 240,000 would always succeed

The configured limit is a shared application spending ceiling across author, reviewers,
corrections, revisions and integration. Individual calls receive allocations from that
ceiling. Increasing it provides capacity; it does not change the workers' reasoning
effort setting, force use of the allowance, or make a malformed return valid. The
application separately reserves later review and handoff capacity. A worker or a
complete revision cycle can lack sufficient allocated capacity while the overall
ceiling has not yet been reached.

The recorded runs also changed requirements and implementation; they are not a
controlled experiment changing only the budget:

| Recorded run | Ceiling | Recorded usage | Outcome and scope |
| --- | ---: | ---: | --- |
| October 4, attempt 6 | 180,000 | 13,807 | Rejected a search receipt in the execution-receipt field |
| October 4, attempt 7 | 180,000 | 170,863 | Insufficient reserved capacity for another revision and review wave |
| October 4, attempt 9 | 180,000 | 171,575 | Literature review exceeded its individual grant; telemetry incomplete |
| October 4, attempt 10 | 180,000 | 177,187 | Three-role workflow passed after one author revision |
| October 5, four-role attempt | 240,000 | 166,608 | Adversarial report still invalid after one correction |
| October 5, after offline follow-up | 240,000 | 109,997 | Four-role workflow passed; 785 words missed the prose-only length request |
| October 5, structured-length attempt | 240,000 | 45,212 | Length correction passed, but invented response ID stopped intake |

Sources are the corresponding saved audit reports in this directory, especially
`2026-10-04-specialist-manuscript-acceptance-10.md`,
`2026-10-05-adversarial-acceptance-after-offline-follow-up.md` and
`2026-10-05-structured-length-live-acceptance.md`. The successful 180,000-token run
predated mandatory adversarial review and deterministic length enforcement. The
successful four-role 240,000-token run demonstrates that 240,000 itself did not prevent
completion, but its length miss also shows why workflow completion was insufficient
as a full acceptance claim.

Some changes repaired genuine controller and prompt weaknesses: per-role reservations,
repair context/accounting and the distinction between validation issues and reviewer
comments. Others made requested requirements explicit and enforced. Neither a successful
single run nor passing synthetic tests establishes reliable completion for arbitrary
manuscripts. These records do not isolate a budget effect or measure a success rate.

## Next boundary

Review this bounded patch before another live attempt. A new live attempt requires
fresh explicit token/time authorization; the unused balance of the previous run cannot
fund a retry automatically. Do not increase the ceiling solely to address this response
ID failure: the last stop was at 45,212 tokens. Continue in this chat because the exact
case and active patch remain useful; reuse gpt-5.6-sol / low for a future comparable
live acceptance case after authorization.
