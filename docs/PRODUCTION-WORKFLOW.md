# Unified production workflow

The application at `C:\Users\brian\Documents\Paper-Workbench` is the working project
home. Its manuscript authoring, evidence graph, delegated research, revision review and
publication packaging operate on the same project and manuscript records. Older linked
worktrees and frozen diagnostics under `working/` remain historical evidence; they are
not runtime dependencies.

## Normal production path

The delegated-research task defaults to at most three child researchers under one
coordinating parent. The parent plans bounded assignments, each child returns a structured
report, and the same parent integrates the returned reports. The “three-agent production
default” therefore means `max_children=3`; it may involve four model processes when the
parent and all three children run. A task's explicit child, token and time limits remain
authoritative.

The research form now defaults to **Manuscript production** (`task_type=manuscript`).
Policy `manuscript-quality-v2-adversarial` requires proof/method, source/citation,
literature/contribution and adversarial reviewers for the complete draft. The parent
writes against an explicit section and claim inventory. Four fresh independent
children inspect the same frozen candidate, with at most three running concurrently.
Each wave starts three specialists; a completed and closed worker releases a slot
for the adversarial role while other reviews may continue. Known report-format
defects pause further dispatch until the bounded corrections finish. Waiting
correction workers retain their slots. All four roles retain budget reservations. At most two
repair cycles reuse the original budget and fresh reviewer threads; there can be
twelve children across three waves plus the persistent author. Adding a role does
not increase a task's authorized budget; exhaustion returns a blocked partial draft.

Adversarial reports must attempt concrete challenges for proof stress, source
entailment, novelty limits, scope overclaims and reproducibility. Each unresolved
challenge binds a blocking objection and measurable criterion in the existing review
ledger. Passed challenges establish only the supplied evidence's stated scope.
Older three-role runs remain historical evidence and do not satisfy the new gate.

The task shows separate outcomes: draft produced, agent checks complete, and human
publication approval. Diagnostic drafts remain downloadable with blockers. Missing
coverage, stale evidence, unresolved serious objections, invented execution receipts,
and bibliography markers prevent review clearance and release. Offline simulation
can exercise the workflow but cannot become production evidence. Existing exploratory
research tasks retain their parent-plan/child-report/parent-synthesis behavior.

The controller's readiness report is visible in the task, manuscript path and exported
JSON. It records reviewer and packet hashes, claim assessments, adversarial challenges,
agent blockers, pending human text/support/source decisions, publication audit findings
and package freshness. It assigns no numerical submission probability. A diagnostic
handoff can complete while human review and release remain pending. Agent review does
not change `Source.human_verified`, claim support or AI-text acceptance. Human publication
approval is reported from an approved current publication package through the existing
evidence binding; stale packages and bibliography placeholders remain release blockers.

Exploratory research output enters a manuscript through a human's hash-bound review
and explicit promotion. Manuscript production instead creates a new **unaccepted AI
draft**, linked claims and sections; it does not accept prose or approve publication.
Subsequent objections and repairs in both paths use
`services/revision_review.py`: the responding author cannot close their own objection,
and an independent verification binds the comment, response and candidate hashes.
Publication approval and export continue through the existing manuscript evidence basis
and publication-package checks. Do not create a second review ledger or evidence graph.

For one local application with both live manuscript chat and delegated research, prepare
the dedicated Codex profile and database as documented in `CODEX-LOCAL.md` and
`DELEGATED-RESEARCH.md`, set `WB_CODEX_LOCAL_GATE_SECRET` in the current process, then run:

```powershell
.\scripts\start_paper_workbench_local.ps1 -AccountEmail you@example.com
```

The launcher uses the guarded loopback chat server and configures the research worker in
the same process. It does not load `.env`, run migrations, start a research task, or relax
the per-task acknowledgement and budget checks. The manuscript form can explicitly
authorize up to four public Crossref queries, capped at five results each. API clients
can select the existing supported adapter and at most ten results per query. Search
receipts record real failures and empty results separately; imported metadata is still
discovery evidence. Workers receive frozen text and cannot browse or execute source code.

## Review and call evidence

Specialist packets bind the candidate, source versions, whole section/claim coverage,
searches and execution receipts. Exact passage checks establish that quoted text is in
the referenced source; semantic support and proof adequacy remain reviewer judgments.
Assertions about evidence availability name the artifact and packet. Ambiguous prose
receives review flags, and corrected historical assertions identify the earlier packet.
These checks share `evidence_availability.py` with the evaluation workflow.
Unresolved prose flags are accepted diagnostic findings and publication audit errors;
they do not by themselves require a scientific manuscript revision. They are recomputed
from the bound report, so editing a saved flag cannot grant release clearance.

