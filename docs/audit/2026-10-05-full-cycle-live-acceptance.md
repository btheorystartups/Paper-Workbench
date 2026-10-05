# Full-cycle acceptance at 320,000 tokens / 1,200 seconds

## Authorization and outcome

The user authorized the proposed single acceptance attempt at **320,000 tokens /
1,200 seconds including setup**, one scientific revision cycle, retaining
**gpt-5.6-sol / low**, with no automatic retry and fresh temporary storage.
This attempt consumed that authorization. No second attempt ran.

The outcome is **`limit_reached_partial`**, with stop reason
`time limit reached; further research stopped`. The first 787-word draft failed
the required 900–1,200-word range. Its fresh intake correction returned an admitted
979-word draft. All four independently returned specialist reports were accepted,
with scientific/coverage objections preserved. Scientific revision was admitted
by the token-capacity gate and returned a proposed 884-word draft with all 21
required response IDs. Length validation rejected that revision. Its single fresh
intake correction stopped at the research deadline without a complete return.
Independent re-review and final model integration did not run.

The saved finish measurement is **1,096.830 seconds including setup**, within
1,200 seconds. The launcher was confirmed absent before the outer ceiling. Actual
reported usage is **139,189 tokens**; controller charged usage is **180,909**.
The interrupted final correction has no terminal actual usage, so its entire
**41,720-token** allowance remains charged as an estimate. These numbers are not
a complete measured usage total for that interrupted turn. Token stopping remains
best effort; no confirmed usage or controller charge exceeded the approved ceiling.

**Agent checks complete: false. Live diagnostic handoff verified: false. Human
publication approval: false. Release eligible: false.** The admitted candidate is
the reviewed 979-word draft; the rejected 884-word proposal did not replace it or
apply its proposed responses to the revision ledger.

## Setup and deadline accounting

The actual preparation start was recorded at `2026-10-05T11:34:38Z`; the outer
deadline was `2026-10-05T11:54:38Z`. Preparation and approved host launch used
approximately 230 seconds, leaving 970 seconds. Preflight/setup before task creation
left a 954-second task ceiling; its existing 10% handoff time reserve was 95 seconds.
The research deadline therefore stopped model work before the outer attempt deadline.
The new task contract and planner both reported the existing 10,000-token manuscript
handoff reserve. Neither deadline nor token ceiling was extended.

The launch reused the same two frozen primary PDFs/excerpts and synthetic finite-
partition specification as the preceding attempt. It used a new synthetic SQLite
database, existing approved authentication, one capped public Crossref query of
three results, and the allowlisted finite-partition verification. It did not rerun
the October 3 pilot, read the default database or edit an original manuscript.

## Returned calls and stopped operation

Times are controller-observed operation spans, not exclusively model inference.
The draft correction and specialist calls overlap only as recorded in the trace;
the four reviews used three concurrent slots.

| Operation | Seconds | Actual tokens | Streamed characters | Result |
| --- | ---: | ---: | ---: | --- |
| Initial author draft | 163.520 | 15,042 | 10,735 | 787 words; rejected for length |
| Fresh draft correction | 175.603 | 18,508 | 12,322 | 979 words; admitted |
| Source/citation review | 40.646 | 19,945 | 8,875 | Accepted report; blockers retained |
| Literature/contribution review | 151.344 | 20,063 | 9,389 | Accepted report; blockers retained |
| Proof/method review | 170.526 | 20,440 | 9,538 | Accepted report; blockers retained |
| Adversarial review | 199.667 | 21,080 | 12,773 | Accepted report; blockers retained |
| Fresh scientific revision | 228.467 | 24,111 | 16,431 | 884 words; rejected for length |
| Fresh revision intake correction | 32.437 | Unknown; 41,720 charged | 1,316 | Deadline stop; incomplete |

There was no recorded stream failure or report-format correction. The seven
completed calls retained final actual usage and finished stream measurements.
The final correction retained its partial stream and stopped-operation receipt.
Call spans, model identities, controller timestamps and function stacks are saved.

## Claim coverage and proposed corrections

The corrected first draft produced three overlapping groups of review findings:

- **Compound source attribution:** C1 combined a complete partition-family
  definition with indit/dit terminology, but listed only the selected 2010 excerpt.
  That page supports the terminology without explicitly stating the complete
  family definition. The supplied 2019 excerpt provides that definition; the prose
  also cited it without including it in C1's source map.
- **Uninventoried dimension wording:** S5 said equal block counts give equal
  dimensions. The manuscript had defined Boolean-function sets and proved their
  cardinality, without defining a vector-space structure or a dimension claim.
- **Reproducibility coverage:** The adversarial reviewer required the runtime,
  implementation hash, invocation, dependencies and deterministic-output assertions
  in S6 to be represented explicitly in the inventory, beyond C9's finite results.

These findings generated **21 bound review entries across four roles**, rather
than 21 distinct underlying mathematical defects. They remain unresolved. The
unadmitted revision proposed splitting the family definition from terminology,
adding C12 with the terminology's source mapping, using cardinality wording and
expanding C9's receipt/reproducibility scope. It returned exactly the 21 unique
expected response IDs, with no missing or invented ID. Author proposals cannot
close objections without admission and independent re-review.

