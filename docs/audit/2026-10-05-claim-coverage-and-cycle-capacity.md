# Claim coverage and full-cycle capacity: investigation and offline fixes

## Scope

The user asked for an in-depth investigation and fixes after repeated acceptance
stops. This phase used repository code, the saved synthetic acceptance artifacts,
read-only synthetic database queries and controlled tests. No new live attempt,
paid request, manuscript model worker, original manuscript edit, pilot rerun,
default database, secret access, commit, push or deployment occurred.

The canonical checkout is `C:\Users\brian\Documents\Paper-Workbench`. Existing
dirty changes and `working/desktop-pilot-2026-10-03` were preserved. Saved live
artifacts were not edited or promoted. The numerical replay is saved separately in
`2026-10-05-claim-coverage-capacity-replay.json`.

## Why the repeated stops have different causes

These attempts did not test one unchanged system. Requirements and validation
became stricter, and the production manuscript policy grew from three independent
review roles to four, including mandatory adversarial review. The earlier
180,000-token success is not a controlled comparison with the current task.
The current ceiling funds every author/reviewer/correction/summary call together;
it does not increase reasoning effort, guarantee valid output or create separate
budgets for each phase.

| Recent saved attempt | What happened | What it establishes |
| --- | --- | --- |
| Structured length | 811-word first draft; 1,045-word correction invented a `manuscript_length` response ID | Length enforcement worked; the author response contract needed explicit binding |
| Response contract | 849-word first draft; 1,079-word correction accepted; proof stream raised generic ValueError | Response fix worked; the old telemetry could not identify the precise stream branch |
| Stream diagnostics | 796-word first draft; retained correction streamed for 632.5 seconds without a complete return | Deadline enforcement worked; no saved output-size measurement establishes the cause of that long correction |
| Fresh author/live telemetry | 902-word first draft and four valid reviewer returns; source coverage objection; revision reservation stop | Transport and length worked in this case; the budget could fund initial review but not the reserved follow-through cycle |

See the corresponding `2026-10-05-*-live-acceptance.md` and
`2026-10-05-fresh-author-live-verification.md` audit records for exact bindings.
The long correction's root cause remains unresolved; the latest run did not need
an author intake correction, so it cannot establish that fresh correction fixes it.

The latest source-review objection is a legitimate review finding. A production
workflow must be able to absorb such findings through revision and independent
re-review. Treating every objection as a new software failure led to repeated
investigation at a stage where ordinary revision should have been budgeted.

## Claim coverage finding

The saved draft's refinement section says the proof does not require finiteness.
The mapped claim states the refinement equivalence and separating-function converse
without explicitly recording that broader domain; the note's standing assumptions
are finite nonempty carriers. Its limitations also repeat the broader observation.

The proof reviewer found the argument valid. The source reviewer identified missing
inventory coverage; literature and adversarial reviewers did not flag it. This
disagreement does not close the source objection. Truth of a mathematical extension
and completeness of its claim inventory are different checks. A section containing
the correct claim ID still may assert something broader than that claim's statement.

The supported remedies are to make the arbitrary nonempty-carrier scope explicit
in the mapped claim and have it re-reviewed, or omit the unrequested extension from
the prose/limitations. This phase did not edit the saved manuscript or certify the
extension. The existing independent review ledger remains the closure authority.

### Implemented coverage changes

- Claim schema descriptions require explicit domain, quantifiers and assumptions;
  section descriptions require mapping of scope extensions and side remarks.
- Author instructions require a prose/claim inventory pass over sections,
  conclusions and limitations, including assumption removal. Unrequested extensions
  must be explicitly inventoried/proved or omitted.
- All reviewer roles are explicitly told to check these scope changes, including
  mathematically true extensions missing from the inventory.
- No regex attempts to decide mathematical scope or semantic completeness. Existing
  structural ID checks, independent assessments and release blockers remain in place.
- A synthetic source-only objection regression confirms that three other passes do
  not grant clearance; both recorded source entries require bound author responses
  and fresh independent re-review.

These instructions should reduce the specific omission; controlled tests cannot
prove that a model will always follow them. Independent review remains necessary.

## Capacity and context findings