Version 2 task requirements bind the question, paper type, success criteria, explicit
length bounds, requested verification and literature-search scope. The packet also
binds task instructions and frozen source metadata. Changing these inputs invalidates
current reviewer clearance. Earlier packets retain only the requirements they actually
recorded; historical runs are not retroactively credited with version 2 binding.
Accepted specialist reports must match their recorded original return after schema
normalization, as well as the campaign's report hash and packet binding.

For structured manuscript length bounds, the author has one pure dynamic tool,
`check_manuscript_length`, limited to four calls per draft/revision/correction turn.
It accepts only section IDs and text and returns exact whitespace counts, per-section
counts, inclusive bounds, a midpoint target and a normalized section-text hash. It
cannot read files, execute code, access a network or make writes. Reviewers and general
research workers retain their existing tool restrictions. The author is instructed
to check the final section text and revise meaningful prose toward the midpoint.
Counter calls stay within the original turn's token allowance and deadline; fresh
corrections reset only that turn's counter limit. Final intake uses the same counting
implementation and independently rejects out-of-bounds drafts. Missing or mismatched
precheck receipts are diagnostic metadata; valid text is not rejected solely for
omitting the tool. No padding or relaxed word bounds are applied by the controller.
Per-attempt provenance retains counter counts/hashes and call timing/stacks without
raw tool arguments. The existing packet length-assertion shape remains unchanged.

Production packets carry complete structured section text once, with each section's
path and checksum in the evidence inventory. Frozen source snapshots include authors,
year, venue, DOI and URL as supplied metadata; their presence does not certify accuracy.
Reviewers collect related actionable corrections in one pass, and the author addresses
all supplied comments together. Every claim and section still requires coverage.
Scientific corrections are distinct from corrections to earlier evidence-availability
claims, which require an actual earlier packet manifest.
Claim statements must specify domains, quantifiers and assumptions. Side remarks,
conclusions or limitations that broaden scope or remove an assumption must be covered
explicitly by a mapped claim or omitted. Semantic inventory completeness still requires
independent reviewers; section/claim ID validation alone cannot establish it.

Author intake permits one correction of a rejected draft in each drafting or
scientific revision phase. It uses a fresh ephemeral model thread on the same
logical author worker, with the rejected draft/hash, unchanged frozen task/source
packet, complete validation defects and exact response inventory. The worker checks
the original against its own prior return before starting the correction. Shared
allocation charges, deadline and specialist reserves continue unchanged. Scientific
revision also starts fresh with the exact previous candidate/hash, frozen evidence,
complete prior comments/responses and expected response IDs. The worker binds that
candidate to its own latest return, including any corrected draft. Historical author
thread identities remain excluded from independent reviewer identities.

Returned reports with coverage, quotation, receipt or availability defects retain all
detected validation issues and the original return. The controller finishes the wave
before offering each affected specialist **one** correction turn on the same packet
and logical worker, using a fresh model thread. Corrections share the task's original
token ledger and deadline; they do not create new agents or manuscript revision cycles.
A second invalid return remains
blocked. Identity/packet-integrity failures and hard stop conditions still fail closed.
The trace links every rejected attempt to its call span; rejected reports never count
as specialist clearance. Author prose cannot substitute for recorded independent review.

The final parent handoff uses the four immutable report hashes and compact review
decisions. It preserves all original specialist reports in the campaign and agent
records without repeating their full text or the complete candidate in the parent
prompt. For this handoff the parent worker creates a fresh ephemeral summary
thread, preserving author/revision context and receipts as evidence without
replaying that conversation. The provenance links both thread identities; usage
starts from the fresh thread's baseline, within the original task ledger. Other
parent operations retain their existing contexts.
A small unused token margin reduces best-effort overshoot risk. If the
production task ends before that handoff completes, valid agent checks remain
visible but manuscript release stays blocked until the task is completed, the
parent/child handoff receipts are recorded, and human publication approvals exist.

Scientific candidate hashes exclude assessment events and human acceptance flags, so
adding a review does not invalidate itself. Publication evidence hashes still include
the review records and approvals. Changes to scientific content or bound source/receipt
bytes invalidate reviews. There is one existing revision-review ledger and one existing
publication approval path.

