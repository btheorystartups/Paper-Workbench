# Offline follow-up: source passage binding

Date: 2026-10-04. Canonical checkout: `C:\Users\brian\Documents\Paper-Workbench`.
This is an offline follow-up to [acceptance attempt five](2026-10-04-specialist-manuscript-acceptance-5.md), not another live attempt.

## Diagnosis

The source reviewer marked C1 and C2 `supported_within_scope` and cited the 2019
excerpt in their `passages`. Both claims also listed the 2010 source ID
`cc6e485ffd3041c7a39099f3c2276210`, which appeared only in the reviewer's prose
explanation of support. The validator correctly retained a missing-passage
blocker for each claim. There was no report-schema failure or unavailable source
artifact: the required source-specific binding was missing.

Inspection was limited to the exact frozen text admitted to that review packet.
The excerpt files were verified equal to the packet's admitted source text.

| Claim | Supplied 2010 excerpt, PDF p. 7 / journal p. 291 | Supplied 2019 excerpt, PDF p. 2 |
| --- | --- | --- |
| C1: complete partition definition, indits and complementary dits | Begins partway through the discussion; contains same-block indits and the complement relation, but not the complete nonempty/disjoint/covering definition. Supports only part of C1 as written. | Explicitly gives the partition definition, same-block relation and complement. Covers the whole claim. |
| C2: equivalence-relation order, Ellerman's opposite convention and reversed join/meet names | Gives refinement by containment, dit-set inclusion and a footnote about the opposite order. Together with complementation these permit an inference about relation inclusion, but the supplied page does not explicitly discuss the join/meet swap. | Explicitly relates the opposite order to equivalence-relation inclusion and states that join/meet definitions reverse. Covers the whole claim. |

These observations concern the supplied page selections, not everything in either
paper. Adding an arbitrary exact 2010 quotation would not establish whole-claim
support. A future author should cite the 2019 excerpt alone for the combined
claims, or split them into narrower sourced statements and explicitly derived
consequences. The saved manuscript and review dispositions were not changed.

## Reviewable correction

- The author prompt now explains that every source ID creates a separate
  whole-claim support obligation. It asks for the smallest sufficient source
  set and separate claims when different sources support different clauses.
- The source-review prompt explicitly requires passages for every source ID on
  that exact claim. Prose assurances, a different source's quotation, and
  quotations attached to another claim cannot satisfy the requirement. Partial
  support must be returned as unresolved with a specific blocking objection.
  Exact text identity alone does not establish semantic entailment.
- The existing deterministic check now names the missing source IDs in its
  blocker. It retains per-claim set coverage and exact quotation checking against
  each bound frozen source. Out-of-claim sources remain report validation errors.
  Missing bindings remain accepted diagnostic findings that block release; they
  were not converted into automatic approval or a fresh reviewer call.

No parallel evidence mechanism was added. Packet/artifact availability checks,
historical corrections, `revision_review.py`, publication evidence binding and
bibliography release blockers retain their existing behavior.

## Offline verification

Four new synthetic regressions cover missing per-source bindings despite prose
assurances or a quotation on another claim; duplicate quotations from the first
source; correct bindings for both sources; a real quotation misbound to the
other source; and an explicitly unresolved assessment that preserves its
blocking objection. They also check that validation does not mutate the packet
or report. These are controller checks, not claims about future model behavior.

A read-only replay of all three saved reports produced exactly the original two
source blockers, now naming the missing 2010 ID. The proof and contribution
reports still had no blockers. The task remained `limit_reached_partial`.
SHA-256 checks before and after the replay confirmed unchanged bytes for the
saved database, snapshot, quality assessment, research package, both excerpts,
source receipts and both controller trace files.

Replay output:
`C:\Users\brian\AppData\Local\Temp\paper-workbench-source-binding-offline-db7501749b214509861dc883e28e3cb2\replay-result.json`.

The focused suite passed **120 tests** in 191.58 seconds across manuscript
quality, the Codex worker boundary, desktop evidence workflow, paired workflow,
publication packages and manuscript paths. This includes the four new cases,
packet-specific historical corrections and accepted diagnostics with unresolved
bibliography markers. Two dependency deprecation warnings were emitted by the
Starlette test client; there were no test failures. Ruff and `git diff --check`
passed. No manuscript agent, external service or default database was used by
this verification.

## Remaining acceptance and budget

The prompt correction still needs live verification. A successful bounded run
must return three complete, correctly bound specialist reports, independently
resolve any objections after revision, complete the final parent handoff and
preserve the release gates. Human publication approval remains separate. This
would validate the selected expository acceptance case, not every future
manuscript or an original research contribution.

The last first wave cost 14,102 author tokens plus 54,933 reviewer tokens, or
69,035 total. Repeating an author-sized revision and a similar three-reviewer
wave would bring the estimate to about 138,070 tokens before the final handoff
and any context growth. A 96,000-token ceiling can still succeed on a clean
first pass, but does not budget that measured revision path. The proposed
180,000-token ceiling would provide room for one such additional wave and the
handoff; this is a planning estimate, not a guarantee or authorization for two
revision cycles.

Automatic approval review rejected the earlier 180,000-token proposal as an
unapproved increase. No new live run, increased cap, commit, push or deployment
is authorized by this offline continuation. A further acceptance run needs
explicit approval for its limits. Use this thread for that closely related
follow-up and retain `gpt-5.6-sol` / low for comparable worker behavior.
