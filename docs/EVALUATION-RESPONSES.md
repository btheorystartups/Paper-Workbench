# Responses evaluation transport

`services.evaluation_responses.ResponsesEvaluation` connects the two-input diagnostic
broker and dedicated reservation ledger to a supervised Responses SDK protocol. The
installed execution mode is **mock only**. It exercises the actual OpenAI Python SDK
2.46.0 using data-only fixtures and `httpx.MockTransport`, in a separate owned process.
No setting or API key can switch this path to a live endpoint. The general chat registry,
research executors and application database are not involved.

The optional `evaluation` dependency pins the reviewed SDK; CI installs that extra.
Missing or mismatched SDK metadata is rejected before a reservation or worker launch.

This is an engineering diagnostic, not a mathematical evaluation. `completed` means a
valid terminal exchange and payload; captures always identify the run as simulated,
scientific assessment as `not_performed`, and `live_ready` as false.

## Contract and request behavior

Construct a `ResponsesContract` with an explicit model, aggregate cost/token ceilings
and protected verification allocations, then pass exactly the two admitted byte strings,
their expected hashes and a neutral brief to `ResponsesEvaluation`. Contract numbers
are synthetic test policy, not recommended real-pilot settings. `step(frames, phase=...)`
takes fixture data under custodian control. Participants cannot supply fixtures, a
client object, executable, filesystem path or provider callback. Tests illustrate the
complete synthetic response shape in `tests/test_evaluation_responses.py`.

The bound request explicitly sets model and high reasoning effort, output allowance,
background mode, `store=false`, default service tier and disabled context truncation.
It sends no conversation or previous-response reference and enables no native tools.
A structured JSON reply can request the existing broker's read, retrieve, cache and
conversation operations. Unknown requests receive generic denials. Tool arguments are
not copied into the subsequent conversation, response receipt or transport journal.

The SDK has retries disabled. Each HTTP operation has its own client request ID; the
local attempt, provider response ID and HTTP request ID are distinct. The supervisor
checks the observed method, endpoint path, serialized body hash, retry count, operation
identity and SDK version. A returned model or policy mismatch stops the run.

## Durability and failure behavior

1. Reserve cost and tokens in the dedicated SQLite ledger before spawning the worker.
2. Commit dispatch, then journal the intended HTTP operation before sending it.
3. Write and flush receipt identity before polling. Each exclusive journal file links
   to the previous record's hash. Source hashes bind the reviewed transport and broker.
4. Accept only consistent final usage within the reservation. Synthetic conservative
   accounting charges all input tokens at the input rate and output tokens at the
   output rate, without assuming a cache discount or counting reasoning twice.
5. Settle known usage and a sanitized output receipt before executing broker requests.
   Incomplete/failed/cancelled responses can settle known usage but cannot invoke tools.
   Invalid scientific output can also settle known usage without becoming a valid result.

An uncertain call keeps its full reservation. Missing usage is never measured zero.
There is no automatic generation retry, resume, reassignment or migration. Reopening
the dedicated ledger for inspection does not authorize another dispatch. A hard
custodian exit leaves a pending/dispatched attempt and any acknowledged response ID
available for later reconciliation. A crash can precede final capture; the ledger and
exclusive event files remain the recovery evidence.

`cancel()` signals without waiting for the step lock. The parent bounds worker reads
and writes and terminates its process on interruption/deadline. Poll exhaustion or a
cancellation observed between successful replies attempts a separately bounded remote
cancellation operation. A blocked or lost operation can prevent that cancellation
exchange; the run then remains uncertain. Local termination never proves remote work
stopped. Process shutdown has a bounded additional grace period (up to two terminate
seconds, two kill/wait seconds and one reader-join second).

`finish()` freezes transcript, accounting, transport events, binding and outcome under
the existing exclusive capture policy. Runtime, contract, ledger-limit or journal
mutation is rejected. Replay of a response ID from an earlier attempt is rejected.
Raw malformed responses and denied tool arguments are retained only as hashes, not
participant-visible text or raw diagnostic logs.

## Isolation and limits

The worker receives synthetic fixtures and the current admitted request through pipes.
It uses a fresh temporary working directory and an environment allowlist. SDK auth is
the fixed literal `offline-placeholder`; proxy inheritance is disabled and socket
connection/DNS entry points are blocked. The executable and worker file are selected
by application code. The worker cannot load arbitrary plugins from fixture values.

This owned-process boundary is **not an OS filesystem sandbox**. It is suitable for the
fixed trusted mock worker, not for arbitrary participant code or a credentialed live
worker. No live image, endpoint-only egress proxy or credential mount is installed here.
The earlier network-disabled Docker canaries do not attest this different runtime.

The contract's `input_token_allowance` and rate schedule are explicit **synthetic**
assumptions. The service does not claim that text bytes bound real billable input tokens
or that these rates reflect actual pricing. A credentialed runtime needs a defensible
input bound, complete conservative tariff, model access verification, response-usage
compatibility checks and approved real ceilings before it can reserve real spending.

## Source references and remaining live gate

The [Responses reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create)
documents output limits including reasoning and response usage/status. The
[structured output guide](https://developers.openai.com/api/docs/guides/structured-outputs)
describes JSON schema formatting; local validation remains mandatory.
The [cancellation reference](https://developers.openai.com/api/reference/python/resources/responses/methods/cancel)
limits cancellation to background responses. The
[background guide](https://developers.openai.com/api/docs/guides/background) describes
temporary retention and polling. These documents are not account-specific guarantees.

Keep execution disabled until the reviewed live deployment provides an attested
filesystem/egress/credential boundary, real resource accounting, a frozen participant
model/brief/input manifest, and explicit execution/spending authorization. Do not remove
the mock-only check as a shortcut. Use a separately reviewed live construction path.

## Priced gateway integration

An explicit `tariff` now selects the mock-count/USD policy within this supervisor.
See `EVALUATION-PRICED-SUPERVISOR.md` for units, durable count/generation sequencing,
persistent custodian-storage canaries and the remaining live runtime gate. The
synthetic-rate limitations above describe the default path without a tariff.
No execution mode has been added beyond SDK mocks.