The latest actual usage was 105,498 tokens. Its remaining 134,502 could not cover
20,530 minimum author tokens, 111,344 re-review tokens, 28,213 report-repair reserve
and 10,000 handoff reserve. The old saved forecast needed 170,087 remaining tokens
and was 35,585 short. It stopped before revision, rather than spending the protected
review/handoff capacity. No token ceiling or time limit was exceeded.

Three design issues contributed to late surprises:

1. **Cycle planning appeared after initial review.** A maximum of two revision
   cycles was configured, but a fundable cycle was not explained before paying
   for the first four reviews. Maximum cycles are an upper bound, not a promise
   that the authorized ceiling funds that many.
2. **Supplied prompt estimates excluded retained author history.** Scientific
   revision resent evidence, previous candidate and comments into an existing
   author thread. Earlier input, output and internal context were not measurable
   from those supplied-text estimates. Fresh report repairs already avoided this.
3. **Review scheduling left available slots unused.** Initial adversarial review
   waited for all three first roles; re-review started two roles and then ran the
   remaining roles one at a time. The fourth role is independent and its budget
   can be protected while a freed slot is reused.

The manuscript creation form also defaults to 96,000 tokens, while the latest
first draft and four reviews actually consumed 105,498. That form budget cannot
be treated as a promise of a complete production cycle. Budget guidance and the
latest candidate-bound forecast are now visible in the interface. This phase did
not increase the default budget or authorize additional spending.

New manuscript contracts now advertise the same 10,000-token handoff reserve that
the planner already protects, using a shared policy constant. General research
keeps its existing percentage reserve. Saved task contracts were not rewritten.

Prompt serialization also repeated a general JSON schema in text while `turn/start`
already carried the stricter operation-specific native `outputSchema`. That textual
copy lacked runtime refinements such as the exact response inventory. Frozen source
text, verifier code and candidate text remain necessary evidence and were retained.

### Implemented context and prompt changes

Scientific revisions now use a fresh ephemeral model thread on the same logical
author worker. They carry the previous candidate/hash, frozen contract/source and
receipt packet, all prior comments/responses and exact expected response IDs. The
worker compares the previous candidate with its own latest returned draft, including
any intake correction, and rejects altered candidate/evidence before dispatch.
Only per-thread usage resets; controller charges, original deadline, one intake
repair per phase and independent re-review remain unchanged.

All recorded historical author thread identities are excluded from reviewer
identities. This closes the independence gap that would result from checking only
the author's latest fresh model thread.

Prompts now serialize the complete supplied data compactly and use the native
schema once. The frozen dictionaries, source text and packet hashes are preserved.
In the saved first-wave packet reconstruction, review prompt sizes changed from
approximately **15,944–15,949** supplied tokens to **13,224–13,229**. Actual historical
dispatch counted additional transport metadata; this comparison uses the same
packet-only reconstruction on both sides. A smaller supplied prompt is not a
measured billing or latency saving: native schema and service overhead remain.

### Implemented planning changes

Before initial specialist dispatch, a capacity plan records the first full review
plus one conditional author revision, four re-reviews, repair pools and handoff.
It projects known historical-inventory growth using actual current packet identities
without inventing future objections. It identifies additional configured cycles,
future candidate size, model usage and wall time as unknown. The risk flag does not
force a revision of a draft that already passes.

Revision admission now reports required remaining tokens, shortfall, implied minimum
total ceiling, and a separate author-slice cap shortage. The ceiling calculation
includes that cap, so it does not misleadingly propose a ceiling that still cannot
grant the minimum author slice. Existing role-specific usage plus 25% margins,
prompt/output floors, repair and handoff reserves are retained.

Readiness exposes the latest capacity plan with its stage and candidate/ceiling
basis; changed bases are historical. The interface displays the shared shortfall,
author allowance shortfall, estimated minimum total budget and observed time replay
when available. Planning metadata does not grant scientific clearance or
publication approval.

Each review wave starts three roles and dispatches the fourth after a worker
completes and closes. Known format defects pause further dispatch until their
bounded correction is finished, and waiting correction workers occupy slots.
The three-worker limit, grants for deferred roles and repair/handoff reserves remain
protected. Timing estimates replay returned calls using that schedule and label
startup, repairs, handoff and changed model latency as unestimated.