The earlier saved finiteness objection did not recur in these reports; a different
scope extension appeared as dimension wording. This demonstrates that explicit
instructions alone do not guarantee complete semantic inventory coverage. The
independent reviewers identified those gaps. Claim counts and ID mappings alone
cannot establish that every prose assertion has the same domain and assumptions.

No ambiguous evidence-availability release flags were recorded for the admitted
candidate. Bibliography placeholder gates and separate human publication approval
remained enforced; no saved output was promoted.

## Full-cycle capacity

The before-review plan reported one conditional revision as `estimated_funded`:
286,450 remaining tokens versus 244,941 forecast required, with no additional
configured cycle left unforecast.

After all first-wave reviews, revision admission reported:

| Reservation | Tokens |
| --- | ---: |
| Minimum author revision | 22,381 |
| Four-role independent re-review | 101,911 |
| Repair reserve | 27,180 |
| Final handoff | 10,000 |
| Required remaining capacity | **161,472** |
| Available remaining capacity | **204,922** |
| Shared and author-slice shortfalls | **0** |

The author grant was 65,831 tokens. Thus the larger token ceiling resolved the
preceding saved-case token-admission stop for this attempt. It did not provide more
time or guarantee length compliance.

The time forecast correctly recorded **`time_risk`**: observed-duration replay
estimated 403.832 seconds for revision and re-review against 260.400 remaining
research seconds. It intentionally served as a planning flag, not a hard admission
gate. The actual scientific revision alone took 228.467 seconds, longer than the
initial draft duration used for the estimate, and its length failure triggered
another author call. Re-review never began.

The first length correction consumed 175.603 seconds and the rejected revision was
16 words below the minimum. The recurring remaining problem is model compliance
with the aggregate section-text word bounds. The validator correctly detects it;
the native schema constrains structure and response inventory but does not itself
enforce that aggregate word count. More tokens alone cannot remove these extra
calls, setup time, changing model durations or the fixed clock.

## Verified behavior and preservation

- Actual maximum concurrent specialist workers: **three**.
- Adversarial review began after the source worker returned and closed, before
  proof and literature review returned.
- Four distinct author model contexts and four distinct reviewer contexts were
  recorded; reviewer identities were distinct from all author history.
- Fresh author intake correction completed live in 175.603 seconds. Fresh
  scientific revision returned successfully with bound response inventory.
  The final fresh correction did not finish. These observations do not isolate
  fresh context as the cause of differences from earlier retained-context runs.
- All ten recorded worker/runtime PIDs and launcher PID **23020** were absent
  after shutdown.
- Implementation hashes, frozen primary PDF hashes and all **131** frozen pilot
  file hashes were unchanged.
- No implementation edits, secret extraction, default database access, original
  manuscript edits, commit, push, deployment or external message occurred.

The temporary runner/verifier scripts compiled before launch. No new tests were
needed because this phase did not change implementation. The preceding focused
test, lint and syntax results remain documented in the offline investigation.

## Saved evidence and bindings

Folder:
`C:\Users\brian\AppData\Local\Temp\paper-workbench-cycle-capacity-acceptance-86fe443307ce4c5ea55e747794e8b23f`

Files include `approved-launch.json`, `host-launch.json`, `setup-verification.json`,
`frozen-input-manifest.json`, `snapshot.json`, `quality-assessment.json`,
`readiness-report.json`, `call-trace.json`, `call-timing-summary.json`,
`stream-measurement-summary.json`, `acceptance-checks.json`,
`post-run-verification.json`, `worker-cleanup-verification.json` and
`research-package.zip`. The package predates the supplementary post-run checks,
which remain alongside it.

- Task: `e2a4939d5dcf4251ae0c092051b9bb6b`
- Manuscript: `02b1c05c7722493185e26b23c34a3939`
- Admitted draft return: `17fb2ddf0fd6ae44fac6c6cbde1b92ee7ac6e3c8cdea5e68a04b7f15d4867ec6`
- Current admitted candidate: `724a39e94a67d2469f6e5be4e269470fb008251fb316a6dc951bde04a9328c35`
- Rejected scientific revision: `d422ed0943aae502989145fb397e50528aed4068d147b7c72c5ec26eb2232120`
- Snapshot: `1637b854a93491923bd1621f58a288b854c493858d5a0a71c632a24d70a252c2`
- Package: `feb51b687fdc5626303789509d3dc5a50ed02eff7acd660aefee3a8fe171fdca`

## Next phase and thread choice

This authorized attempt and its verification are complete; manuscript clearance
is not. Before purchasing another attempt, prioritize a bounded offline follow-up
on reliable length generation and complete revision/re-review time admission,
including repair overhead. Preserve the word bounds, semantic objections, frozen
bindings, independent closure and release blockers. Do not silently pad manuscript
text or increase either ceiling to obtain a pass. Evaluate the granularity of
scientific claims versus receipt metadata as an explicit policy question; it must
not be used to erase the existing unresolved source and scope objections.

Continue in this chat because its bound evidence and active dirty implementation
are directly needed. **gpt-6.1-sol / medium** is sufficient for that focused offline
diagnosis and tests. A further live attempt requires new explicit authorization;
no larger budget or stronger manuscript model is recommended until these two
failure modes are addressed together. No retry remains authorized by this run.
