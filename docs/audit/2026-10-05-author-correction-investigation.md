# Offline investigation of the unfinished author correction

## Scope and conclusion

The user authorized continuation of the investigation. This phase used saved
synthetic acceptance artifacts, read-only access to the latest synthetic database
schema, controlled worker tests and an in-memory benchmark. No model worker or
live acceptance was launched. The preceding one-attempt authorization is consumed.

The timeout's root cause remains unresolved. The correction input was essentially
the same size as two earlier completed corrections. Retained context is a plausible
factor to test, but the saved artifacts cannot reveal server-side context handling,
reasoning duration or output volume. Increasing the task token ceiling alone would
not establish which factor matters.

## Prompt comparison

Inputs were reconstructed using the saved contract, frozen sources, verification
and search receipts, empty prior-comment/response inventories and recorded defects.
They were measured with the worker's `json_prompt` and `prompt_token_count`
(`o200k_base` in the installed environment). These are supplied-text counts,
not complete context measurements or billed usage. Current prompt instructions
were used consistently for all three reconstructions; earlier prompt provenance
was not reconstructed byte for byte.

| Saved attempt | Correction prompt tokens | Correction seconds | Result |
| --- | ---: | ---: | --- |
| Structured length | 6,813 | 72.342 | Complete return; invalid response inventory |
| Response contract | 6,815 | 98.630 | Complete, structurally accepted return |
| Stream diagnostics | 6,806 | 632.500 | Deadline stopped the unfinished turn |

The latest initial prompt measured 6,679 tokens / 24,710 UTF-8 bytes. The
correction measured 6,806 tokens / 25,206 bytes. The source list serialization
measured 2,241 bytes; the complete prompt also includes instructions, contract,
schema and receipts. The correction resends the full packet into the same thread,
which already contains the initial packet and rejected return. The returned draft
serialization measured 3,056 tokens; the initial turn's observed total usage was
15,939 tokens. That total must not be treated as the retained textual context size.

A proposed fresh correction packet containing the same full packet, defects,
`original_draft` and `original_draft_sha256` measured **9,910 tokens / 36,320 bytes**.
Its original hash is
`82a4c47b4d314b573548bed61be4f853fc31f262a9e0555475c92c039211e988`.
Fresh context would therefore send a larger explicit prompt while avoiding reliance
on the preceding model turn. This measurement does not prove faster completion.
The proposal has not been enabled in the workflow.

## What the telemetry establishes

The latest parent saved 15,849 cumulative notifications, including **15,814
agent-message delta events**, one usage update and one completed turn, plus 157
heartbeats. These counters span both author turns. They cannot partition output
between the first draft and correction, quantify characters/tokens or recover the
unfinished answer. Heartbeats establish worker activity, not useful model progress.
The stopped correction has no terminal actual usage; its full outstanding grant
remains charged. No draft, specialist clearance or release eligibility resulted.

The worker currently checks cumulative delta text against 250,000 characters.
This is a general transport bound, not the manuscript word-count gate, a bound
on model reasoning, or a guaranteed time limit. Completed-message text is selected
separately; the delta bound should not be described as covering every return path.
Do not lower it arbitrarily to force this acceptance case to pass.

## Implemented performance fix

The old delta branch recomputed `sum(len(part) for part in text_parts)` after
every fragment. It now increments one integer by `len(delta)`. The same inclusive
250,000-character boundary and failure code remain in place. No author context,
budget, deadline, response inventory or publication gate changed.

An in-memory benchmark used identical eight-character fragments, three repetitions
per size, and median elapsed time on this machine:

| Fragments | Characters | Repeated full-buffer count | Incremental count |
| --- | ---: | ---: | ---: |
| 15,849 | 126,792 | 5.835 seconds | 0.003574 seconds |
| 50,000 | 400,000 | 55.756 seconds | 0.011202 seconds |

The larger case intentionally benchmarked accounting without the production bound;
production would stop before its final size. Neither case replays the actual
fragment distribution. The smaller case's old loop visits 125,603,325 fragment
lengths. This establishes avoidable quadratic accounting, not the cause of the
632-second live correction. The benchmark was run entirely in memory and wrote
no acceptance artifacts.

## Verification

- All **35** tests in `tests/test_research_codex_worker.py` passed, including two
  new controlled multi-fragment cases: exactly 250,000 characters accepted and
  250,001 rejected with `response_text_bound`, with interruption in both cases.
- Four selected cases in `tests/test_manuscript_quality.py` passed using
  `-k 'author_correction or length_correction_uses_empty_response_inventory'`.
  They preserve one correction, both returned drafts and review funding.
- **39 focused tests passed in total**. Ruff checks for F/I passed on the touched
  worker and test files; `git diff --check` passed. Git status and diff statistics
  were reviewed; the broader existing dirty changes are not this phase's changes.

Saved acceptance files and the frozen October 3 pilot were read only. The only
implementation change in this phase is the incremental character counter, with
its focused regression cases. Earlier dirty changes remain intact.

## Recommended next offline change

Add non-content, per-turn stream measurements before another paid/live experiment:
delta count, accumulated characters/UTF-8 bytes, elapsed time since turn start,
first/last delta timing, and supplied prompt-token estimate with its counting policy.
Bind them to controller call span and model turn identity, reset at each turn and
validate finite numeric values and allowed fields at controller intake. Preserve
legacy progress events and never store delta text or exception messages in telemetry.
Persist a final snapshot on controlled interruption/error where possible.

Then prepare one bounded fresh author correction, reusing the specialist repair
pattern: retain the same logical worker; bind the original rejected draft by hash;
include the exact frozen task/source packet, defects and response inventory;
reject a second correction; reset only model-thread usage baseline. Keep the
controller ledger, shared deadline, specialist reserves and release gates unchanged.
Tests must cover initial drafting and scientific revision, hash tampering,
second-correction denial, original-return preservation and missing usage accounting.

These changes can be prepared offline under the existing scoped implementation
authorization. A live comparison still requires a new explicit attempt, model and
token/time budget. Change one experimental factor at a time; raising reasoning
effort as well as changing context would confound the comparison.

Continue in this chat: the three saved attempts and dirty implementation are directly
relevant. gpt-6.1-sol / medium is a suitable current-session recommendation for the
bounded implementation/review. No model setting was changed by this investigation.
