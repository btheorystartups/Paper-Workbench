# Delegated research (local v1)

Use the **Research** tab inside any local project, including Paper Writer. Create a
question, choose general research / literature search / independent proof audit,
optionally enter success criteria and instructions, select ingested documents, then
attach individual documents or ZIPs. Empty details use an evidence-first template.
The default deliverable is a research report plus the full evidence package. Paper
and reviewer-report requests add explicitly unreviewed drafts to that package.

This feature belongs to Paper Workbench's application code; it does not require a
separate Paper Writer repository or an online deployment. The new schema is in
migration `f91a7b2c340d`. The named local database was backed up and migrated on
2026-09-30; other instances still need their own backup and upgrade.

## What has actually been exercised

The offline executor starts a persistent parent worker process, receives its bounded
plan, starts independent child worker processes with distinct IDs, polls and saves
their checkpoints/results, and sends the returned reports back to that same parent
process for integration. It does not call `ChatProvider`, replay sequential chat
prompts as children, or change any `codex_local` restrictions.

The offline worker and test peer are controlled fakes, not model agents. The separate
`research_codex_worker.py` uses a dedicated ChatGPT-plan Codex profile and creates
one ephemeral Codex thread per independently spawned worker process. The parent
process keeps its thread between planning and synthesis. It has no shell, MCP,
browser or web-search tools: its search scope is the attached frozen text.

The dedicated profile and worker capability handshake were verified. Earlier
lifting attempts stopped at Codex `turn/start`; a corrected request started a live
planning turn and reported actual usage, then stopped when its planning allowance
was exceeded. A second bounded run returned a parent plan and started a child on
a distinct Codex thread; it reached the time cutoff before the child returned a
report. A later narrow one-source run returned a child report but stopped when
parent integration exceeded its phase allowance. A separately authorized
64,000-token/600-second narrow run completed planning, the child report, and parent
synthesis. The package verifies distinct parent and child threads, the original child
return and hash, and synthesis on the planning thread. This establishes a live
parent-to-child-to-parent handoff for the narrow one-source scope. See the
verification record for the completed package and earlier partial packages. The
pilot ZIP remains a single-agent format reference, never evidence of delegation.
On 2026-10-04, a synthetic finite-partition manuscript task completed with three
independent child researchers and the original parent synthesizing their reports.
The live package verified all three returns and thread identities. The generated
paper, research report and reviewer report remain unreviewed diagnostic artifacts.
See [the manuscript validation record](audit/2026-10-04-manuscript-validation.md).
The separate `codex_local` chat provider also passed a live reviewed-edit and summary
check after its request format was updated for the pinned runtime; its text-only
restrictions remain enforced.

## Intake, provenance and evidence

Accepted document types follow existing ingestion: PDF (text extraction only here),
TeX, Markdown, text, BibTeX, CSV, JSON, Python, HTML and YAML. Scripts/HTML are inert
text. No uploaded code is run; no ZIP path is used as an extraction destination.
OCR is not automatically invoked. Extraction confidence and unresolved PDF page
states are carried into each snapshot.

Limits: the configured upload body ceiling (default 4 MB), 200 ZIP members, 8 MB per
member, 40 MB expanded, and 100:1 maximum member expansion. Absolute/traversing paths,
Windows alternate streams/device names, ambiguous duplicates, links/special files,
encrypted entries, unsupported compression and bad CRCs are rejected. Nested ZIPs
and unsupported members are inventoried and retained inside the original archive,
not recursively expanded. All members have SHA-256 hashes; the ZIP itself, originals
and extracted text are retained in the existing content-addressed artifact store.

Sources are frozen when execution starts. Snapshots preserve source IDs, original
and extracted hashes, acquisition, access/license, extraction state, archive/member
origin and user-declared version. “Unspecified” never means current/latest. Conflicting
versions remain distinct. Each document supplies at most 120,000 extracted characters;
truncation is labelled. Total task context is limited to 400,000 characters and 40
documents. Repeated identical uploads are idempotent.

Reports include findings, citations or precise source locators, proof attempts,
failed approaches, open questions, research leads, searches with coverage, and
verification artifacts. Categories are `verified_result`, `conjecture`,
`apparent_prior_art`, `counterexample_candidate`, `nothing_found`, and `unresolved`.
“Verified” is the child's scoped assessment, **not an application-issued certificate**.
It requires located evidence and a recorded passed verification artifact. Nothing
found requires a recorded search; neither it nor apparent prior art establishes novelty.

