# Priced Responses supervisor — offline qualification

`ResponsesEvaluation(..., tariff=Tariff(...))` now composes the existing diagnostic
broker, owned SDK process, response validation and capture flow with the budgeted
gateway. The execution mode remains **mock only**. No live client, credential
discovery, external network path or paid-run entrypoint was added.

Without `tariff`, existing synthetic-cost behavior is preserved. With `tariff`,
the contract's cost ceiling and protected cost reserve use integer nanodollars;
token limits remain tokens. The tariff and unit are recorded in the frozen binding
and bound to the dedicated ledger. Synthetic `input_token_allowance`, `input_rate`
and `output_rate` no longer price this path. The model must match the tariff.
Fixtures and all count/usage observations remain explicitly synthetic.

## Dispatch and settlement

The fixed SDK worker now supports the Responses input-token count operation. It
uses the actual pinned OpenAI SDK with `MockTransport`, no retries, no inherited
proxy and blocked socket connections. The supervisor verifies the observed HTTP
method/path/body hash and unique client identity for counting as it already does
for creation, retrieval and cancellation.

The sequence is:

1. Create an exclusive run directory and freeze its contract, tariff, admitted
   inputs, system/schema and runtime source hashes.
2. Start the fixed offline process. Reserve and commit the count attempt before
   passing the count request to it; flush the intent journal before exchange.
3. Record the count response identity/hash. Verify and settle the count upper fee.
4. Reserve and commit generation against that exact count before create. If the
   protected budget cannot accommodate generation, no create request is sent.
5. Apply existing model/policy/status checks and response ownership rules to every
   generation exchange. Reserve space for counting, creation, bounded polls and a
   cancellation operation within the gateway's operation ceiling.
6. Settle verified terminal usage, record the sanitized receipt, then permit the
   diagnostic broker to handle valid tool requests. Malformed output can settle
   known usage without invoking tools. Unknown usage retains its reservation.

Count and generation are distinct ledger attempts. On an interrupted count, the
supervisor marks the count attempt itself uncertain. It does not attempt to settle
a generation that has not been reserved. A settled count fee is not refunded when
generation cannot proceed. Each later turn uses a fresh count and shares the same
aggregate ledger and protected verification allocation.

The run directory is exclusive: restarting against it does not resume or redispatch
work. Ledger reopening supports inspection. Pending/dispatched/uncertain attempts
block a new reservation until a separately reviewed reconciliation resolves them.
Local process termination does not prove any remote computation stopped.

## Persistent custodian boundary

The preparation workspace's `supervisor-gateway-phase/container_probe.py` extends
the prior two-container canary. Only the gateway receives `/custodian`, a persistent
host-backed directory for its synthetic ledger and evidence. The worker receives
its own output directory and cannot read the custodian ledger or journal. The
credential remains a dummy fixture mounted only in the gateway.

A separate gateway process commits a synthetic count reservation, flushes an intent
record and exits abruptly with code 17. A fresh container reopens the same storage:
both records survive, a new attempt is denied, and the ledger still contains only
the original attempt. Test containers/volume are removed; persistent test evidence
is retained in the preparation workspace.

This establishes process/container-exit persistence and worker mount separation for
the tested layout. It does not establish host power-loss durability, protect against
a privileged host user, or qualify automatic recovery. The containers have network
disabled. The pinned SDK runs in a separate host-side integration test; the container
canary uses a loopback mock server and the same gateway/accounting code. These are
complementary layer checks, not an attestation of one credentialed runtime image.

## Failure coverage and remaining launch gate

Integration tests exercise count/create timeouts and exits, redirects carrying an
external Location, malformed responses, missing count HTTP identity, incorrect
model/policy/response ID, inconsistent count and usage, budget exhaustion before
create, polling/cancellation, invalid scientific output, journal mutation, and
valid tool requests only after settlement. Runtime hashes now include the gateway
and pricing modules as well as the existing protocol/broker modules.

Before live use, qualify one complete runtime with endpoint-only external egress,
TLS/redirect/DNS/proxy behavior and credential injection. Network-disabled mock
tests cannot establish those properties. Recheck the full image/source/mount
configuration, upstream response policy and deadlines together. Establish
account-applicable pricing and auxiliary fee bounds, model access, real count/usage
compatibility, participant selection and aggregate experiment ceilings. Then freeze
the proposal and obtain explicit credential, execution, retention and spending
authorization. Astra/high remains the selected mathematical adjudicator; participant
selection is still pending.

No mathematical findings were produced by these synthetic checks. They establish
infrastructure behavior only. See `EVALUATION-RUNTIME-BUDGET.md` for the conservative
rate formula and `EVALUATION-RESPONSES.md` for protocol/capture semantics.
