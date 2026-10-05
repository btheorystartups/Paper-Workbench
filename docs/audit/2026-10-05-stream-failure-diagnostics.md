# Offline stream failure diagnostics

## Scope and implementation

Continues the authorized offline follow-up to the proof worker's generic
`ValueError` during streaming. No new live run or model call is included. Existing
dirty work and frozen acceptance/pilot artifacts remain unchanged.

Seven explicit failure branches now raise `WorkerStreamError` with a fixed code:

| Code | Worker condition |
| --- | --- |
| authentication_changed | Authentication update no longer indicates ChatGPT |
| model_rerouted | Model rerouting notification |
| runtime_error | Runtime error notification |
| unsupported_item | Started item outside the research worker's permitted types |
| invalid_message_delta | Message delta is not text |
| response_text_bound | Accumulated response exceeds the existing text bound |
| turn_incomplete | Completed-turn notification reports an unsuccessful status |

The worker's error envelope includes only the fixed code and exception class in
addition to its existing stage/RPC metadata. Exception messages, arbitrary tool
names and provider error payloads are not serialized. Other exception types retain
their existing class/stage reporting; transport and parsing errors are not guessed
into a stream reason code.

The shared allowlist lives in `research_contract.py`. The controller accepts codes
only at `turn_stream`, saves `worker_failure_code` in agent provenance and emits a
`worker_failed` trace event bound to the original operation span, agent and stack.
Unknown codes and non-string values are discarded. Existing snapshots and packages
carry the provenance and trace through their existing export paths.

The failure still stops the workflow. The stream is interrupted during cleanup,
the worker entrypoint closes, and the original task budget/deadline remain binding.
No model rerouting, retry, new tool permission or publication clearance is introduced.

## Verification

**40 distinct focused tests passed**: all 33 Codex worker tests, two research
transport tests, four existing author/length-correction cases, and one new controlled
process failure case. Nineteen new cases cover each explicit stream branch, sanitized
entrypoint emission and cleanup, controller allowlisting (including unknown and
non-string codes), stage binding, and saved provenance/trace retention. A private
sentinel message was excluded from both persisted provenance and the task ledger.
Python F/I lint and Git diff checks passed.

The initial process regression exposed only a test assumption: an early failure
can leave the handoff field absent rather than false. The assertion now treats
absence as no handoff, and its rerun passed. Failure-code persistence and privacy
assertions passed before that correction as well.

All tests use controlled events/processes and synthetic temporary storage. No paid
service, manuscript agent, default database, credential store, original manuscript,
commit, push or deployment was involved.

## Limits and next step

This patch cannot retrospectively recover the cause of the preceding live failure.
It will distinguish the seven branches if a future failure reaches them. A
`runtime_error` code identifies a runtime notification, not its underlying provider
cause; raw provider details remain excluded. It does not establish that a stronger
model or higher effort would help.

The next useful verification is one comparable live attempt, after fresh explicit
token/time authorization. Continue in this chat because the same evidence and patch
remain relevant; retain gpt-5.6-sol / low for that comparison. Do not increase the
ceiling or reasoning effort solely because the earlier generic failure was unresolved.