Original structured child returns and checkpoints are preserved. The parent must
reference every completed valid report. Deterministic comparisons retain all
findings grouped by their declared claim key; differing statements, scopes, statuses
or stances are visible as conflicts/scope differences even if the parent omits them.
Unmatched keys remain uncompared, not assumed agreements. Semantic equivalence and
scientific correctness require human review.

## Limits and lifecycle

Defaults: **24,000 task-wide tokens / 600 seconds / at most 3 children**. A worker
advertising a hard total-token limit allocates 10% to planning, at most 70% to
children, and reserves 20% for integration. A best-effort worker allocates 25%
to planning, at most 50% to children, and reserves 25% for integration. The
larger live planning allowance reflects observed Codex reasoning overhead; each
phase can still stop before returning a result.
Research stops before the last 10% of wall time so the parent can return a handoff.
Every worker operation receives a total-token allowance (including supplied context,
reasoning and tool/model work), and a remaining wall-time allowance. No unbounded
retry or automatic continuation exists.

Completed phases with confirmed final actual usage release their unused allowance
for parent integration, within the original task-wide ceiling. In-flight work and
phases with incomplete telemetry keep their full reservation. The ledger records
released capacity separately; cumulative historical reservations may therefore be
larger than the currently committed allowance. Progress notifications are coalesced,
and bounded transport backpressure preserves final reports during bursts.

Actual reported tokens are separate from conservative estimates. Missing/incomplete
telemetry charges the unused part of the full reservation as estimated usage; it is
not zero usage and is not an account billing ledger. Committed capacity cannot exceed
the task limit when allocating new work. A worker may advertise a hard total-token ceiling, or explicitly
advertise best-effort stopping with task-level human opt-in. The Codex worker uses
the latter: it rejects oversized supplied prompts and interrupts when streamed
usage reaches the allowance, but an in-flight turn can overshoot before usage
arrives. Missing telemetry is estimated. Neither this ledger nor Codex text limits
are an account billing ceiling. A detected overrun stops further work and is reported.

At a research cutoff, children are stopped; only available reserved capacity may be
used for parent integration. After the observed limit, local deadline or cancellation,
no further model operation starts. Deterministic packaging of already-saved data uses
no model tokens and remains available afterward. The terminal states include
`completed`, `limit_reached_partial`, `failed_partial`, `cancelled_partial`, and
`interrupted_partial`. Terminal tasks cannot resume; additional research requires a
new task and new limits. Failure/cancellation retains completed reports and checkpoints.

Execution v1 needs a persistent local Python application; serverless execution is
refused. Shutdown cancels owned workers. After an abrupt application crash, saved
work is recovered as interrupted on the first task read/download after its hard
deadline plus a short cleanup allowance. No work is silently restarted. A trusted
worker must stop on stdin EOF, cancellation or its deadline, including any remote
jobs it owns. Killing a local process cannot prove an upstream service cancelled;
that behavior remains part of live-worker acceptance verification.

## Human review and output

Review an exact task/report snapshot, select the intended use (finding, proof,
scoped novelty assessment, or manuscript), and record the evidence checked and
scope. Then use **Promote approved finding**. Approval is bound to the source,
report and synthesis hashes and the selected purpose. It does not authorize a
different purpose. Proof/novelty promotion needs a verified-within-scope finding
plus the human's assessment. Simulation findings cannot be promoted. The original
reports are never overwritten. Manuscript promotion explicitly selects a manuscript
in the same project and adds a scoped section with a claim/evidence link.

Download works during execution (a checkpoint snapshot) and after any terminal
state. The ZIP contains a readable summary, task contract/settings/usage, agent
lineage, source manifest, search log, individual JSON/Markdown reports and
checkpoints, parent synthesis and comparisons, verification artifacts, open
questions, review history and requested draft deliverables. A package manifest
hashes every other member. Artifacts are data, never executed by export.
The task and original artifacts also participate in whole-project export/restore.
Restored approval hashes may need human review again because artifact locations
are rewritten; restore never starts a worker.

## research-process-v1 worker contract

Set operator configuration, not task input. For the bundled Codex worker, use the
absolute paths to this project's virtualenv Python and worker file:

