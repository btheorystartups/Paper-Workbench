# Evaluation gateway and USD accounting qualification

This phase adds data-only gateway and pricing policy. It does not add a live HTTP
client, credential loader, application setting, or live execution entrypoint. The
Responses SDK transport remains mock-only. This is infrastructure qualification,
not a mathematical evaluation or an approved spending plan.

## Accounting contract

`services.evaluation_costs` represents USD amounts as integer nanodollars, with
exact decimal-string conversion. A dedicated `AttemptLedger` uses those units for
both the total ceiling and protected verification allocation. Do not reuse the
earlier synthetic-cost ledger. `providers.evaluation_gateway.usd_binding` binds the
unit, full tariff evidence and frozen run hash; `BudgetedGateway` rejects a mismatch.
Reuse that ledger across attempts in the same budget; creating a new ledger does
not replenish an approved budget. An eventual multi-arm runner must also enforce
the experiment-wide ceiling.

`InputCount` binds the provider count and its client/HTTP identities to both the
exact generation request and its count projection. The projection includes direct
text input, instructions, reasoning and structured-output schema. Changes to model,
output allowance or any other generation field invalidate the evidence. Remote
files, prior responses, conversations, native tools, automatic truncation and
non-default service tiers are outside the accepted request scope. Returned payloads
are detached from caller-owned mutable data.

The [token-counting guide](https://developers.openai.com/api/docs/guides/token-counting)
explains why visible text alone omits request overhead. The
[count endpoint](https://developers.openai.com/api/reference/python/resources/responses/subresources/input_tokens/methods/count)
returns `response.input_tokens`. These references do not establish a zero price
for counting, polling or cancellation; an operator must supply a defensible upper
fee and evidence for each auxiliary operation before live use.

The conservative reservation is:

    input_count * (input_rate + cached_rate + cache_write_rate)
    + maximum_output_tokens * output_rate
    + maximum_auxiliary_requests * auxiliary_fee_upper

Rates are integer nanodollars per token or operation. Summing all input categories
deliberately overestimates possible overlapping charges; this is not an invoice
calculation. Use upper rates covering the allowed context range and account scope.
Reasoning tokens are already within output usage and are not counted twice.
Terminal input usage must equal the bound count; output must fit its allowance and
the total must equal input plus output. Missing or inconsistent usage retains the
entire reservation and blocks further attempts.

The [published pricing page](https://developers.openai.com/api/docs/pricing), checked
2026-10-03, lists Astra standard long-context rates of $20 input, $2 cached input,
$25 cache write and $75 output per million tokens. The corresponding conservative
input sum is $47 per million, not an advertised billing rate. For 300 counted input
tokens and a 4,000-token output allowance, the token-only upper estimate is $0.3141.
This example excludes auxiliary fees and is neither a selected participant model
nor a budget approval. Account-specific applicability and additional charges remain
unverified. The implementation requires explicit tariff evidence; it contains no
default live prices and does not authenticate supplied evidence.

## Gateway sequencing

`GatewayPermit` is the low-level route/state policy and has no budget authority.
`BudgetedGateway` is the custodian-side accounting composition:

1. Validate the exact request hash, unique operation identity and route shape.
2. Reserve the count fee and commit dispatch before returning its route. A verified
   zero-fee bound still reserves one nanodollar until count completion.
3. Accept a valid count with provider HTTP identity, then settle its upper fee.
4. Reserve generation tokens, output allowance and bounded poll/cancel fees; commit
   dispatch before returning the create route.
5. Allow retrieval/cancellation only for the successfully acknowledged response ID.
   The operation ceiling includes counting, creation, polling and cancellation.
6. Accept terminal usage from the trusted dispatcher and settle the conservative
   upper amount. Close the gateway after settlement or an uncertain exchange.

Calls are serialized. No retry, recovery redispatch, arbitrary URL, headers or
caller-supplied credential is supported. A crash leaves the durable pending or
dispatched reservation, which blocks another attempt. The generation reservation
covers all admitted auxiliary operations, including interrupted ones. Invalid
count evidence or an unsuccessful exchange records uncertainty. Invalid policy
requests that never reach dispatch are denied without incurring a new reservation.

The dispatcher remains responsible for authenticating upstream replies, verifying
terminal status/model/policy, preserving a durable operation journal and applying
deadlines. `settle()` is a trusted custodian API, not a participant capability. These
modules have not yet been composed with the mock Responses supervisor into a live
runner. No count supplied by a participant is acceptable provider evidence.

## Tested container boundary

The preparation workspace's `runtime-budget-phase/container_probe.py` tests the
application policy in two separate containers using cached official Python 3.13.15:

    python@sha256:b6bd71b0dd3811ddbcbc523ec2965fd1e1bcfdf7a20ab24679273d3bee726129

Both run non-root with read-only roots, no network, dropped capabilities,
no-new-privileges, and bounded processes/memory/CPU. The worker sees only admitted
synthetic input, its runner, output and a read-only Unix-socket volume. The gateway
alone sees the dummy credential and injects it into requests to its own loopback
mock server. Actual socket exchanges exercise count/create/retrieve/cancel and
durable accounting. The loopback server checks a dispatched reservation before
each upstream operation.

All 31 checks passed: 22 worker checks and nine gateway/accounting checks. They cover
protected files, hidden paths, credential separation, direct network denial,
request tampering, response ownership, duplicate creation and exact bounded
accounting. Test containers and the shared volume were removed successfully.
An initial combined run exposed an incompatible Python 3.11 image; the final run
uses the project's required Python 3.13 runtime without compatibility patches.

This receipt qualifies the tested local layout only. The gateway itself also has
network disabled; remote TLS, endpoint-only egress, redirects, proxy bypass,
real SDK integration and real credential handling are not qualified. The test
ledger is intentionally temporary and does not qualify durable container recovery.
The shared output mount is test evidence, not a tamper-resistant custodian archive.

## Remaining launch requirements

- Compose the existing protocol supervisor and this policy behind a reviewed
  gateway; verify the dispatcher and a persistent custodian-only journal/ledger.
- Qualify endpoint-only egress and response filtering against synthetic upstreams,
  including redirect/DNS/proxy failures and interrupted or replayed operations.
- Establish account-applicable tariff/auxiliary fee evidence, model access and
  input-count compatibility. Unknown auxiliary pricing is not zero.
- Resolve the participant selection, aggregate/per-arm dollar and token ceilings,
  deadlines, reserves and temporary provider-retention acceptance. Astra/high is
  the user-selected adjudicator; it is not automatically the participant.
- Freeze the complete execution proposal, then obtain the remaining explicit
  credential-access, live-execution and spending authorization.

Scoped implementation and synthetic tests are authorized. No real credentials,
live model calls, manuscript changes, commits, pushes or deployment occurred here.
