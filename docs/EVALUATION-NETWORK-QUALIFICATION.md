# Synthetic HTTPS runtime qualification

The 2026-10-03 qualification composes the existing Responses supervisor, budgeted
gateway, actual OpenAI SDK 2.46.0, persistent custodian storage and a synthetic
HTTPS upstream in one isolated Docker deployment. All 63 final checks passed.
This establishes the tested synthetic boundary. It does not enable live provider
execution or establish account access, billing applicability or scientific validity.

## Tested layout

The participant and gateway containers both use `network=none`. The participant
can reach only the gateway's Unix socket. Its mounts contain its test program,
admitted synthetic input and its own result directory. The gateway alone receives
the custodian ledger/capture directory and credential fixture; it also receives
the public test certificates and a separate read-only egress socket mount.

The gateway's owned SDK process sends HTTPS through that Unix socket. A bounded
relay connects to one fixed IP and port belonging to the synthetic upstream
container. The caller cannot supply a relay destination. Relay and upstream share
a Docker internal network with external DNS resolution disabled. No host ports
are published. All four roles run non-root, with read-only roots, dropped
capabilities, no-new-privileges and process/memory/CPU bounds.

The image is built offline from 16 version-pinned Linux wheels downloaded from
public PyPI. Installation requires their SHA-256 hashes and passes `pip check`.
The base is the previously cached official Python 3.13.15 image. The receipt binds
the resulting image ID, dependency hashes, six application module hashes, executed
harness hashes, certificate fingerprint and inspected mounts/network state.
The wheel download is the only public package retrieval in this phase; provider
tests use no public endpoint, real account credential or original manuscript.

## Results

The final run passed 28 participant checks, 26 gateway/accounting checks, three
relay network checks and six upstream/capture assertions. Eleven scenarios cover
completion, cancellation, redirects, an untrusted certificate, a wrong hostname,
timeout, disconnect, malformed count, wrong returned model, mismatched usage and
a provider error containing the synthetic credential marker.

The upstream observed exactly 15 HTTP requests. Redirects were not followed, and
no retry occurred. Certificate/hostname rejection happened before an HTTP request
reached the server. Each observed request had a distinct client identity and the
expected authentication marker. Poisoned proxy environment variables did not
divert successful SDK requests. Direct gateway access to the actual upstream IP
failed, while its approved Unix-socket route succeeded.

Completed and cancelled runs settled the expected conservative amounts. Failed
exchanges retained their reservations and stopped. The participant could not read
the credential file, egress socket or custodian ledger, including after that ledger
was created. Captured JSON and participant replies contained no credential marker.
Caller-supplied URLs, paths and headers were denied before execution.

The containers, both socket volumes and the internal network were removed after
the run. The local test image, pinned wheel bundle, synthetic certificates and
private test evidence are retained for reproducibility. The certificates expire
after one day; the reproduction helper creates fresh test certificates each run.

## Qualification limits

This harness supplies a test-only HTTPS worker through the supervisor's transport
seam. It reuses the installed parent process protocol, gateway, accounting and
response validation. The normal application still constructs only its fixed mock
worker. No live setting, production endpoint selector or credential loader was
installed. The test seam must not be treated as a production launch path.

The relay is fixed to a private fixture endpoint on an internal network. Public
OpenAI routing, certificate trust, address changes and account/model access are not
tested. Nor does this test establish host power-loss durability, protect against
a privileged host administrator or authorize automatic recovery. Earlier crash
checks remain evidence for process/container-exit persistence and denied redispatch.

This phase made no application runtime changes. The prior authoritative result of
125 passed and one Windows symlink-permission skip was not rerun; all six runtime
module hashes used here match that verified implementation. Ruff passed for the
six executable qualification harness files. These runtime checks are additional
evidence, not replacements for mathematical adjudication or the pilot's hard gates.

## Remaining launch requirements

Freeze a separately reviewed production transport/relay configuration and bind it
to the existing execution contract. Establish account-applicable token and
auxiliary-operation pricing, model availability and real count/usage compatibility.
Participant model selection, experiment ceilings and retention acceptance remain
open. GPT-6 Astra/high remains the user-selected mathematical adjudicator.

Then obtain the still-missing credential-access, live-execution and spending
authorization for that exact configuration. The synthetic test result and scoped
implementation approval provide none of those permissions.

Evidence is in the preparation workspace under
`working/scoped-implementation-2026-10-02/network-runtime-phase`, including the final
readiness receipt, image/dependency manifest, run receipts and proposal version 6.