## What the saved-case replay predicts

Historical observed usage was kept unchanged, rather than discounting it based on
the new prompt. The updated revision forecast still needs **166,850** remaining
tokens, with **134,502** available: **32,348 short**, implying **272,348 total tokens**
for this saved forecast. Four-role reserves remain 111,344; repair input reduction
lowers that reserve to 24,976. This result is not a guarantee for a new run.

Replaying the first-review milestone with the saved 902-word candidate warns of
conditional cycle capacity risk before review: 241,785 estimated remaining tokens
with two stage-specific repair pools versus 223,576 remaining. Its implied total
ceiling is 258,209, and one further configured revision cycle remains unforecast.
The difference from the post-review forecast is expected: actual specialist usage
and objections were unknown before those calls returned.

Using the saved returned call durations, the old initial schedule represents about
306.47 seconds of review operations; the new three-slot replay represents **194.92**.
The old two-role/serial re-review schedule would represent about 427.26 seconds
with those same role durations. Fresh author plus new review replay represents
**372.54 seconds** before startup, format repairs or final handoff. These are
offline scheduling calculations, not measured new model timings. A larger token
ceiling alone does not address the 900-second clock.

## Verification

The focused suite passed **237 tests** across `test_research_codex_worker.py`,
`test_manuscript_quality.py`, `test_research_transport.py`,
`test_publication_packages.py`, `test_evaluation_desktop_workflow.py` and
`test_evaluation_pair.py` in 382.14 seconds. After the final author-slice reporting,
admission and handoff metadata changes, **13 targeted capacity tests passed** in
15.80 seconds, including the new cap-shortage and contract/planner reserve
regressions. **Four research API tests
passed** in 9.79 seconds after the interface update. The two warnings are existing
Starlette/httpx and anyio alias deprecations.

Ruff F/I checks passed on the changed Python surfaces and fixtures. The interface
passed `node --check`; `git diff --check` found no whitespace errors. The dirty
checkout was reviewed and preserved; no staging, commit or push was performed.

Controlled coverage includes native schema with literal/Unicode frozen data preserved, fresh
scientific revision from both an initial and corrected draft, candidate/evidence
tampering before dispatch, historical author/reviewer independence, source-only
scope objection closure, early planning/unchanged packets, stale capacity basis,
author-slice ceiling math, rolling dispatch with and without correction, and token
and concurrency preservation. Existing bibliography/release, historical packet,
response inventory, correction count and missing-usage regressions are included.

Scheduling tests that required the former two-role/serial order were updated to
assert the new slot-release behavior and preserved grants. Known format-failure
tests retain their fail-closed/no-handoff assertions; dispatch pauses during repairs.

## Next phase

The authorized offline investigation, fixes and verification are complete. The saved
manuscript remains unresolved and unreleased. The new scientific-revision context,
native-only schema prompt and rolling dispatch require a separately authorized live
acceptance; the preceding one-attempt authorization was consumed.

A concrete proposed trial is **one attempt at 320,000 tokens / 1,200 seconds including
setup**, retaining **gpt-5.6-sol / low**, allowing **one scientific revision cycle**,
one intake correction per author phase and one report correction per specialist,
all four independent roles, no automatic retry and a fresh temporary output folder.
The budget provides headroom above the saved-case floor, and the longer clock
addresses the observed-duration replay; neither guarantees completion. Any second
scientific revision would require a different explicit capacity/budget plan.
This proposal is not authorization to run it.

Before dispatch, capture the setup start at the actual beginning of attempt
preparation, rather than adding an arbitrary initial time reservation. Preserve
implementation/source/pilot hashes, retain every call/stream/response receipt,
report readiness separately from human approval, and verify all worker shutdowns.
No gate may be weakened to obtain a pass.

Continue in this chat because this exact case, dirty patch and bound evidence are
needed. gpt-6.1-sol / medium is sufficient for orchestration/review; the evidence
does not establish that raising manuscript model reasoning would fix a capacity
stop. No additional live work or spending is currently authorized.
