# Structured manuscript length validation

## Implementation

Manuscript tasks now accept optional explicit bounds:

```json
{
  "task_type": "manuscript",
  "manuscript_length": {
    "min_words": 900,
    "max_words": 1200
  }
}
```

The task form exposes both bounds under Manuscript review settings. Both must be
positive integers, minimum no greater than maximum, capped at 200,000. Bounds are
inclusive and manuscript-only. Leaving them blank preserves existing behavior.
No numeric bounds are inferred from natural-language success criteria.

The versioned `section-text-whitespace-v1` policy counts whitespace-delimited
tokens in every section's text, including equations and references. It excludes
title, headings, claim metadata and reviewer-response metadata. This is a precise
acceptance count, not a linguistic word counter or a judgment of manuscript quality.

An out-of-bounds draft is rejected before manuscript sections, claims or candidate
history are modified and before specialists are dispatched. The existing single
bounded author correction receives the actual count, both bounds, counting policy
and affected field. A repeated failure retains rejected returns and stops using
the original ledger/deadline. No new retry path was introduced.

Reviewer packets now carry structured task requirements, natural-language success
criteria and the deterministic length result. Explicit bounds take precedence over
the author's previous approximate 1,200-word guidance. Readiness exposes the length
result, also shown in the task UI. Quality assessment rechecks bounds and binds
review packets to the current requirements; changing the requirements invalidates
prior clearance. Existing publication/evidence and revision-review services remain
the authority for their respective gates. Passing length does not confer scientific
clearance or human publication approval.

## Verification

New regressions cover invalid/reversed/non-integer bounds, inclusive endpoints,
counting scope, legacy tasks with only prose length requests, rejection before
manuscript mutation, bounded correction failure, packet/readiness propagation,
stale bounds and API round trips. The saved 785-word synthetic live candidate was
replayed offline with explicit 900–1,200 bounds and rejected with the expected
structured issue. Its frozen candidate, reports and historical statuses were not
changed; no model call was made.

**156 distinct focused tests passed** across manuscript quality, Codex worker,
research-task API, publication packages, desktop evidence workflow and pair
regressions, including 13 new length/API tests. Python F/I lint, JavaScript syntax
and diff checks passed. Existing Starlette/httpx/anyio deprecation warnings remain. Existing checkout changes and frozen pilot
artifacts remain intact. No commit, push, deployment or new live run is included.

## Related follow-up

A combined offline acceptance-contract audit could check other explicit completion
requirements, their propagation to every reviewer, and repair/revision budget edge
cases together. Avoid translating arbitrary prose into guessed hard requirements.
Keep task completion, scientific clearance and human release approval separately
visible. For that broader review, gpt-6.1-sol / high is a reasonable cost-conscious
choice; this is a task-specific recommendation, not a measured cost comparison.
Official guidance positions GPT-6.1 Sol for complex work where time and cost matter:
https://developers.openai.com/api/docs/guides/model-selection

Continue in this chat because the acceptance evidence and implementation decisions
are directly relevant. A future live verification still requires a new explicit
token/time authorization and must set `manuscript_length` in its task contract.
