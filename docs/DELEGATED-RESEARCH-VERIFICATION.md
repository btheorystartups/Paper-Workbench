# Local verification — 2026-09-30

Implementation checkout:
`C:/Users/brian/Documents/Paper-Workbench/paper-research-delegation-worktree/Paper-Workbench`

Owner: `C:/Users/brian/Documents/PoP/Tools/Paper-Workbench`. No separate Paper Writer
repository was found; this is a project-scoped application feature. No project-specific
AGENTS.md files were present. The user's supplied global instructions applied.

The reviewed source changes were adopted into the owning checkout as uncommitted
local edits. Unrelated dirty files in the parent Tools repository were preserved.
The specifically authorized local SQLite database was backed up and migrated; no
other database or .env file was read or changed. No commit, push or deployment occurred.

## Results

- Full offline suite: **328 passed**, 1 existing Starlette/httpx deprecation warning,
  270.12 seconds. This run preceded the last source-version/unfinished-assignment
  hardening and two additional regression tests.
- Final delegated-research service/API suite: **32 passed** after that hardening,
  including the two additional regression tests.
- Follow-up existing migration, project transfer, Codex provider and Codex config
  regression selection: **74 passed**. Existing text-only provider restrictions pass.
- Final API selection after the task-list/UI adjustments: **3 passed**.
  These selections overlap; the numbers must not be added as distinct test totals.
- CI's `ruff check src/`: passed. All new Python files, new tests/fixtures, acceptance
  script and migration also passed Ruff. `git diff --check`: passed.
- An optional broader `ruff check src tests migrations` found **8 pre-existing
  findings** in untouched old tests/migrations: import ordering in five old migrations
  and `test_expansion.py`, plus unused symbols in `test_figures.py`. Left unchanged.
- Local browser smoke check: created a literature-search task, observed planning and
  completed state, parent plus two independent child records, zero model tokens,
  parent synthesis and disabled simulation approval. No browser JavaScript errors.
  The Download ZIP button issued a successful HTTP 200 ZIP response; the in-app
  browser's automated download-event wait timed out, so saved-file receipt was not
  verified with that browser tool. ZIP bytes, members and checksums were independently
  validated by the API tests and saved acceptance artifacts.
- After final adoption, the owner checkout's full suite passed: **333 passed**, one
  existing Starlette/httpx deprecation warning. This includes the best-effort
  protocol test and two controlled Codex-worker tests. Source lint and diff checks
  passed. An initial full-suite attempt failed in Windows temporary-test setup;
  the rerun with a fresh writable temp directory passed.
- The local PowerShell launcher parsed successfully and started the loopback app on
  port 8769. Its research-executors endpoint reported the process worker available.
  No research task or model call was started by this smoke check.
- After the no-empty-integration fix, the final owner-checkout offline suite passed:
  **334 passed**, with the same existing deprecation warning. Ruff and scoped
  `git diff --check` passed. The new time-cutoff regression test is included.

## What the spawning test establishes

Controlled test workers start as separate operating-system processes. Tests check
distinct parent/child process identities, child-to-parent lineage, preserved original
returns, report hashes and synthesis returned by the same parent process that planned
the assignments. Child failure, invalid results, cancellation, soft and hard token
stops, time cutoff, unknown-usage estimates, retained checkpoints and interrupted
recovery are covered. Native Windows virtualenv launcher and worker PIDs are recorded
separately. ZIP traversal, Windows special paths, links, duplicate names, member
counts, CRC corruption and expansion bombs are rejected.

The pilot's exact lifting question and original ZIP are exercised through the HTTP
application path. Controlled substantive report fixtures separately cover lifting,
literature search and independent proof audit, including conflict retention and
review-gated promotion. Fixture findings and token telemetry are simulated data;
they are not newly discovered research, live usage, proof or novelty certification.

**The controlled tests had not verified a real model child-agent handoff.** The
application now includes
a separate Codex app-server worker with independently launched parent/child
processes and ephemeral model threads. Its capability handshake verified the
dedicated ChatGPT profile, pinned runtime, model/effort, effective tool restrictions
and account quota without generation. A controlled offline peer verified the
best-effort opt-in and distinct model-thread provenance contract. The first real
lifting attempts failed at Codex `turn/start`, before a usage event or child spawn.
The transport deliberately hides provider error text; the recorded safe stage is
`turn_start`. Reported actual usage is zero, but missing telemetry cannot prove
that no account usage occurred. The ChatGPT account's primary quota read 5% used
after the attempts; no API key was passed to a worker. `codex_local` remains unchanged.
Inspection of the pinned runtime's generated protocol schema found that the
worker's turn request supplied an unsupported `access` field inside its read-only
sandbox policy. That request has been changed to the documented `networkAccess:false`
shape and checked offline with a controlled Codex client. The corrected request
was then exercised in one newly bounded live task. Codex started the planning turn
and reported 4,531 actual tokens. That exceeded the original 2,400-token planning
allocation, so the worker stopped before returning a plan or spawning a child.
The task was `limit_reached_partial`; **a real child handoff and parent synthesis
were still unverified at that stage**. A separately authorized 32,000-token/300-second run then
returned a live parent plan using 4,560 reported tokens and started one child
on a distinct Codex thread. The child did not return a usage event or structured
report before the research time cutoff. The task again ended
`limit_reached_partial`. Its child token usage is unknown; the 16,000-token child
reservation was labeled an estimate. The old code also started an integration
turn with no saved child work, creating a further 8,000-token estimate without
returning a synthesis. No child-to-parent result handoff was verified in that run. A
focused offline fix skips that integration when no child report or checkpoint exists;
later narrow live runs exercised the updated worker path, as documented below.

