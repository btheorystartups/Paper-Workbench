# Live verification after fresh author correction and stream measurements

## Authorization and outcome

The user authorized the proposed one live verification: gpt-5.6-sol / low,
240,000 tokens / 900 seconds including setup, approved host launch, fresh temporary
output, no automatic retry. This attempt consumed that authorization. No retry ran.

The attempt ended **`limit_reached_partial`** after producing an admitted
**902-word** draft and accepting all **four** independently returned specialist
reports. A source-review objection requires revision. The existing budget admission
gate stopped before author revision because full reserved follow-through capacity
was unavailable. There was no stream error or time-limit stop.

Actual and charged usage both equal **105,498 tokens**, with terminal actual usage
for every allocation. Setup-inclusive elapsed time was **648.222 seconds**, within
900. The launch clock conservatively reserved 120 seconds for preparation already
completed before launch; that reservation is included in this elapsed figure and
reduced the remaining execution window. These measurements are not a controlled
causal comparison with earlier attempts.

## Calls and stream evidence

| Operation | Controller seconds | Actual tokens | Streamed characters |
| --- | ---: | ---: | ---: |
| Author draft | 177.616 | 16,424 | 11,842 |
| Proof/method review | 32.025 | 21,875 | 6,786 |
| Source/citation review | 143.574 | 22,425 | 9,975 |
| Literature/contribution review | 120.783 | 21,932 | 8,248 |
| Adversarial review | 162.898 | 22,842 | 11,421 |

The first three specialist calls overlapped, respecting the maximum three
concurrent children; adversarial review followed in the deferred wave. Call spans,
model identities, function stacks and controller timestamps are retained in the
trace/provenance. All five turns retained final per-turn stream snapshots with
finite timings and character/UTF-8 counts; completed-message sizes match their
delta totals in this case. No failure code was recorded.

The initial draft already met length requirements and had `responses=[]`. No
author intake correction, report correction or scientific revision ran. Therefore
this attempt verifies the new stream measurements live, **but does not exercise
or prove faster completion of the fresh author correction**. That behavior retains
its offline controlled verification only.

## Scientific findings and release status

The proof reviewer found the general proofs and task-seeded counterexample valid
under the stated assumptions. Literature review found no blocker in the bounded
expository scope. The adversarial reviewer returned all five required challenge
categories as `passed_within_scope`: proof stress, source entailment, novelty
limits, scope overclaim and reproducibility. These judgments apply to this frozen
candidate and packet, not universal publication quality.

The source reviewer found one blocking issue, `obj-inventory-finiteness`:
`sec-refinement` states that the refinement proof does not require finiteness, but
the corresponding claim inventory does not explicitly record that broader scope.
Its acceptance criterion is to amend `c-refinement-theorem` to state applicability
to arbitrary nonempty carriers, or add a stable mapped claim for that assertion,
then assess it under the same assumptions/proof. The report also records a coverage
flag for the same issue. The existing revision ledger preserved both review entries;
neither another role's pass nor the author's prose closes them.

Bibliographic metadata agreed with the frozen manifest according to the reviewers.
There are no recorded ambiguous-prose release flags in this candidate. Unresolved
bibliography placeholders would still block release. Human verification of complete
sources and other human approval requirements remain separate.

**Agent checks complete: false. Diagnostic handoff: false. Human publication
approval: false. Release eligible: false.** An accepted draft/report is not a
completed production campaign or publication authorization.

## Why revision was not admitted

| Reservation | Tokens |
| --- | ---: |
| Minimum author revision | 20,530 |
| Four-role re-review | 111,344 |
| Report-repair reserve | 28,213 |
| Final handoff reserve | 10,000 |
| Total required remaining capacity | **170,087** |
| Actual remaining capacity | **134,502** |
| Shortfall | **35,585** |

Per-role review reservations are 27,344 / 28,032 / 27,415 / 28,553 tokens.
The policy uses observed fresh operation usage plus 25% and prompt/output floors.
The author input estimate is 13,737 tokens; the repair input estimate is 22,213.
The admitted author grant was zero. The exact stop reason, forecast inputs and
policy are retained in `revision_budget_plans` and the call trace.

For this saved forecast alone, a total ceiling of 275,585 tokens would have met
the minimum admission calculation. That is **not** a guarantee that a new run at
that ceiling would finish: its draft, reviewers, revised packet and usage could
differ, and it would still need time and explicit new authorization. The 900-second
clock was not extended and no reserve or scientific gate was weakened.

## Verification and preservation

Post-run checks confirmed unchanged implementation hashes, frozen primary PDF
hashes and all 131 October 3 pilot file hashes. Allocation sums match the ledger;
all usage is terminal actual and both ceilings were respected. All ten recorded
worker/runtime PIDs and launcher PID 22352 were absent after shutdown.

Only a fresh synthetic temporary database/output folder was used. No original
manuscript/default database/secret files were read or edited. Normal approved
authentication was used by the existing worker without extracting credentials.
No implementation edits, commit, push, deployment or external message occurred.

## Saved evidence

Folder:
`C:\Users\brian\AppData\Local\Temp\paper-workbench-fresh-author-acceptance-e855fe68df0844c0a5391c1a0b77e88c`

See `snapshot.json`, `quality-assessment.json`, `readiness-report.json`,
`call-trace.json`, `call-timing-summary.json`, `stream-measurement-summary.json`,
`post-run-verification.json`, `worker-cleanup-verification.json` and
`research-package.zip`.

- Task: `0e8f65982b9f4f44bed2af6dbf84ab6c`
- Manuscript: `15c4e231467b425ca09be32ddd80db2f`
- Draft return: `7b1a18ccab37cf8489e3d280921cb7514893d6555e4547b60c061bfd2743c774`
- Candidate: `243e838561a2ad3561f955066bbae5a020eeaec1520e68261ece0864c88801bd`
- Package: `d21a55309a4f9fe8cf12f404e00f8f1e9995b869c89ff178c5debc9a925e5f41`

## Recommendation and phase boundary

First review the combined claim-coverage and revision-capacity findings offline
before buying another attempt. Decide whether to tighten claim-inventory guidance
and prepare a fundable full-cycle plan, or approve a larger bounded trial. Do not
manually promote this incomplete manuscript or reuse its finished live attempt.
The saved forecast supplies a concrete capacity floor, not a recommended guaranteed
budget. Live verification of fresh author correction remains outstanding.

Continue here for that focused review: it directly reuses the saved candidate,
review packet and active dirty implementation. gpt-6.1-sol / medium is sufficient
for offline review; a model/effort change in the manuscript workers is not justified
by a reservation stop alone. Any new live run needs new explicit model/token/time
and one-attempt authorization. No further live run is currently authorized.
