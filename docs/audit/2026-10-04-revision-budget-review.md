# Revision budget review

Scope: local review and synthetic verification following live acceptance attempt
eight. No further live attempt or budget increase was authorized or launched.

## Findings

The existing allocation protected three times one tenth of the task ceiling for
re-review: 54,000 tokens at the approved 180,000 ceiling. This is below observed
review usage. Attempt seven's first reviews consumed 56,361, and its second
reviews consumed 69,717. The controller admitted revisions with any grant above
1,000, even though observed successful revision usage was 31,215. It also did
not reserve the minimum final integration allowance and its telemetry margin.

Attempt eight's proof-report correction used another 32,731 observed tokens.
This left 78,074. The fixed reservation assigned 24,074 to the author, whose
revision reached 30,087 before stopping. Final usage telemetry was incomplete.
The stop was correct enforcement of the author grant; the total task ceiling
alone did not entitle the author to borrow the future review reservation.

## Implemented bounded follow-up

- Before each revision, derive a separate reserve for each specialist role from
  its largest completed actual audit usage, rounded upward with a 25% margin.
  Retain the original one-tenth-of-task floor per role. Corrections on a role's
  existing worker contribute observed usage to that role's estimate.
- Protect 7,000 for final integration: the existing 6,000 minimum grant and
  1,000 margin. Initial/repeated audit grants and report correction grants also
  retain this capacity.
- Require an author grant at least one sixth of the task ceiling, or 125% of
  its largest completed author usage, whichever is larger (minimum 1,000).
  Preserve the existing one-quarter-of-task maximum revision grant. Stop before
  dispatch if this complete-cycle plan cannot be funded.
- Re-review grants preserve the different per-role reserves and distribute
  remaining capacity evenly. An expensive role's observed reserve is not lost
  through equal averaging.
- Record remaining tokens, role reserves, author minimum/grant and handoff
  reserve in the campaign and controller trace before admitting or declining
  the revision. Reuse the existing task ledger and pending-allocation accounting.

These are conservative planning estimates, not hard guarantees or a claim that
25% is statistically calibrated. Live in-flight calls can still overshoot their
grants. Report corrections remain bounded to one per specialist. No budget is
reset, no unobserved future correction is promised, and no review or release
gate is weakened. The final reviewed candidate remains immutable at integration.

## Replay of the saved observations

At attempt seven's first revision decision, the observed-role reserve would be
70,452 and the final reserve 7,000. With 110,069 remaining, the author grant is
32,617, above the 30,000 minimum and above the observed successful 31,215 usage.
This is allocation arithmetic, not a rerun or guarantee of the later reviews.

At attempt eight's decision, the observed-role reserve would be 87,682, plus
7,000 final integration, already greater than the 78,074 remaining. The new
policy would decline the revision before dispatching it. It does not complete
the manuscript; it avoids beginning an underfunded cycle and preserves the
accepted diagnostic candidate, source objections and all report evidence.

## Verification

All 10 focused budget, revision, handoff and observed-review-size regressions
passed after the final allocation changes. This includes two arithmetic replays
of the saved live usage and a controlled-process end-to-end case with unequal
reviewer costs, fresh re-review workers and successful parent integration.
Existing tests retain stopping before revision dispatch, author correction
reservation, report correction exhaustion and the observed 19,555-token review
case under the 96,000 ceiling.

An earlier full manuscript-quality run passed 53 cases and found one mistaken
expected replay value, 32,616 instead of the correctly rounded 32,617. That test
expectation was corrected; both replay cases then passed, followed by the final
10-case focused run covering the subsequent per-role dispatch change. Ruff on
the runner, tests and controlled worker and `git diff --check` passed.

The original acceptance artifacts were read only. The checkout's unrelated
changes, frozen desktop pilot, original manuscripts, default database and PoP
checkout remain preserved. No commit, push or deployment was performed.
