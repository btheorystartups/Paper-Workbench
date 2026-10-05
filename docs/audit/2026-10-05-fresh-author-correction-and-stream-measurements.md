# Fresh author correction and per-turn stream measurements

## Authorized offline follow-up

The user authorized continuation of the offline implementation proposed in
`2026-10-05-author-correction-investigation.md`. This phase implements that bounded
change and verifies it using controlled clients and synthetic temporary stores.
No live acceptance, manuscript model worker, paid service, default database,
credential store, original manuscript, commit, push or deployment was used.
The existing dirty checkout and frozen October 3 pilot remain intact.

## Author correction

The controller retains both draft attempts and supplies the first rejected draft,
its stable hash, all detected defects, frozen task/source packet, receipts, prior
comments and exact response inventory for the single correction. This applies
to intake after initial drafting and after scientific revision.

The Codex worker records its schema-normalized original return and packet hash.
Before correction it checks original-return hash, operation identity, unchanged
contract/sources/receipts/comments/response IDs/previous candidate, and that this
phase has not already used its correction. A changed draft with a newly recomputed
hash still fails because it differs from the worker's own original. Integrity
failures stop before thread creation or model dispatch.

The same logical worker starts a fresh ephemeral read-only model thread. Provenance
records `fresh_author_correction` and the old/new model thread identities. Only the
per-thread usage baseline resets. Shared controller charges, remaining allowance,
research deadline, specialist reserves, final-handoff reserve and maximum correction
count remain unchanged. Missing actual usage retains the full allocation charge.
Normal scientific revision retains its preceding context; its intake repair starts
fresh. A subsequent new scientific revision can have its own one intake repair.

This removes dependence on the rejected turn's hidden retained context. It has not
yet been shown to improve live completion time. Explicit length bounds, response
coverage, independent specialist review and human release approval remain required.

## Stream measurements

Each started turn resets a content-free measurement containing:

- Allocation call span, model thread ID and model turn ID.
- Agent-message delta count and accumulated characters / UTF-8 bytes.
- Seconds since turn start and first/last delta times.
- Last completed agent-message character / UTF-8 byte size, measured separately
  from deltas (the same output must not be counted twice).
- Supplied prompt-token estimate and `o200k_base` counting policy, or the existing
  `utf8-byte-upper-estimate` fallback when tokenization is unavailable.
- `finished`, meaning that the stream loop ended, including error or interruption;
  it does not imply a successful result or accepted manuscript.

Periodic notification/heartbeat progress includes these fields. A final snapshot
is attempted in stream cleanup. Forced process termination can prevent final
delivery; the controller retains the latest snapshot it actually received.
Explicitly identified foreign-thread/turn events do not enter output measurements.
Worker-wide notification counters retain their earlier cumulative meaning.

Controller intake requires exactly the allowed measurement fields, matches the
current allocation span and started model identities, rejects negative/non-finite
or inconsistent values, and rejects counter regression or reopening a finished
stream. It preserves one latest snapshot per span, capped at the last 100 turns
per logical worker. Older protocol workers without measurements remain supported.
No delta content, raw exception message or arbitrary runtime payload is stored in
these measurements. Estimates are not converted into actual token usage.

The existing inclusive 250,000-character delta bound remains unchanged, using the
incremental count from the preceding phase. Completed-message size is observable
but this follow-up does not impose a new model output/reasoning/time bound.

## Verification

Controlled tests cover fresh repair for draft and revision, original-return and
packet tampering, response inventory changes, wrong operation and repeat denial;
Unicode byte/character accounting, counter reset, success/error terminal snapshots;
allocation/turn binding, invalid fields and values, counter regression and legacy
progress; controller payload preservation and correction usage missing from the
shared ledger. Full manuscript-quality and research-transport regressions are also
run. **168 distinct focused cases were verified across the broad run and targeted
reruns**, including 28 new cases in this phase. The initial broad run passed 167
cases and failed the new usage-removal simulation described below. After correcting
that simulation, all 30 selected correction/measurement cases passed. All 60 worker
cases were then rerun against the final code and passed. The entire 168-case command
was not repeated after the test-only correction.

Ruff F/I checks passed for the three changed implementation files and three test/
fixture files. `git diff --check` passed. Git status and diff statistics were reviewed;
their broader existing changes are not attributed to this phase. Implementation
changes are confined to the author payload, Codex worker and controller progress
intake, with focused tests/fixture and production/audit documentation.

One initial new test failed because its simulated usage removal changed only the
accounting copy while leaving the actual event marked as `actual`. The simulation
was corrected to remove usage from the event delivered to the controller. The
targeted rerun passed and confirms that missing usage remains fully charged.

## Reviewable next acceptance

Offline preparation is complete once the checks below pass. Another live run
requires fresh explicit one-attempt/model/token/time authorization; the previous
attempt is consumed. A proposed comparison keeps **gpt-5.6-sol / low**, **240,000
tokens / 900 seconds including setup**, no automatic retry, approved host launch
and a new temporary output folder. This changes author correction context and
adds observation, while keeping the model, effort, length, evidence and review
gates fixed. The performance fix is another acknowledged implementation difference;
this would not be a rigorously isolated causal experiment.

Inspect per-turn stream sizes/times if the correction stalls. Do not claim that a
deadline stop identifies server latency or lengthy reasoning. On success require
an admitted 900–1,200-word draft, all four independent role reports, mandatory
adversarial review, revision/response clearance as needed and final handoff.
Report diagnostic acceptance, agent checks, human approval and release eligibility
separately; bibliography placeholders remain release blockers. Verify shutdown,
budget accounting, frozen source/pilot integrity and implementation hashes.

Continue in this chat because the exact saved evidence, implementation and approval
boundaries remain directly relevant. gpt-6.1-sol / medium is sufficient for orchestration
and review here; no model setting has been changed. The proposed live worker retains
its existing setting to make comparison more informative.