### Child-turn cutoff diagnosis

The 300-second task started at 09:12:08 UTC. Planning returned and the child was
spawned at about 09:13:29 UTC, leaving approximately 189 seconds before the
09:16:38 research cutoff; the last 30 seconds were reserved for handoff. The
runner stopped at the configured deadline at 09:17:08. The child had a distinct
Codex thread and turn ID, but no saved usage event, checkpoint, report, or worker
failure stage. Its 16,000-token allowance is a reservation, not a measurement.

Reconstructing the child's supplied prompt from the frozen task snapshot gave
approximately 7,955 local-tokenizer tokens. It included all three pilot documents
(16,689 source-text characters), the report schema, and the broad lifting audit
assignment. This explains why the 300-second task gave the child substantially
less time than the nominal limit, but it does not establish whether generation
was merely slow or the provider stopped responding. A metadata-only Codex
`thread/read` attempt after worker shutdown could not retrieve either ephemeral
thread. The worker did not persist intermediate Codex event counts or partial
text, so this run cannot resolve that distinction retrospectively. No further
model turn was started for diagnosis.

The old browser URL's exact project and task IDs were found in
`C:/Users/brian/Documents/Paper-Workbench/output/delegated-research-acceptance-verified-2026-09-30/acceptance.sqlite3`.
Its project is `Paper Writer — offline acceptance`, with five controlled tasks and
40 sources. It is synthetic acceptance data without an Alembic revision table, not
the migrated `data/workbench.sqlite3` application database. It was read only.

## Saved acceptance artifacts

Latest packages are in:
`C:/Users/brian/Documents/Paper-Workbench/output/delegated-research-final-2026-09-30/`

- `lifting.zip` — completed controlled parent / three-child / parent workflow.
- `literature.zip` — completed controlled literature-search workflow.
- `proof-audit.zip` — completed controlled independent-audit workflow.
- `partial.zip` — limit_reached_partial, with reports/checkpoints already saved,
  open questions and unfinished assignments.

`acceptance.sqlite3` in that directory is newly created synthetic test data, not the
user's project database. Reproduce in a fresh directory with
`scripts/research_acceptance.py`. Earlier acceptance directories retain development
diagnostics; use the `delegated-research-final-2026-09-30` packages above.

Live diagnostic packages are in `output/live-research-acceptance-2026-09-30/`,
`output/live-research-acceptance-retry-2026-09-30/` and
`output/live-research-acceptance-diagnostic-2026-09-30/`. Each used a new synthetic
database and the pilot's lifting question. The first stopped at prompt-size
preflight; the second and third failed before a model usage event. The last package
records `worker_failure_stage: turn_start`. No live child report or synthesis exists.
The corrected-request run saved
`output/live-research-acceptance-corrected-2026-09-30/lifting-live.zip` with
the observed planning usage, limit reason, source manifest and open work. It used
a new synthetic database. This package also has no child report or synthesis.
The one-child run saved
`output/live-research-acceptance-one-child-2026-09-30/lifting-live.zip` with
distinct parent/child thread lineage, one unfinished assignment, 4,560 reported
parent tokens and 24,000 conservatively estimated reserved tokens. Its ZIP
integrity check passed. It used another new synthetic database.

The named owner database backup is
`data/backups/workbench-before-delegated-research-20260930-144420.sqlite3`.
It passed SQLite integrity checking. A separate copied database successfully
traversed the full migration chain before the original was migrated. The original
then reached `f91a7b2c340d`, passed integrity checking, and retained one project.
That project's name is `Design UI`; it was not used for the synthetic acceptance run.

## Local rollout status

1. The narrow one-source parent-to-child-to-parent handoff completed in the second
   separately authorized live run documented below. Its report and synthesis still
   require scientific review before any proof or novelty claim.
2. The full three-source lifting audit, live literature search, and independent
   proof-audit quality remain separate acceptance scenarios. State their source scope
   explicitly if they are run.
3. Use `scripts/start_research_codex_local.ps1` for the migrated local database.
   Its only project is `Design UI`. The URL's `Paper Writer — offline acceptance`
   record is in a separate synthetic database. The bundled worker searches supplied
   text only and has best-effort token stopping; it does not satisfy a hard
   task-wide account-usage ceiling.

