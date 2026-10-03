# Evaluation launch contract and sizing

The launch-contract phase freezes a production design and a conditional budget
proposal; it does not authorize or enable execution. The authoritative runtime is
still mock-only. The proposal is custodian material and must not enter participant
context. GPT-6 Astra/high is the selected model adjudicator. Participant selection
remains open, so the cost proposal conditionally prices both arms at Astra rates.

## Input fit and polling fixes

Hash-only admission and serialization checks confirm the allowed manuscript is
97,170 bytes, but its encoded read result occupies 101,363 bytes. The previous
100,000-byte maximum made a complete read impossible even with a raised preset.
`ResponsesContract` now permits an explicitly selected tool-result bound up to
200,000 bytes. The existing default remains 32,000; the proposed pilot profile uses
128,000 and a 500,000-byte context ceiling. No source text or later answer material
was copied into tests. A synthetic escape-heavy fixture covers the size regression.

`poll_interval_seconds` now accepts integer values from zero to 30. Zero preserves
existing fast offline tests. The proposal uses ten seconds and at most 20 polls.
The wait is interruptible by cancellation and bounded by the remaining attempt
deadline. Exhaustion still attempts the separately bounded cancellation operation.
In this implementation, `request_seconds` bounds the complete count/create/poll
attempt, not each individual HTTP request. The proposal uses 300 seconds per
attempt, 1,800 per arm and five for cancellation, with bounded process cleanup.

## Proposed resource envelope

The proposed ceiling is **$75 total**: $30 per arm and $15 for model adjudication.
This is a ceiling for a future matched-pair diagnostic, not an expected invoice or
permission to spend. Both arms receive identical ceilings. Each arm gets at most
12 generations, 600,000 aggregate input-plus-output tokens, 32,768 output tokens
per generation, 50 broker calls and 30 minutes. One quarter of arm dollars and
tokens is protected for verification. The role controller must also protect four
of the 12 generations for review/verification; that aggregate role controller is
not implemented by the single-run transport alone.

The adjudication allocation proposes at most four generations, 300,000 aggregate
tokens, 16,384 output tokens per generation and 15 minutes. A hard stop preserves
incomplete work; these caps do not promise completion or establish scientific merit.

The [official Astra model page](https://developers.openai.com/api/docs/models/gpt-6-astra),
checked 2026-10-03, supports high reasoning and reports standard pricing and the
long-context multiplier. The conservative calculation uses $47 per million input
tokens by summing long-context input/cache categories, and $75 per million output
tokens. This deliberately overestimates token charges and is not an advertised rate.

The illustrative planning envelope is 352,000 input and 128,000 output tokens per
arm, plus 192,000 input and 64,000 output tokens for adjudication: **$66.112** in
conservative token accounting. Up to 616 count/poll/cancel operations at a
**hypothetical, unverified** one-cent upper fee add $6.16, giving **$72.272**. The
remaining $2.728 is headroom within $75. The one-cent value is a proposed admissible
fee ceiling, not a claim about provider pricing; launch is blocked until evidence
supports an applicable fee bound. Actual token counts and durable reservations
control dispatch. Planning quantities do not independently authorize their use.

The [token-counting guide](https://developers.openai.com/api/docs/guides/token-counting)
supports counting the exact request structure; the inspected material does not
establish that auxiliary operations are free. Account pricing and model access
remain unverified. The [background guide](https://developers.openai.com/api/docs/guides/background)
describes temporary response retention for roughly ten minutes, including with
`store=false`; this retention proposal still needs acceptance.

## Production boundary and readiness

The frozen design specifies HTTPS to `api.openai.com:443`, exact Responses routes,
strict hostname validation with a pinned trust bundle, no redirects/proxy inheritance,
zero retries, a relay pinned to a custodian-resolved public endpoint, and no direct
worker/gateway TCP network. The worker receives no credential or custodian mount.
The credential source remains unset and may not be discovered from environment,
shell profiles, caches or default stores. DNS/address and certificate verification
must precede any credentialed request and be recorded in a launch attestation.

The existing 63-check synthetic HTTPS result supports this pattern; it does not
certify the public deployment. Changes to source/configuration require matching
attestation. Production transport selection remains absent.

The full historical E1 protocol also requires fresh workflow reviewers, revision
verification, paired-arm budget aggregation and candidate/export handling. Those
are not supplied by one `ResponsesEvaluation` instance. Python/TeX execution is
not available in the current tool broker, so computational reproduction and PDF
layout remain unassessed unless separately implemented and qualified. The budget
proposal must not be mistaken for completed orchestration or an executable pilot.

The user's Astra adjudicator choice supersedes the earlier request to name a human
for this model-led diagnostic. Its judgments must be labeled model-adjudicated;
this does not turn the existing reference drafts into human gold labels or imply
external peer review. No mathematical adjudication has run in this phase.

Concrete configuration, budget arithmetic, input-fit evidence, current readiness
blockers and hashes are saved under the preparation workspace's
`working/scoped-implementation-2026-10-02/launch-contract-phase`.
