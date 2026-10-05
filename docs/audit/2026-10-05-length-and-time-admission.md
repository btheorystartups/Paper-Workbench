# Bounded offline length and time-admission follow-up

## Scope and evidence

The user authorized addressing the next issues after the consumed 320,000-token /
1,200-second full-cycle acceptance. This phase implements length-generation support
and time admission offline in the canonical `C:\Users\brian\Documents\Paper-Workbench`
checkout. It preserves the existing dirty work, scientific objections, frozen packets,
word bounds, independent review and human release gates. No new model acceptance,
paid request, manuscript agent, pilot rerun, secret/default database access, original
manuscript edit, commit, push or deployment occurred. Tests use synthetic temporary
databases and controlled processes. Historical acceptance JSON was read without mutation.

The prior attempt rejected a 787-word initial draft and an 884-word scientific revision
under the same 900–1,200-word bounds. Its permitted corrections consumed substantial
time. Token capacity funded revision, while a recorded 403.8-second revision/review
estimate already exceeded 260.4 research seconds remaining. That timing flag did not
previously prevent dispatch. See `2026-10-05-full-cycle-live-acceptance.md` for the saved
attempt, unresolved source/scope objections and final usage accounting.

## Reviewable changes

- `manuscript_length.py`: bounded text-only tool arguments and a shared pure word
  counter. Titles, headings, claim metadata and responses remain excluded; equations
  and references in section text remain included. Inclusive bounds are unchanged.
- `codex_rpc.py`: an optional trusted server-request handler. The default text-only
  transport still denies server requests. The worker allowlists only the counter
  for the active author thread/turn, with no namespace, replayed call IDs or other
  capabilities. Malformed arguments consume a check and return a fixed diagnostic;
  a fifth request stops the turn. No permission or runtime restriction is relaxed.
- `research_codex_worker.py`: registers the counter only for bounded author operations,
  instructs checking exact final text before JSON, and returns bounded measurement
  receipts plus content-free timing/call stacks. Native final output schemas remain
  enabled. Fresh correction contexts and original draft/evidence bindings are retained.
  Missing checks or changes after a check are visible; they do not create a new gate
  rejecting otherwise valid final text. Final controller counting remains authoritative.
- `manuscript_quality.py`: final counting reuses the pure helper while preserving the
  historical packet length-assertion format. This avoids invalidating saved packet
  bindings merely by adding tool diagnostics.
- `manuscript_quality_runner.py`: recomputes time admission before scientific revision
  and fresh author corrections. Forecasts include three-slot re-review, author/report
  repair reserves, a 25% margin and measured reviewer startup. Accepted candidates and
  open review rounds survive denial; rejected responses are not applied. Each draft
  attempt retains its own counter receipt, and the parent is shown running while authoring.
- `manuscript_readiness.py` and `research.js`: expose denied time plans, available versus
  required seconds, and staleness when candidate or token/time limits change. Legacy
  plans lacking a time-limit basis are historical. These estimates never grant release.