Allowlisted `finite_partitions_v1` executes exhaustive finite checks for carrier sizes
1 through 5 (2,959 ordered partition pairs), recording implementation/input hashes,
environment, timestamps and scope. It never executes ingested or model-generated code.
Other computational evidence must use existing hash-bound approved compute runs.

The task view and ZIP expose `call-trace.json` and `call-timing-summary.json`. The scoped
`/projects/{project_id}/research-tasks/{task_id}/call-trace` endpoint adds worker RPC
timings. Events identify controller-assigned agents, parentage, specialist roles,
operation spans, worker PIDs, model threads/turns, UTC times and elapsed durations.
Stacks contain function names, repository-relative filenames and line numbers only;
RPC timings exclude prompts, response bodies, frame locals and exception messages.
Controller timestamps describe when calls were observed, not server-side queue times.
Worker stream failures expose fixed reason codes for authentication changes, model
rerouting, runtime errors, unsupported items, invalid message deltas, response text
bounds and incomplete turns. Valid codes are retained in agent provenance and the
`worker_failed` trace event. Raw provider messages and arbitrary tool names are not
included. Older failures without these codes retain their original limited diagnosis.
Per-turn stream measurements record delta count, character/UTF-8 byte totals,
first/last delta timing, completed-message size and supplied prompt-token estimate
with its counting policy. They contain no message content. Controller intake binds
each snapshot to its allocation span and started model turn, validates counters and
finite timings, and retains up to 100 turn snapshots per worker. Counts reset per
turn; legacy workers without these fields remain supported. A final stream snapshot
is emitted on normal completion or controlled interruption/error where possible;
forced process termination may prevent it. `finished` means streaming ended, not
successful validation or scientific clearance. These measurements do not measure
reasoning tokens, server queue time or billed usage.
Optional activity snapshots additionally count reasoning notifications, item events,
usage events, counter requests and local heartbeats without retaining reasoning text.
They use the same allocation/thread/turn binding and reject regressing counters and
invalid timings. The task view exposes notification/progress inactivity and local
heartbeat gaps. A gap of 30 seconds raises an observation flag; two minutes without
observable progress raises a separate review flag. Neither proves computation stopped
or changes the deadline. Keep the host awake during an authorized live run: lid closure
or standby can suspend workers and interrupt connections while the original deadline
continues. The application does not change power settings or prevent standby.
Structured runtime failures retain only an allowlisted category, valid HTTP status
and boolean runtime retry flag when available. Unknown categories become `unknown`;
raw messages, additional details and reasoning content are discarded. These fields
survive the diagnostic package and are not scientific clearance. A runtime retry flag
does not authorize a workflow retry: the campaign still stops on the failure.
Cancelled and failed calls retain terminal receipts. Token stopping remains best effort
for the current live worker; missing telemetry consumes the full reserved allowance.

## Production budget reservations

The research Codex worker defaults to **gpt-5.5 / low**. Bounded author operations
require the version-reviewed direct counter transport for runtime **0.154.0**.
The previous gpt-5.6-sol catalog requires Code Mode, whose execution host this
restricted workflow disables. Explicit model overrides are preserved; incompatible
or unreviewed bounded-author selections stop at input checking before a model turn,
with a saved, fixed counter-compatibility reason. General text-only operations do
not require counter compatibility. Existing account/model/effort preflight remains
mandatory; the new default does not attest authenticated availability.

Set `WB_RESEARCH_CODEX_MODEL=gpt-5.5` in an approved launch when an older explicit
override exists. No profile, secret file, generic chat default or permission setting
is changed by this selection. The counter descriptor declares `deferLoading: false`.
`length_tool_capability` records the pinned offline review separately from registration
and successful callback receipt; `length_precheck.matching_check` still determines
whether a receipt matches the final text. Compatibility review is not live model
compliance or scientific clearance. Unknown usage retains conservative reservation
charging. Word-count bounds, repair limits and release blockers are unchanged.

Before the first specialist dispatch, the campaign records a conditional capacity
plan for the first review plus one scientific revision, all four re-reviews, format
repair pools and handoff. It includes known historical-inventory growth without
inventing future comments. Further configured revision cycles and future candidate,
output, model overhead and time remain explicit unknowns. This planning risk flag
does not require a revision when the initial draft already passes.