```text
WB_RESEARCH_EXECUTOR_ENABLED=true
WB_RESEARCH_EXECUTOR_COMMAND=["C:/absolute/path/to/.venv/Scripts/python.exe","C:/absolute/path/to/src/workbench/providers/research_codex_worker.py"]
WB_RESEARCH_CODEX_HOME=C:/Users/<you>/.paper-workbench-codex
WB_RESEARCH_CODEX_ACCOUNT_EMAIL=<expected ChatGPT email>
WB_RESEARCH_CODEX_MODEL=gpt-5.6-sol
WB_RESEARCH_CODEX_REASONING_EFFORT=low
```

The expected email is recommended; the worker always requires ChatGPT
authentication and the parent verifies that returned child accounts match. Use
the **best-effort token stopping** checkbox when creating a task with this worker,
then acknowledge that specific live execution at start. The acceptance helper
`scripts/research_live_acceptance.py` requires an explicit ChatGPT-plan flag,
uses a new synthetic database, and never retries automatically.

For the migrated local checkout, run `scripts/start_research_codex_local.ps1`
from PowerShell to open a loopback-only app on port 8769 with the dedicated
ChatGPT profile and the named local database. It disables automatic migrations
and `.env` loading. This only configures the executor; it does not start a
research task or establish that live turn generation works.

The executable is launched with no shell, an empty temporary working directory,
and a minimal OS environment. Application API keys, local gate values and `.env`
configuration are not inherited. Authentication must be independently established
by the trusted worker using its supported provider mechanism. Do not pass secrets
as command arguments. Selecting `process` never selects the chat provider.

Messages are newline-delimited JSON on stdin/stdout. Stderr is not persisted. Every
response echoes the application's `agent_id`. Maximum message size is 2 MB; total
output is bounded at 8 MB per process. No unsolicited events/tool commands are
accepted. The worker must wait idle between commands and exit on stdin EOF.

1. App sends `{op:"hello", agent_id}` before any generation. Worker returns
   `{type:"capabilities", agent_id, worker_pid, capabilities:{protocol:"research-process-v1",
   executor:"operator name/version", simulated:false, child_agents:true,
   structured_reports:true, hard_total_token_limit:false,
   best_effort_token_stopping:true, bounded_wall_time:true, no_external_writes:true}}`.
   A hard-limit worker may instead set `hard_total_token_limit:true`. Best-effort
   workers require explicit task opt-in. Children must match the parent's
   capabilities. Hello performs no research or model calls.
2. Parent receives `op:"plan"`, contract, frozen source text/metadata, task ID,
   token/time allowances and policy. Return `type:"plan"`, `result:Plan` and optional
   final `usage:{tokens,kind:"actual"|"estimate",source}`. Live model results also
   carry Codex thread/turn/account/model provenance. Parent remains alive/idle.
3. Each independently launched child receives `op:"research"`, its assignment,
   parent/task IDs, selected frozen sources, contract, policy and allowances.
   It may emit `type:"checkpoint", report:AgentReport` (maximum 25) and cumulative
   `type:"usage", usage`. Return `type:"report", result:AgentReport, usage` on completion.
   `type:"limit"` stops research and returns saved work; `type:"error"` fails that child.
4. The same parent receives `op:"integrate"` with all valid returned reports/hashes,
   checkpoints and lineage, plus the reserved allowance. Return `type:"synthesis",
   result:Synthesis, usage`. Original reports remain separately stored.

`src/workbench/research_contract.py` defines the exact message schemas; the
controlled worker in `tests/fixtures/research_protocol_worker.py` is an executable
protocol example, not a production agent. A live integration must demonstrate
distinct model thread IDs, actual child reports, parent integration, usage
telemetry and cancellation before being called verified.

## Verification commands

Run with `WB_LOAD_DOTENV=false` and this checkout's `src` on `PYTHONPATH`, using the
existing project virtualenv. The suite is offline:

```text
python -m pytest tests/test_delegated_research.py tests/test_research_task_api.py
python -m pytest
python -m ruff check src tests migrations
```

Tests cover the pilot lifting question, literature search, independent proof audit,
real subprocess identities and parent continuity, capability refusal, source hashes,
ZIP safety, time/token partial returns, failure/cancellation, stale review gates,
tenant access, exports and schema migration on disposable databases.

## Readable artifacts and manuscript progress

Task downloads now include a results PDF. The Research tab links to an evidence-derived
project manuscript path and private versioned artifact package. See
[Research artifact verification](RESEARCH-ARTIFACTS-VERIFICATION.md) for routes, privacy
boundaries, the narrow demonstration, reproduction commands and evidence gaps.