The pinned 0.154.0 runtime's generated experimental JSON schemas confirm dynamic-tool
descriptors, `item/tool/call` requests/responses and `dynamicToolCall` items. Generation
ran in an isolated temporary profile without inference or account access. OpenAI's
[App Server documentation](https://learn.chatgpt.com/docs/app-server) describes the same
experimental protocol. Tool/schema coexistence is covered by controlled transport and
worker tests; actual model use and improved length behavior remain unverified live.

## Timing policy and replay

The forecast uses the largest completed ordinary author duration and each specialist's
largest completed ordinary review. Corrections remain separate. Author repair cost is
at least the ordinary author baseline, raised by completed corrections. Report-repair
cost uses the largest completed report correction, or the largest reviewer duration
when unseen. One shared report-repair pool is reserved, matching bounded token planning;
it does not guarantee capacity for four simultaneous report repairs. Startup reserves
four serial process launches at the largest observed spawn duration plus 25%, with a
five-second minimum. All modeled operation and repair durations receive a 25% margin.
The protected handoff interval is already outside available research time.

Before four specialist timings are available, full-cycle time stays unestimated.
An initial draft correction checks known author repair cost without fabricating review
history. After a rejected scientific revision, admission reserves correction plus
independent review and the shared report-repair pool. Pending/stopped calls cannot
create a false zero-duration forecast. Estimates are admission guards, not a service
latency guarantee or a reason to change the user's ceilings.

`2026-10-05-length-time-admission-replay.json` applies the new pure forecast to saved
JSON trace/allocation evidence:

| Saved point | Required research seconds | Remaining seconds | New decision |
| --- | ---: | ---: | --- |
| Original scientific revision admission | 993.33 | 260.40 | Stop before revision |
| Rejected revision's proposed intake correction | 855.01 | approximately 31.87 | Stop before correction |

The second remaining-time figure is reconstructed relative to the saved revision
forecast and trace timestamps. No saved artifact or database was edited. All **131**
frozen pilot files match their saved SHA-256 baseline; hash letter case was normalized
when comparing the PowerShell baseline to Python digests.

## Verification

The broad focused suite passed **349 tests** in **868.37 seconds**:

```powershell
.venv\Scripts\python.exe -m pytest -o addopts= tests/test_manuscript_length.py tests/test_research_codex_worker.py tests/test_codex_local.py tests/test_manuscript_quality.py tests/test_research_transport.py tests/test_research_task_api.py tests/test_publication_packages.py tests/test_evaluation_desktop_workflow.py tests/test_evaluation_pair.py tests/test_evaluation_adapter.py -q
```

After final receipt/timing metadata changes, **138** worker/counter/transport tests,
**6** targeted timing/readiness/full-cycle tests, and a final **78** worker tests passed.
These are overlapping follow-up runs, not additional unique tests. Ruff F/I checks,
`node --check src/workbench/web/static/research.js`, and `git diff --check` passed.
Two existing Starlette/httpx and AnyIO deprecation warnings remain. No missing runtime
dependency prevented verification. An initial suite command named a nonexistent
`test_evaluation_workflow.py`; no tests ran from it. The corrected invocation uses
`test_evaluation_adapter.py` and the desktop/pair tests that exercise that workflow.

Coverage includes:

- Exact section-text counts, inclusive bounds, excluded metadata, whitespace handling,
  normalized content binding, malformed/oversized inputs, duplicate IDs and code-looking
  text treated solely as data.
- Transport default denial; active thread/turn/tool/namespace binding; replay denial;
  malformed requests consuming the four-call allowance; bounded fresh correction reset;
  same-turn count correction; changed text after a check; valid output with no precheck.
  Counter telemetry contains only measurements, hashes, fixed tool identity and stacks.
- Complete controlled revision plus all four independent re-reviews; known insufficient
  time despite funded tokens; time rechecked after a previously sufficient budget plan;
  no correction dispatch when follow-through cannot fit; accepted candidates, original
  returns, open objections and unapplied rejected responses preserved.
- Observed repair/startup durations, unknown timing, unfinished-call exclusion,
  original handoff protection and candidate/token/time basis staleness.
- Existing evidence-intake regressions: paraphrased false absence retained as a review
  flag, quoted/corrected historical claims, artifact-specific different missing reports,
  historical packet scope and accepted final diagnostic output with a bibliography
  marker still blocked from release. Publication binding and revision closure remain
  covered through the existing services.

Early integration tests detected that readiness graph measurements supplied text-only
sections and that adding tool hash fields to packet assertions changed comparison
shape. The final helper supports legacy graph measurements, and packet assertions keep
their prior shape. The corrected suite passed; frozen artifacts were not rewritten.

Final status/stat review confirms the broad dirty checkout includes work from earlier
phases. The file list above identifies this phase's changes; the entire Git diff is not
attributed to this follow-up. Nothing was staged, committed or pushed.

## Remaining verification and thread choice

Offline implementation cannot establish that a real author will use the counter or
produce a scientifically cleared manuscript. A new bounded live attempt needs separate
explicit authorization, token/time ceilings including setup, a fresh temporary output
folder and no automatic retry. The consumed attempt's source/scope objections remain
open. Do not raise a budget solely to make the prior trajectory fit.

Continue in this chat for that closely related verification because the active dirty
patch, bound evidence and decisions are needed. Retain the existing manuscript model
for the first efficacy comparison; `gpt-6.1-sol / medium` is sufficient for controller
review and diagnosis. No model change, new thread or live run is initiated here.
