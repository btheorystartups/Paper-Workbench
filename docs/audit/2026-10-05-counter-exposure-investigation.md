# Offline counter exposure and final-schema investigation

## Result

The pinned runtime reproduction identifies a **model/tool-transport incompatibility**,
not a final JSON schema that removes the counter. The bundled 0.154.0 catalog declares
`gpt-5.6-sol` with `tool_mode: code_mode_only`. With the application's existing
restrictions, that runtime advertises the counter inside `functions.exec`, while
warning that Code Mode is unavailable because its host is disabled. Setting the
Code Mode feature to false does not override this model's catalog tool mode.

The application callback accepts a direct `item/tool/call` for the counter. The
advertised model interface instead instructs the model to invoke the counter through
an executor unavailable under these restrictions. Therefore successful registration
does **not** establish an executable, model-visible direct counter capability.

This explains a concrete defect in our capability assumption and is a strong
candidate explanation for the zero counter calls in the acceptance attempts. The
historical authenticated catalog and the model's internal choices were not inspected;
the reproduction cannot prove precisely why each prior model chose not to call it.

## Method and boundaries

Used the installed **openai-codex-cli-bin 0.154.0** executable and actual
`StdioCodexClient`, `runtime_overrides`, `tool_spec` and counter callback against a
fake Responses server bound only to `127.0.0.1`. Every runtime profile, working
directory and store was fresh temporary storage. The test provider requires no
authentication and supplies synthetic responses; no account preflight or model
inference occurs. Its custom endpoint exists only in the fixture, and production
preflight still rejects custom endpoints and catalogs.

Also read the runtime's public bundled model catalog using
`codex debug models --bundled`, which explicitly skips refresh. No authenticated
profile, token file, default database or manuscript agent was used. Official
documentation reads were separate from the wholly local runtime probes.

The [official App Server documentation](https://learn.chatgpt.com/docs/app-server)
defines experimental dynamic tools on thread creation, their client callback flow,
and per-turn final output schemas. The installed binary and its generated schema
determine this investigation's version-specific behavior.

## Observed comparisons

| Controlled case | Model-visible counter | Final schema | Observation |
| --- | --- | --- | --- |
| gpt-5.6-sol, default descriptor | Nested in `functions.exec` description | On/off | Same executor wrapping; host-unavailable warning |
| gpt-5.6-sol, `deferLoading: false` | Same executor wrapping | On/off | No direct function; explicit eager loading alone does not fix it |
| gpt-5.6-sol, boolean Code Mode feature disabled | Same executor wrapping | On | Model tool mode still controls wrapping |
| gpt-5.6-sol, `deferLoading: true` | Thread rejected | On/off | Rejected under the existing disabled-search configuration |
| Isolated synthetic catalog omitting Sol's tool-mode requirement | Direct counter function | On/off | Demonstrates catalog metadata controls this exposure |
| gpt-5.5, unmodified bundled catalog | Direct counter function | On/off | Executable synthetic callback roundtrip; final schema preserved |

The synthetic catalog variant is an experimental control, **not a proposed production
catalog override**. No production settings or model selection changed.

Tools may appear in an `additional_tools` input item rather than the top-level
`tools` field. Looking only at top-level `tools` initially suggested absence; the
complete request showed the executor-wrapped counter. Evidence and tests inspect
both locations, preventing that false absence conclusion.

For the positive roundtrip, the fake endpoint emitted a direct counter call with
one section containing `one two three`. The actual runtime forwarded a bound
`item/tool/call`; the existing worker callback returned **three words** and a
content hash. The runtime included that result in its second outgoing request.
With `outputSchema` enabled, **both** outgoing requests retained the same final
JSON schema, and the synthetic final JSON parsed successfully. This verifies the
local protocol/callback path; it does not verify a live model chooses that path or
the backend's constrained generation behavior.

Forcing a direct call through the Sol runtime also reached the callback in exploratory
probes, despite the counter not being directly advertised. That distinguishes routing
from exposure: callback availability does not mean the model is offered that direct
call. Exploratory custom executor-call variants yielded unsupported-tool output and
no counter callback; they do not establish that every possible executor-call encoding
was exercised. The host-unavailable warning independently establishes the unavailable
execution host in this configuration.

`gpt-5.5`'s offline catalog/transport compatibility is **not** confirmation of its
availability on the authenticated account, manuscript quality or live tool compliance.

## Reviewable follow-up

Recommended bounded implementation, before another acceptance attempt:

1. Add a compatibility check and a clear failure reason for bounded-author counter
   configuration. A code-only model paired with a disabled execution host must not
   be described as having a verified executable counter. Keep registration and
   capability verification separate in provenance. Use version-bound public runtime
   metadata; do not silently trust unknown or changed tool modes.
2. Select an explicitly approved direct-tool-compatible manuscript model. The offline
   tested candidate is **gpt-5.5 / low**, subject to the existing account/model/effort
   preflight. Do not silently change the current **gpt-5.6-sol / low** selection,
   modify its catalog to hide requirements, or enable general Code Mode execution.
3. Preserve native final JSON, exact independent word counting, four-check bounds,
   one configured intake correction, original ledger/deadline, default-deny callbacks
   and every scientific/release gate. Keep zero tool calls as an explicit diagnostic;
   do not reject an otherwise valid in-range draft solely for missing a check.
4. Verify the compatibility guard and capability receipts with controlled fixtures
   and these real-runtime loopback tests. Only then prepare a separately authorized
   live counter/acceptance check with explicit ceilings and no automatic retry.

This investigation added tests and evidence only. Application behavior, production
settings, model choice, permissions and manuscript content remain unchanged. The
requested offline investigation is complete; production implementation/model choice
is the next phase to approve and review.

## Verification and preservation

- **8 new pinned-runtime tests passed**: Sol exposure with/without final schema and
  eager loading; direct-model counter roundtrip with/without schema; feature-override
  behavior; deferred-tool rejection. Processes and loopback servers close after each
  case, including errors.
- **161 focused tests passed** across the new runtime tests, Codex local transport,
  research Codex worker and manuscript length. Existing FastAPI/Starlette deprecation
  warnings remain. Ruff passed for the new test module.
- All **131 pilot hashes** and the latest acceptance package hash remain unchanged.
- No live provider/model calls, secret/default database access, original manuscript
  edits, commit, push or deployment occurred. The accumulated dirty checkout was
  preserved; final status/stat/diff checks separate these additions from older work.

Reproducible tests: `tests/test_counter_runtime_exposure.py`.
Compact evidence: [runtime comparisons](2026-10-05-counter-runtime-exposure.json).
Exploratory scripts and full synthetic captures remain in
`C:\Users\brian\AppData\Local\Temp\paper-workbench-counter-exposure-b4cbcfd08d5043bbab3cc2587e466d34`.

Continue the proposed implementation in this chat because the active patch and runtime
findings are directly relevant. **gpt-6.1-sol / medium** is sufficient for that code
phase. A model change and any new live attempt require explicit approval; higher
token/time ceilings do not fix this transport incompatibility.
