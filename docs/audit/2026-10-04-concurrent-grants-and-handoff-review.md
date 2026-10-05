# Concurrent grants and final context review

Scope: authorized local review following acceptance attempt nine. No live task,
budget increase, model change, commit, push or deployment occurred.

## Findings

Attempt nine's second-wave literature worker exceeded its fixed grant by 520
observed tokens. Earlier proof/source workers had completed below their grants,
releasing 1,470 and 473 tokens. Those 1,943 tokens were available in the task
ledger, but could not enlarge a running worker's originally supplied limit.
Both worker and controller enforce that individual allowance. Sending a larger
grant after the fact would not recover the stopped structured report.

Final integration had a different risk. The controller supplied compact review
decisions, but the parent worker reused its existing author/revision model
thread. Input preflight counted only the new prompt, while the model context
included earlier turns. A small compact payload therefore did not establish
that a final turn would fit the protected 7,000-token reserve.

Offline token counts of the existing compact integration payloads were 5,105
for attempt seven and 3,975 for attempt nine, using o200k_base. These were size
measurements on incomplete campaign evidence, not authorized integration inputs
or evidence of completed reviews. They exclude model/runtime overhead and output
and do not establish actual billing or guarantee the reserve is sufficient.

## Implemented bounded changes

First-wave review still permits three concurrent specialists. Re-review starts
proof and source workers concurrently and dispatches literature after both have
returned and any permitted report corrections have completed. Its fixed grant
uses then-available task capacity after preserving the 7,000 final handoff reserve.
Already-running grants do not change. No new task, deadline or token ceiling is
created. All three roles remain required and use fresh identities.

Corrections to the initial pair preserve the deferred role's reservation as well
as final integration. A repeatedly invalid report stops partial before launching
the deferred reviewer. This is a scheduling tradeoff: the last specialist starts
later, increasing latency, while completed receipts make unused capacity usable
for its initial grant. It does not guarantee all possible reviews fit the budget.

For manuscript final integration only, the persistent parent worker starts a new
ephemeral summary thread using the same existing verified thread/start options.
The controller still supplies compact immutable review decisions and preserves
the manuscript unchanged. Author/revision operations and specialist corrections
keep their original threads. The final turn records its previous and new thread
IDs and fresh-context policy in provenance. The per-thread usage baseline resets
for the new thread, while all earlier controller allocations remain charged in
the original task ledger. Notifications from the old thread are ignored.

No fresh model turn is created unless the controller has completed specialist
checks and sufficient final allowance. Account verification, model selection,
read-only/no-network sandbox, disabled tools and existing release gates remain
in force. Creating a fresh summary thread is not independent scientific review,
does not clear an objection and does not constitute publication approval.

## Synthetic verification

All 24 distinct focused tests passed across the worker boundary (9) and
manuscript budget/revision/correction/handoff cases (15). Worker tests verify
fresh-thread selection only for reviewed manuscript integration, unchanged
generic integration, original-task usage charging, both thread identities and
ignoring stale old-thread usage notifications. The real verified thread creation
method is exercised against a controlled client; no model/network call occurs.

A controlled-process replay uses attempt nine's observed draft, revision and
six review token counts. The deferred literature grant becomes 25,931, enough
for the observed 24,506. The synthetic campaign completes all roles, revision
dispositions and parent handoff with 171,675 charged tokens, including a fixture
100-token final summary. That summary cost is synthetic and not an estimate of
live summary usage. The test verifies both initial re-review workers close before
the deferred reviewer launches. Two additional cases cover successful correction
before deferred dispatch and repeated invalid correction stopping without a
deferred reviewer or final handoff. Ruff and git diff --check passed.

## Remaining acceptance boundary

These changes are verified offline only. Actual completion still depends on
scientific findings, actual input/output/context usage, best-effort in-flight
limits and the unchanged overall deadline. Neither reusing released capacity
nor fresh final context guarantees a pass at 180,000 tokens. A further explicitly
authorized one-attempt live verification is required to establish complete
specialist review and final handoff. Retain the manuscript-worker model for
comparison and continue in this thread, whose evidence and implementation are
directly relevant. Do not start another attempt from this review authorization.

Original manuscripts, default database, PoP checkout and earlier acceptance
artifacts were not edited. The dirty checkout and frozen pilot remain preserved.
