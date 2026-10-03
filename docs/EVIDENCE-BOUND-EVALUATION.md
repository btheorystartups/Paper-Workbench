# Manuscript evidence binding and offline evaluation

Publication approval now records a versioned dependency snapshot for one manuscript.
The offline diagnostic services provide a restricted two-input tool interface, revision
records and a separate attempt ledger. These changes do not enable a live evaluation.
No provider adapter, automatic mathematical verifier or publication action is added.

## Approval and manuscript scope

`services/evidence_basis.py` collects manuscript sections, their claims, live claim
evidence, complete excerpts and source records, supporting result bodies, and explicitly
linked dependencies. It follows outgoing `depends_on`, `derives_from` and `cites` edges,
and incoming `supports`, `contradicts` and `part_of` edges. Both edge direction and role
are frozen. References to another manuscript are rejected; shared work should be an
explicit result or other evidence object.

Body reference fields are `claim_ids`, `source_ids`, `excerpt_ids`, `artifact_ids`,
`required_check_ids`, `dependency_ids`, `included_object_ids`, `from_candidate_id`,
`section_order`, `dataset_id`, `compute_run_id` and `research_task_id`. Notes and artifacts
with the current `manuscript_id` are also dependencies. A referenced research task is
versioned as a whole, including its source text, reports, reviews and provenance.
Referenced compute runs retain their plans, output descriptors and review state.
Content-addressed artifact descriptors are read and checksum-verified. Legacy source
and figure paths without descriptors require reingestion before approval.

Attach figures and tables through `artifact_ids`, a paper candidate's
`included_object_ids`, an explicit dependency edge, or their `manuscript_id`. Unlinked
project figures are no longer automatically exported. Their project inventory and
project audit remain available. Required check objects must record
`verification_status: passed` and nonempty `verification_evidence`; this is an assessment
record, not an automatic assertion that the science is correct.

The policy version is part of the approval basis. Bump `POLICY_VERSION` when changing
dependency or assessment rules. Earlier packages lack this basis and therefore become
stale; their historical approval, notes and snapshot remain stored. Create and approve
a new package version to use the new policy. No database migration is needed.

Readiness is false when approval is stale. Export manifests include the input evidence
hash and file checksums. Package assembly checks them, includes the frozen approval
snapshot and declared supplements, and rechecks dependencies after export and artifact
capture. These checks trust the local renderer and application code; they are not
cryptographic attestation of an untrusted exporter. Concurrent changes after the final
check cannot rewrite the captured bytes; a later readiness check detects their staleness.

The manuscript-path JSON and download endpoints accept `?manuscript_id=...`. With it,
research tasks, claims, checks and packages are scoped to that manuscript. Without it,
the response is explicitly a project inventory and cannot claim publication readiness.

## Review and evidence assessment

`services/revision_review.py` provides trusted service functions for opening a review
round, recording author responses and appending independent verification dispositions.
Each round has comments and acceptance criteria. Verification binds the response,
comment and candidate hashes, records evidence and regression assessment, and requires
a verifier identity different from the responding author. An author response cannot
close an objection. Candidate or criterion changes reopen a prior disposition.
Unresolved round comments block package approval. Alternative repairs and justified
rejections are allowed when the recorded criterion and regression assessments pass.

Caller-supplied assessments and identities require a trusted custodian. No new public
review endpoint is exposed. This service does not authenticate professional expertise
or determine whether a mathematical argument is valid. Existing generic skeptical
notes are frozen as evidence but are not automatically converted to verified rounds.

Approving a research finding for proof use no longer sets `formally_established`.
Promotion records use approval and scoped proof assessment separately, with finite and
formal verification explicitly unestablished by that approval. Existing historical
objects are preserved; this change does not relabel them in place.

## Offline diagnostic boundary

`services/evaluation.py` accepts exactly two byte streams with expected hashes, under
`inputs/manuscript.tex` and `inputs/historical_verification_record.txt`. The custodian
must supply a neutral brief and approved input bytes. This interface cannot discover
host files, import project retrieval, fetch URLs, run a shell or resume a conversation.
Read and retrieval tools search only those two byte streams. Caches and conversations
are fresh per run. Denied tool arguments and hidden contents are omitted from logs.
Tool calls and output sizes are bounded. Freezing seals further tool use and produces
hashes of inputs, outputs and trace. Exclusive capture rejects overwrites, traversal,
symlink and Windows junction ancestors and changed output bytes.

The broker is a data-only service boundary, not an in-process sandbox for arbitrary
Python or a capability-safe object that can be handed to untrusted code. Only structured
tool requests may cross it. The custodian is responsible for keeping the brief and
admitted bytes free of privileged answers. Content hashes prove identity, not historical
authenticity, correctness or absence of answer leakage.

`container_command` constructs an offline runtime command with a digest-pinned image,
no image pulls, no network, read-only input and root filesystem, nonroot execution,
dropped capabilities and resource limits. Only the staged two inputs plus an
operator-reviewed `runner.py`, and a fresh output directory, are mounted. It validates
mount paths and rejects links and undeclared input files. It does not launch a process.
An operator harness must freeze and recheck staged bytes, bound wall time and logs,
capture outputs and kill an interrupted container. Never mount the workspace, project
database, credential directories, host Docker socket or custodian packet.

## Accounting and remaining live prerequisites