The existing task/report contracts, offline harness and acceptance examples are the
starting point for any follow-up. See `DELEGATED-RESEARCH.md` for the exact protocol
and limitations.

### Narrow live acceptance preparation — 2026-09-30

The Codex worker now emits a content-free heartbeat every five seconds during a live
turn, and a content-free progress record when it receives a Codex notification. Records
contain an ISO UTC timestamp, allowlisted stage, elapsed seconds, total notification
count, and a bounded count by recognized notification method (unknown method names map
to `other`). The runner validates and persists the latest record, notification counts,
and worker-heartbeat count in agent provenance. Partial ZIPs include this provenance in
`agent_lineage.json`, so a worker heartbeat is distinguishable from received Codex
notifications. No prompt, model output, credentials, or raw provider event is recorded.
The existing cancellation and deadline paths remain in place; worker line, transcript,
event-queue, and text bounds remain unchanged.

`scripts/research_live_acceptance.py --narrow-lifting-one-source` keeps the exact pilot
lifting question and attaches only `research_report.md`. Its single-child assignment
checks the finite asymmetric two-cell example's exact cross-cell distances and claimed
positive-observation topology, with a precise passage citation. It excludes the
symmetric comparison, general theorem, external literature, and novelty assessment.
The default continues to attach all three pilot sources and run the broader lifting
audit. The script labels the selected scope in its output and source version.

Offline verification for this change: **33 focused tests passed**, including the
controlled timeout/partial-package/provenance case, content-free worker telemetry, and
existing cancellation and read-only protocol checks. Ruff passed for the six changed
Python files with cache disabled. A trailing-whitespace scan passed; AST syntax parsing
passed for all six Python files. `research_live_acceptance.py --help` showed the narrow
option without starting a task. A
bytecode compile attempt could not write into existing `__pycache__` directories under
the sandbox; the in-memory AST syntax check succeeded instead. After tightening the
runner's timestamp validation to require UTC, the three worker tests plus the timeout /
partial-package regression were rerun and passed.

#### Separately authorized narrow live run — 2026-09-30

One run used **600 seconds**, **32,000 best-effort tokens**, one child, and
`--narrow-lifting-one-source`. It attached exactly one source. The run reached planning,
completed a child on a distinct Codex thread, and began parent integration. The child
turn used 174.4 seconds and returned a report with a recorded turn ID. Its saved
`original_return` equals the packaged report, and its report hash matches.

The task ended `limit_reached_partial` before parent synthesis. Reported usage was
25,692 tokens and estimated usage was zero. Planning reported 4,120 tokens against an
8,000 allocation; child research reported 11,069 against 16,000; integration reported
10,503 against 8,000 and triggered the worker allowance stop. The ledger records
`child_handoff_received: true`, no completed parent integration, and
`live_handoff_verified: false`. Parent plan and active integration used the same parent
thread; the child thread was distinct. The integration result was not received, so the
presence of its child ID in deterministic partial-synthesis bookkeeping does not prove
model synthesis. Progress provenance distinguished heartbeat counts from notification
counts. The ZIP passed CRC and every package-manifest SHA-256 check.

The package is
`output/live-research-acceptance-narrow-20260930/lifting-live.zip`. It is a synthetic
acceptance database and package, separate from the application database. The requested
parent-to-child return is verified; the child-to-parent model synthesis remains
unverified.

#### Second separately authorized narrow live run — 2026-09-30

Task `23b84148d41b4209965d00a859191c2a` used **600 seconds** and **64,000
best-effort tokens**, one child, and `--narrow-lifting-one-source`. It completed the
parent plan, child report, and parent synthesis. The package is
`output/live-research-acceptance-narrow-64k-20260930/lifting-live.zip`.

The package has exactly one source, `research_report.md`, and two completed agents.
The planning and synthesis turns have the same parent Codex thread ID; the child report
has a distinct thread ID. All three turn IDs are present. The child's `original_return`
equals its saved report, and its stored report hash matches. The parent synthesis lists
the child report ID and matching hash. The ledger has `child_handoff_received`,
`parent_integration_received`, and `live_handoff_verified` all true. This verifies the
live parent-to-child-to-parent handoff for the narrow one-source scenario.

Reported actual usage was **27,480 tokens**, with zero estimated tokens and complete
usage telemetry: 4,116 planning, 11,616 child research, and 11,748 integration. All
were below their respective 16,000, 32,000, and 16,000 allocations. Progress provenance
records 28 parent heartbeats and 2,890 parent notifications, plus 38 child heartbeats
and 3,368 child notifications. ZIP CRC and every package-manifest SHA-256 check passed.
The run verifies delegation and result handoff; it does not certify the scientific
claims, proof, novelty, or the broader three-source scenario.

## Results PDF and manuscript-path follow-up - 2026-10-01

See [Research artifact verification](RESEARCH-ARTIFACTS-VERIFICATION.md) for the new
readable results PDF, versioned package, synthetic UI/API checks and current readiness.
The acceptance ZIP remains unchanged and no owner database was accessed for this follow-up.