Revision admission records exact required remaining capacity, shortfall and implied
minimum total ceiling under its saved forecast. Readiness exposes the latest plan
with its candidate/token/time-ceiling basis and flags a changed or legacy missing
time basis as historical. Before author revision and before a fresh intake correction,
the controller recomputes time admission against the original research deadline.
Completed author and four-role review durations support a three-slot forecast; it
includes one author correction, one shared report-repair pool, a 25% duration margin
and reviewer startup reserve. The author-correction baseline is at least the longest
ordinary author call; observed corrections can raise it. Unseen repairs use ordinary
author/largest-reviewer fallbacks. Startup reserves four serial launches using the
largest observed spawn plus 25%, with a five-second minimum. A revision correction
reserves only the correction and review follow-through, not another scientific
revision. Insufficient known time stops before dispatch and retains accepted
evidence and open objections. The first draft correction lacks observed specialist
timings and checks its known author cost; unknown timings remain explicitly unestimated.
Stopped or unfinished calls do not establish zero-cost forecasts. Handoff time stays
outside the research deadline. Future candidate size, service latency and additional
repairs remain uncertain; the shared repair pool cannot guarantee every possible repair.
These are planning estimates, not completion guarantees or publication approval.
The task view displays the forecast and shortfalls; creation explains that the
96,000-token form default may not fund the full manuscript cycle. New manuscript
contracts use the same 10,000-token handoff reserve as the planner. Historical
contracts retain their original values, and general research keeps its percentage
reserve. No planning estimate raises a task's authorized ceiling.

The Codex runtime receives the strict operation-specific outputSchema once. Compact
prompt serialization preserves all supplied fields/source text and avoids an additional
general schema copy. Prompt estimates use the same rendering as actual dispatch;
native schema/model overhead remains covered by observed usage and margins.

Revision admission reserves each role's largest completed fresh audit or re-review
usage plus 25%, with the frozen prompt plus 6,000 tokens as a lower bound. Unseen roles
use a 20,000-token baseline, raised for larger prompts. Format repairs remain charged
but do not inflate future scientific review forecasts. A separate repair reserve includes the frozen packet,
original returned report and known correction details, with the same output headroom;
10,000 tokens remain protected for final integration. The minimum author grant is
the largest of 12,000 tokens, observed author usage plus 25%, or the full revision
prompt plus 6,000 tokens. These fixed calibration values do not grow merely because
the task ceiling grows. The campaign
records the forecast; unavailable full-cycle capacity stops before author revision.
These margins are estimates, not a guarantee of live completion.

The initial review wave protects the fundable repair pool while prioritizing all four
reviews. Deferred reviewers retain their grants. Repair charges consume that pool once;
spent repair capacity is not reserved again. Only terminal actual usage releases unused
grants; missing usage remains charged at the reserved allowance. Audit-wave plans are
recorded in the campaign and call trace.

Each specialist may correct one rejected report in a fresh model thread. The same
logical worker receives the frozen packet, original report and precise defects.
Original returns, hashes, allocations and old/new model identities remain auditable;
the task ledger and deadline continue unchanged. Author revisions and intake
corrections use the fresh bound context described above.

Allowlisted finite checks freeze their exact implementation as a publication-bound
artifact and include standard-library dependencies, a hash-checked installed-module
invocation and deterministic expected output. The workflow never executes manuscript
attachments. Finite checks do not replace independent scientific review or human
release approval.

## Fourteen-stage diagnostic

`evaluation_desktop_workflow.DesktopWorkflow` is a separate development experiment: two
six-role arms followed by two order-swapped graders. It requests up to fourteen native
desktop agents and produces diagnostic candidate artifacts. It is not the production
orchestrator, does not write a project manuscript, and does not grant publication
eligibility. Its frozen October 3 artifacts remain unchanged under
`working/desktop-pilot-2026-10-03`.

Evidence-intake v2 accepts diagnostic output independently from release eligibility.
Availability statements intended to support release use exact packet and artifact
identities. Ambiguous prose is retained with a review flag. Historical corrections name
the earlier role, packet hash and artifact path. Unresolved bibliography placeholders and
unresolved review flags remain release blockers.

See `docs/audit/2026-10-05-bounded-offline-follow-up.md` for this policy change and
offline verification, and `docs/audit/2026-10-05-offline-acceptance-brief.md` for
the reviewable brief for a separately authorized acceptance attempt.
See `docs/audit/2026-10-05-combined-offline-contract-audit.md` for the subsequent
requirement binding, diagnostic/release separation and budget edge-case follow-up.
See `docs/audit/2026-10-05-length-and-time-admission.md` for the bounded author counter,
time-admission follow-up and offline replay of the consumed full-cycle attempt.
