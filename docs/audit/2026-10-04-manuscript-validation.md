# Unified manuscript validation — 2026-10-04

## Result and scope

The unified project at `C:\Users\brian\Documents\Paper-Workbench` completed a real,
bounded manuscript task with three child researchers and one coordinating parent.
The same application also completed live section editing, reviewed application of
the edit, and generation of an unaccepted plain-language summary. Seven manuscript
export formats were produced and checked.

This establishes working generation, delegation, handoff, editing and export for
the tested example. It does not certify new research, literature completeness,
general mathematical correctness, journal readiness, or every possible manuscript.
The live draft remains explicitly unreviewed and ineligible for release.

Work began from `36d2370` on `main`. The existing dirty `uv.lock` was preserved.
The root virtual environment has the project dependencies and optional test,
local Codex, semantic research, PDF, figures and OCR dependencies installed.
The tested Python is 3.13.5; the pinned Codex runtime is 0.154.0.

All application data, databases, generated papers and test receipts used synthetic
temporary storage. The original publication collection was consulted only for its
collection guide and review expectations; its manuscripts were not edited or sent
to model workers. No default database, secret file, API-key provider, production
migration, deployment, commit or push was used in this validation phase. Live calls
used the existing dedicated ChatGPT profile through the supported account interface.
No profile credential files were read. No paid API service was called.

## Defects reproduced and fixed

| Observed failure | Change | Verification |
| --- | --- | --- |
| A burst of model progress events filled the transport queue and lost the terminal result. | Bounded backpressure preserves reports; repetitive progress is coalesced without dropping counts. | A 300-event subprocess regression, cancellation while full, and successful live handoff. |
| Planning returned JSON that failed the report contract. | Send an output schema derived from the existing Plan, AgentReport and Synthesis models; retain validation on receipt. | Closed schema and citation tests; actual parent and three child reports validated. |
| Parent synthesis stopped at its fixed phase allowance despite unused verified task capacity. | Release unused capacity only after final actual telemetry, and allocate remaining task capacity to integration. Unknown usage retains the full reservation. | Regression with a synthesis larger than its initial reserve; missing-usage test; live completion within 96,000 task tokens. |
| Live manuscript chat used a rejected `readOnly.access` field. | Use and verify a named permission profile with no filesystem grants or network access. Reject inherited/substituted grants. | Restriction regressions and live reviewed edit plus summary. |
| Release checks did not block empty or unaccepted AI prose, or accepted outputs carrying bibliography markers. | Feed explicit blockers through the existing manuscript audit and publication evidence basis. Reuse the bibliography-marker check in evaluation. | Publication regressions, including accepted output still blocked until its marker is removed; corrected historical review quotation allowed. |
| Requesting BibTeX without citations omitted the file and could break bundle assembly. | Emit an empty `references.bib` when requested. | Export and checksummed publication-bundle regressions; repeat live-draft export with all requested formats. |

The release work reuses `revision_review.py`, the manuscript evidence basis and
publication package readiness. No second approval ledger was introduced. Diagnostic
acceptance still does not imply publication eligibility.

The ordinary default remains **at most three child researchers plus one parent**.
The fourteen-stage desktop evaluation remains a separate development experiment;
the frozen October 3 pilot was not rerun. See [production workflow](../PRODUCTION-WORKFLOW.md).

## Live evidence

### Delegated manuscript

The synthetic source defines block-constant Boolean functions on finite partitions.
The task asks for a proof, a four-point enumeration, correction of a quoted false
historical claim, explicit limitations, and no novelty claim. Assignments cover
proof checking, independent enumeration and skeptical scope/correction review.

- Model: `gpt-5.6-sol`, low reasoning; three children, 96,000 best-effort task tokens,
  900 seconds. These are test-specific bounds; the application defaults remain
  24,000 tokens / 600 seconds and are not a promise of a complete full paper.
- Final state: `completed`; parent and all three children completed.
- `live_handoff_verified`, `child_handoff_received` and
  `parent_integration_received`: true. Distinct child thread identities and original
  report hashes are retained; synthesis uses the original planning parent.
- Confirmed final usage: **62,204 tokens**. The manuscript, research report and
  reviewer report were returned. This is reported usage, not a billing statement.
- Before the fixes, three bounded attempts exposed transport loss, invalid planning
  output and the integration allowance problem. Their known reported usages were
  4,691 and 61,295 for the latter two attempts. The first had incomplete telemetry;
  its 24,000 reservation was retained as estimated usage, not reported as zero.
- Independent deterministic enumeration verified the refinement/function-inclusion
  equivalence and counts over carriers of sizes 1–5: **2,959 ordered partition
  pairs**. The specific example has function-set sizes 4, 4 and 16, intersection
  size 2, and the stated `0011` counterexample. This is a finite check, not a
  substitute for a general proof or literature review.

Successful evidence root:

```text
C:\Users\brian\AppData\Local\Temp\paper-workbench-live-manuscript-c26bbcad90a04d75a48d79d4843bd73e
```

