# Four-role acceptance: authorized attempt stopped during preflight

The user authorized one attempt at 240,000 tokens and 900 seconds including
setup, with no automatic retry. The prepared harness was invoked once on October
4, 2026, using new synthetic temporary storage and the existing subscription
runtime (`gpt-5.6-sol` / low).

The attempt started at 15:48:01.151489 UTC. The initial Codex app-server
`initialize` RPC failed at 15:48:03.678362 UTC with `CodexLocalError:
codex_local transport closed`. The handshake lasted 0.211553 seconds.

No model turn was requested, no manuscript agent was created, and no task or
synthetic database was created. The harness closed the worker in its existing
`finally` block. No second acceptance attempt or model call was made.

A subsequent non-model `--version` probe succeeded with `codex-cli 0.154.0`.
The binary is available; the app-server startup failure's root cause is not
established. The existing stdio transport discards runtime stderr, so the saved
trace contains the failed RPC and controlled exception but no runtime diagnostic.
Do not attribute this failure to the new adversarial review or claim live
verification of that workflow.

Evidence folder:
`C:\Users\brian\AppData\Local\Temp\paper-workbench-adversarial-acceptance-agli12ah`.
It contains the prepared plan, checksummed frozen inputs, implementation manifest,
attempt-started receipt, preflight call trace and attempt-finished receipt.

No default database, secrets, original manuscript, PoP checkout or frozen pilot
was edited. No commit, push or deployment occurred. The earlier synthetic test
results remain valid; the four-role workflow's live acceptance is still unverified.

Next: diagnose app-server startup while preserving the no-retry boundary. A new
live acceptance attempt requires fresh authorization after startup is resolved.

Follow-up: the [startup diagnosis](2026-10-04-codex-startup-diagnosis.md) confirmed
filesystem sandbox denial. The existing profile initializes successfully with
approved host execution; no runtime-code fix or acceptance retry was performed.