`AttemptLedger` uses its own explicitly created SQLite file and immediate transactions.
Reservations precede dispatch, concurrent attempts share a ceiling, and caller database
rollback cannot erase reservations. Attempt IDs and request hashes cannot be reused.
Timeouts with uncertain charges retain the full reservation and block further attempts
until reconciliation. Above-reservation reports also stop further work. Costs are
integer units chosen by the operator; a request hash must include its logical request
identity. Store this ledger outside participant mounts.

### Scripted provider adapter

`services/evaluation_adapter.py` now connects the broker and durable ledger through a
supervised, fake-only adapter. `providers/evaluation_fake.py` accepts JSON fixtures and
returns scripted replies; it never imports a provider SDK, selects from the provider
registry, reads credentials or contacts a network. Ambient live-provider settings cannot
activate it. These fixtures exercise engineering behavior and do not simulate the
quality or accounting behavior of a real model.

Create `EvaluationAdapter` with a new output directory, the two admitted byte streams
and expected hashes, a neutral brief, an `AdapterContract`, and scripted frames. The
contract requires explicit cost and token ceilings and protected verification reserves.
It also sets turn, tool-call, input, output, tool-result and wall-time limits. This
adapter uses one canonical JSON byte as a **synthetic token unit**, with fixed synthetic
integer input/output rates. These units are neither actual model tokens nor money.

Each `step(phase="work")` reserves the full input allowance and maximum output in both
token and cost units, durably records dispatch, then calls the fake transport. A valid
reply has `text`, `final` and `tool_calls`; each tool call has `name` and `arguments`.
Replies and usage are validated before usage and a sanitized response receipt are
committed together. Only then can tool requests reach the two-input broker. No proposed
application action, project retrieval or arbitrary callback is executed.

`step(phase="verification")` is an operator decision, never a participant tool. Work
cannot consume the protected cost/token reserve or the final remaining turn. A work
budget denial leaves verification available. Overall budget, tool and time limits still
apply. The wall-time check surrounds the fixed, nonblocking fake transport; it is not
a timeout mechanism for a future blocking SDK. Such a transport remains unavailable.

Timeouts, interruption, incomplete usage, malformed replies and uncertain persistence
stop the run. Reservations remain charged against available capacity until explicit
reconciliation. There is no automatic retry or continuation. Bound ledgers permit only
one unresolved dispatch at a time. Caller database rollback cannot erase an attempt.
Attempt IDs, request hashes and the run binding prevent duplicate dispatch or reuse
under another context. Changes to the frozen binding or ledger limits prevent dispatch.
Status events retain reservation, dispatch, uncertainty and settlement history.

`cancel()` stops before further work. `finish()` freezes complete or partial transcripts,
accounting, the run binding, tool-trace hashes and an outcome into exclusive capture
files. Pending or uncertain attempts remain explicitly uncertain in that outcome.
An interrupted run directory cannot be reused to start a new adapter. Inspect and
reconcile its ledger without redispatching. The adapter never automatically resumes an
interrupted conversation. A `completed` outcome means that the scripted exchange ended;
scientific assessment is explicitly `not_performed`, and `live_ready` is always false.

The new dedicated ledger format is version 2. Older dedicated ledgers are rejected
without alteration; they are not silently migrated or reset. This has no effect on
the application database schema. The adapter's ceilings are per run, not account-wide:
starting another directory is another operator action and must not be used to evade
an approved total budget. Custodians must keep fixtures, ledgers and run captures outside
any future participant filesystem.

The fake adapter does not change the existing live research runner or usage service.
Before live execution, a concrete live transport must supply enforceable real token/cost
bounds, durable provider request identity, authoritative usage reconciliation and bounded
cancellation. The scripted adapter is not evidence that an existing provider supports
those guarantees. Freeze the approved model, numeric resource ceilings, neutral brief,
runtime and input hashes, and validate the actual transport's access boundary. A
synthetic container smoke test cannot attest a future model process or connector.

Live calls, unattended recovery, a blind participant run, deployment and publication
remain outside this implementation. The mathematical adjudicator choice remains
GPT-6 Astra at high reasoning; no such separate call was made by these services.

## Verification

Run the focused evidence, evaluation, publication-package, authoring/export, figure,
manuscript-path, research API and proof-promotion tests with fake providers. Configure
`WB_LOAD_DOTENV=false`, disable bytecode and local/live executors, and set new synthetic
database and storage paths before importing application modules. Tests needing an API
schema should create tables only in that synthetic database. Never use a real database
or apply migrations as part of this verification.

Coverage includes relevant and unrelated dependency mutations, source-byte corruption,
policy changes, export races and artifact substitution, historical approval preservation,
ineffective and alternative repairs, regressions, hidden-input denials, independent
namespaces, output substitution, concurrency, uncertain charges and caller rollback.
Container canaries separately cover admitted reads, hidden paths, symlinks, read-only
mounts, root writes, host environment, nonroot identity and network denial. Host symlink
creation may require privileges; Windows junction coverage is a separate test.

`tests/test_evaluation_adapter.py` additionally checks fake-provider tool round trips,
reservation-before-dispatch ordering, cost and token ceilings, protected verification,
hard process exit, duplicate-dispatch denial, usage/persistence faults, caller rollback,
fresh conversation boundaries, neutral denial logs, contract substitution, cancellation,
resource limits and capture hashes. All adapter fixtures are synthetic. No live model
or manuscript assessment is performed by this suite.
