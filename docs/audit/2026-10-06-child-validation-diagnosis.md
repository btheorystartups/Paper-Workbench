# Offline diagnosis of the gpt-5.5 child validation failure

## Scope and evidence

This work used only saved synthetic acceptance artifacts, local source, and offline
tests. No live model call, acceptance retry, original-manuscript edit, default
database access, secret access, commit, push, or deployment was performed. Existing
dirty changes in `C:\Users\brian\Documents\Paper-Workbench` were preserved.

Frozen run directory:

`C:\Users\brian\AppData\Local\Temp\paper-workbench-gpt55-acceptance-e9e6cee3906345c780c24b7f4a4c18bf`

Task: `78f9c5e53d4e479ba00bacb5744738cc`.

Hashes before and after diagnosis were identical:

- `lifting-live.zip`: `59816fa1e8f5fb70d75d12663a55fdd31aede79faa9c826ef4d5f29bdfc1ae4f`
- `acceptance.sqlite3`: `e9644b22379fbfbdb4bd6531a44f60d61cb806337a57a6862cc9b2e2a379e541`

The explicitly authorized synthetic database was opened through SQLite URI
`mode=ro`, with `PRAGMA query_only=ON`. Research-agent rows matched the package.

## Findings

The failed child, `1fe7163c329d4d98bcbd2c0dc0b44ee3`, completed its stream. Saved
telemetry records 4,398 deltas, 18,337 characters/bytes, and a completed message of
the same length. The worker then failed at `report_validation` with
`ValidationError`. The trace records this at sequence 20. There is no recorded
counter, transport, turn-completion, or JSON-decoding failure.

The local code narrows this to `AgentReport.model_validate(json.loads(raw))`:
JSON parsing succeeded, then model validation rejected the returned value. The
worker never emitted an accepted report to the controller. The empty `{}` in the
package is the agent's unsupplied report field, not evidence that the model
returned an empty object.

**The exact rejected field or semantic rule is unrecoverable from the saved
evidence.** The worker retained only the exception class, not validation codes,
paths, or rejected text. The database has the same provenance as the ZIP, with no
additional response or checkpoints. The saved run directory has no response log.
Potential causes include shape/field constraints and report evidence-reference
validators; selecting one would be speculation. The regressions below are
synthetic examples of this failure class, not reconstructions of the lost text.

A separate, definite failure occurred during parent integration. The parent did
return a structurally valid synthesis, but its `report_ids` contained all three
child IDs, including the failed child. The controller supplied only two completed
reports and correctly required exact report-ID coverage. Its inventory check
therefore rejected that synthesis, explaining the terminal generic stop reason
`executor or report validation failed`. A failed child alone already warrants
`failed_partial`; successful partial synthesis must not turn that into acceptance.

## Scoped changes

- `src/workbench/research_contract.py`: preserve existing rejection rules and
  messages, with fixed Pydantic error codes for citation targeting and report
  evidence/ID consistency.
- `src/workbench/providers/research_validation.py`: produce bounded, content-free
  diagnostics (total error count, up to 20 codes, up to 12 path components).
  Codes are allowlisted; paths retain only known schema fields and bounded indices.
  Unknown keys become `*`. Response values, exception messages, and context are
  excluded. JSON decoding errors receive a separate fixed code.
- `src/workbench/providers/research_codex_worker.py`: attach those diagnostics to
  failures; explicitly state cross-reference rules in child instructions; bind
  synthesis report-ID count and allowed values to `message.reports`; explain that
  failed lineage entries do not supply report IDs. The controller still checks
  uniqueness and exact coverage independently.
- `src/workbench/services/research_runner.py`: revalidate diagnostics before saving
  them in agent provenance and the `worker_failed` call-trace event, only for
  `report_validation` failures.
- `tests/test_research_codex_worker.py`: add 14 offline cases covering complete
  streams rejected by structural, semantic, and JSON checks; worker-to-controller
  diagnostic persistence; sanitization and bounds; synthesis ID inventories;
  and explicit child instructions. Failures remain failures, with one turn and
  no automatic retry.

No validation was relaxed, no missing evidence was fabricated, and no failed
report was promoted to completed. These changes close the diagnostic gap and
address the observed synthesis-generation mismatch. They do not prove that the
unknown historical child defect can no longer occur.

## Verification

Using the repository's `.venv/Scripts/python.exe`, with dotenv loading disabled
and fake provider mode:

- `-m pytest tests/test_research_codex_worker.py -p no:cacheprovider`:
  **112 passed**.
- `-m pytest tests/test_counter_compatibility.py tests/test_counter_runtime_exposure.py tests/test_delegated_research.py tests/test_research_task_api.py tests/test_research_artifact_package.py tests/test_math_typesetting.py -p no:cacheprovider`:
  **74 passed**, with two existing FastAPI/Starlette deprecation warnings.
- Read-only replay: both saved completed-child reports validate with unchanged
  content. The saved parent synthesis passes structural validation but includes
  the failed child ID; the new generation schema admits only the two supplied
  IDs and requires exactly two entries.
- `git diff --check` passes. Ruff comparison against the preserved pre-edit
  baseline finds no new lint issues; 36 existing line-length findings remain in
  the touched files. The new diagnostics module passes Ruff.
- Final `git status --short` and `git diff --stat` were reviewed. The accompanying
  `offline-validation-fix.diff` is relative to the dirty pre-edit baseline, so it
  isolates this task's code/test changes from earlier work.

## Remaining acceptance and recommendation

Offline work is complete within the available evidence. Successful end-to-end
live acceptance remains unverified. A single fresh bounded acceptance run is
warranted if acceptance is still required, but it requires fresh explicit
authorization specifying a token limit and setup-inclusive time limit, with no
automatic retry. It should capture any new validation codes and paths. Do not
reuse the previous one-attempt approval or alter the frozen failed run.

Continue that closely related verification in this chat to retain the evidence
and approval boundaries. For routine launch/monitor/audit coordination,
`gpt-6-luna` / medium is a reasonable least-cost available choice; measured billing
or savings are not established. The application's acceptance worker selection
remains `gpt-5.5` / low. No further model run is needed unless live verification is
authorized or new evidence arrives.
