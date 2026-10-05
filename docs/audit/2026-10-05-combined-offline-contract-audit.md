# Combined offline acceptance-contract audit

## Scope

Continues the authorized structured-length follow-up in the canonical checkout at
`C:\Users\brian\Documents\Paper-Workbench`. Changes are local and reviewable.
All execution uses synthetic temporary storage, offline responses or controlled
protocol workers. No live manuscript agents, paid calls, original manuscript edits,
default databases, secrets, commits, pushes or deployment are included. The existing
dirty checkout and frozen October 3 pilot artifacts are preserved.

## Findings and implementation

### Reviewer bindings

Length and success criteria were bound, but task question, paper type and requested
verification/search scope were not in the requirements projection. Version 2 packets
now bind those inputs, task instructions and the frozen source metadata manifest.
Changing a bound input invalidates current clearance. Earlier packets retain their
recorded, narrower requirements scope; this is compatibility, not retroactive evidence
that earlier reviewers checked the new requirements.

Rechecking a report hash alone allowed a changed report and resealed campaign hash to
agree. Current assessment also checks the stored original return and its packet hash,
after schema normalization. Deleted production tasks cannot retain clearance.
Readiness counts current section text rather than the last saved draft snapshot.

### Repair and revision reservations

Initial reviewer grants could consume capacity intended for report corrections.
The initial wave now protects the fundable repair pool while preserving priority for
all four reviewers. A correction's charged usage consumes that pool once. Deferred
reviewers no longer reserve already-spent repair capacity again. Missing or pending
actual usage still consumes the reserved allowance through the central task ledger.

Fresh repair prompt estimates now include the original returned report and known
correction details. Author revision estimates use the same full payload builder as
the actual operation, including previous candidate and prior comments. Prompt counts
reuse worker preflight counting, with a conservative byte fallback. Each audit wave
records grants, funded repair capacity, repair forecast and handoff reserve in the
campaign and trace. Original token/time limits and one report correction per reviewer
remain unchanged. Estimates cannot guarantee successful live completion.

### Diagnostic acceptance and release

Ambiguous availability prose already generated review flags, but those flags also
entered the scientific blocker list and could trigger manuscript revisions. Flags are
now accepted diagnostic findings. Current assessment recomputes unresolved flags from
the packet-bound report, and the existing manuscript audit emits release-blocking
errors consumed by publication-package readiness. Editing a saved campaign flag does
not grant clearance. Structured availability contradictions still reject reports;
scientific objections still use `revision_review.py`. Bibliography placeholders remain
blockers through the existing publication evidence path.

Production documentation now distinguishes three concurrent child workers, the four
required manuscript-review roles, production budget rules and the separate fourteen-
stage experiment. It also corrects stale statements about reviewer correction context
and the number of report hashes used in final integration.

## Verification

Twelve new regression cases cover funded initial repairs, near-budget corrections
before deferred re-review, changed question/paper type/instructions/verification scope,
changed frozen source metadata, resealed accepted reports, accepted ambiguous diagnostic
reports with canonical publication blockers, current-text length, oversized repair
inputs and deleted production tasks.

The focused suite covers:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_manuscript_quality.py tests/test_research_codex_worker.py tests/test_research_task_api.py tests/test_publication_packages.py tests/test_evaluation_desktop_workflow.py tests/test_evaluation_pair.py -q
```

**168 distinct focused tests passed**: 166 in the combined suite, plus the two final
forecast/deleted-task regressions added after that suite was collected. The strengthened
ambiguous-diagnostic regression also passed separately: marking stored campaign flags
resolved does not bypass the recomputed publication blocker. Existing regression
coverage includes paraphrased absence claims, quoted historical corrections, different
missing reports, packet scope and accepted diagnostic output with bibliography markers.
Python F/I lint, JavaScript syntax and Git diff checks passed. The frozen October 3
pilot still contains 131 files and was not edited. Existing Starlette/httpx/anyio
deprecation warnings are unchanged.

## Remaining boundary

These changes have no new live acceptance evidence. The earlier live run completed
agent review but missed its prose-only length request; it remains historical evidence,
unchanged. A future run must set explicit `manuscript_length` and requires new explicit
token/time authorization. Continue review in the current chat because the evidence and
active patch are shared; no new thread or model switch is required for this phase.