It contains `synthetic-source.md`, `snapshot.json`, `research-package.zip`,
`paper.md`, `research_report.md`, `reviewer_report.md`,
`independent-finite-verification.json`, and `manuscript-export-receipt.json`.
The ZIP SHA-256 is
`bac0c2f9b10969dc862eb464d44a9e918484e9dc74085074b34c8b49b5c49fc1`.
These are local temporary diagnostics and are not stored in the publication collection.

The draft was imported as unaccepted diagnostic prose into its temporary database
for export testing. This import is not a human promotion or publication approval.
The audit reports `manuscript-unaccepted-ai`, and the export receipt explicitly
records `release_approved: false`.

### Live manuscript chat and browser

A separate synthetic database exercised the actual guarded loopback HTTP server:

- Missing gate rejected; existing account verified through the adapter.
- Live section revision proposed and applied with its matching review hash;
  duplicate approval rejected with HTTP 409.
- Live summary created with `accepted_by_user: false`.
- Export downloads and stored artifact checksums matched.
- Browser navigation verified workspace, project, manuscript sections, executed
  edit history, unaccepted summary, three-child default and updated allowance copy.
  No browser console errors were observed.
- The owned test server was stopped and the temporary browser tab closed.

Receipts are `receipt.json` and `browser-check.json` under:

```text
C:\Users\brian\AppData\Local\Temp\paper-workbench-api-smoke-4af62bb148704d969c92984b6bf7d715
```

The HTTP export receipt predates the empty-BibTeX repair and records the missing
file honestly. The subsequent export regression and successful manuscript export
receipt verify the corrected behavior.

### Export quality

The complete generated draft exported Markdown, LaTeX, HTML, DOCX, BibTeX, PDF and
JATS, plus a manifest. Every stored artifact hash was verified. JATS passed the
bundled full JATS 1.3 archiving DTD. WeasyPrint 70.0 and MathJax 3.2.2 rendered
75 equations; all three PDF pages were inspected with no clipped text or broken math.
The native LaTeX export also compiled to three pages using installed MiKTeX, with
package installation and shell execution disabled. Its expected warning was that
the synthetic, unapproved draft has no author. The app's built-in compiler was
unavailable due to its platform-directory error; the installed compiler supplied
the successful check. DOCX and HTML file generation was checked; Word layout and
typeset equations in those formats were not independently certified.

## Automated verification

| Run | Result |
| --- | --- |
| Baseline full suite after dependency installation | 640 passed, 1 skipped |
| Full suite after core fixes | **658 passed, 1 skipped**, 690 seconds |
| Final export/publication/unified-workflow suite after the final BibTeX fix | **26 passed** |
| Ruff over `src` and `tests` | Passed |
| JavaScript syntax check for updated research UI | Passed |
| `git diff --check` | Passed |

The new empty-BibTeX test was added after the full-suite collection and is included
in the 26-test run. These run counts overlap and should not be added together.
The one skipped test requires Windows symlink-creation privileges; the separate
Windows junction boundary test passed. Two existing Starlette/AnyIO deprecation
warnings remain; no dependency churn was introduced to silence them.

The full suite includes the evidence-intake regressions for paraphrased false
absence, quoted historical corrections, a different missing report, historical
packet scope and an accepted final diagnostic containing a bibliography marker.
Structured contradictions remain deterministic failures; ambiguous prose remains
a review flag; unresolved bibliography markers remain release blockers.

Full-suite JUnit receipt:

```text
C:\Users\brian\AppData\Local\Temp\paper-workbench-final-validation-7bf52fdb7be541748f383de58f6f93b9\results.xml
```

Final focused JUnit receipt:

```text
C:\Users\brian\AppData\Local\Temp\paper-workbench-export-regression-39604a3d9940497d8df6acac37228d20\results.xml
```

To reproduce automated tests, use the root `.venv`, `WB_LOAD_DOTENV=false`, fake
providers, an explicitly named temporary `WB_DATA_DIR` and `WB_DATABASE_URL`, and
an isolated pytest `--basetemp`. Do not use a normal manuscript database. Live
reproduction additionally consumes the existing ChatGPT account's usage and needs
an explicit bounded task; the temporary harness is not a startup instruction.

## Preservation and remaining judgment

The frozen pilot still has 131 files and its latest modification is
2026-10-03 17:40:58 local time, matching the pre-test inventory. No operation in
this phase targeted that directory or the PoP checkout for writing. No root
`data` directory was created. Source changes were left uncommitted at the end of
validation; the subsequent user-authorized commit and push are recorded in Git.

Further synthetic generation is unlikely to add much evidence. The useful next
validation is a chosen real manuscript question with a frozen source set, explicit
research limits, subject-specific proof/data checks and human review of claims,
citations, authorship and release readiness. No real manuscript is automatically
approved by this software smoke test.

Runtime protocol references used for the compatibility repair:
[official app-server documentation](https://learn.chatgpt.com/docs/app-server) and
[official permissions documentation](https://learn.chatgpt.com/docs/permissions),
checked against the installed runtime's generated JSON schemas and effective
configuration response.
