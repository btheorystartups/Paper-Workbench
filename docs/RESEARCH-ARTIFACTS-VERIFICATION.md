# Research artifacts and manuscript path - 2026-10-01

Implemented locally without model calls, owner database access, migrations, commits,
pushes or external publication. Existing uncommitted delegated-research implementation
was the baseline. Only scoped files were adopted from a separate writable staging area.

## UI and API

- Project > Research > task > **Download results PDF**:
  `GET /projects/{project_id}/research-tasks/{task_id}/results.pdf`.
- Existing task ZIP download now contains `results.pdf` and renderer metadata, with
  original JSON reports, lineage, checkpoints and provenance preserved.
- Project > Research > **Path to manuscript and artifact package**:
  `GET /projects/{project_id}/manuscript-path` and `/manuscript-path/download`.
- **Download private artifact package**:
  `GET /projects/{project_id}/research-artifacts/download`.

All routes use existing project reviewer authorization. Evidence links open saved
records using the authenticated API client. Downloads work for draft, in-progress,
completed and stopped partial snapshots. No route promotes findings or records approval.

The ten manuscript stages aggregate saved research, latest partial checkpoints,
current hash-bound reviews, claims, sections, skeptical-review objects, reviewed compute
runs, checksummed PDF export receipts, and existing publication-package readiness.
Counts describe recorded objects; no readiness percentage is invented. A package's
existing approval is reported separately from the conservative project evidence assessment.
An old PDF receipt is evidence of typesetting only, not current scientific approval.

## Artifacts

Fresh demonstration: `output/research-artifacts-final-20261001/`.

- `results.pdf`: ten-page readable report from the unchanged narrow acceptance ZIP.
- `research-artifacts-v1.zip`: original versioned handoff.
- `research-artifacts-v2.zip`: adds independently recomputed finite examples,
  reproduction script/output and a hash-linked history back to version 1.
- `manuscript/provisional-outline.tex` and `.pdf`: explicitly provisional scaffold.
- `path-to-manuscript.json`, `verification.json`, `narrow-finite-checks.json`.
- `synthetic-results.pdf`, `partial-results.pdf`, synthetic task/project ZIPs and
  synthetic path export exercise the actual local HTTP application.
- `qa/`: rendered page images used for visual inspection.
- `synthetic.sqlite3` and `synthetic-data/`: disposable isolated demonstration only;
  do not import them into an owner's project.

Package entry point is `README_FIRST.md`; manifests cover all other ZIP members.
The shared checksum/ZIP writer is reused by the existing publication-package builder,
whose approval/staleness gates remain unchanged. Content-addressed snapshot versions
change with evidence, while an explicit numeric version and history support handoffs.
API downloads do not persist a new approved publication-package record.

The project bundle includes canonical recorded manuscript JSON and corresponding
Markdown/TeX/PDF snapshots when manuscripts exist. The provisional outline is a
separate scaffold and never replaces a recorded manuscript. PDF rendering reuses
WeasyPrint with the existing explicitly recorded minimal-renderer fallback.

**Privacy:** the whole ZIP is private. Byte-for-byte original task ZIPs retain private
provenance and are labeled `PRIVATE-original-research-task.zip`. Derived PDFs use a
field allowlist, HTML escaping, and free-text redaction. Account email, prompts,
raw events, credentials and private paths are excluded from the results PDF. Original
source metadata and quoted passages do not necessarily include full frozen source bytes.

## Scientific readiness

One source, one child report, three findings, five citations, five reported checks,
parent synthesis, **zero human reviews**. Execution completed; scientific acceptance
of the original broader question did not. The source-stated example has one coarse
cell and two states, so it cannot test non-vacuous cross-cell preservation. The four-state
two-cell case is a conditional specialization, not a source-stated example.

The local stdlib script independently checks the recorded matrices at epsilon=1, q=2:
8 and 64 directed-ultrametric triples, 3 and 9 open sets, zero versus eight ordered
cross-cell pairs. Its output explicitly does not establish a general theorem, novelty,
source authenticity, or human approval. Original agent reports/reviews are unchanged.

Next evidence requirements: clarify the intended source example; verify matching full
source text and broader coverage; review exact claims and locators; establish the
general argument or counterexample and bounded literature assessment; develop reviewed
sections; resolve skeptical review; finish authorship, declarations and publication gates.
No live research or owner-data action is necessary for the completed implementation.

## Reproduction

Use the project virtualenv with `WB_LOAD_DOTENV=false`, `PYTHONDONTWRITEBYTECODE=1`,
and the checkout's `src` on `PYTHONPATH`:

```powershell
python scripts/research_artifact_acceptance.py --narrow-finite-checks `
  --input output/live-research-acceptance-narrow-64k-20260930/lifting-live.zip `
  --output output/a-new-artifact-demo-directory
python -m pytest
python -m ruff check src --no-cache
```

The output directory must be new. The finite-check option verifies the exact frozen
input ZIP hash; it cannot silently apply those calculations to a different task.
The standalone reproduction script only evaluates its explicit finite tables and
never executes uploaded content or contacts an external service.

## Verification record

Original input SHA-256:
`62bbb8b55aed9a583ddf2f64031c6bfe901d2d4209b2f224244a89d02e6603d0`.
Version 2 SHA-256:
`6ba4e91bc5decc5609685d55737dba4de0f10003e006f6419cf189e9e20adb6e`.

ZIP CRCs, every manifest file hash, original ZIP identity, partial behavior and API
downloads passed. The synthetic path changed from no reports to three final reports,
while valid approvals stayed zero and publication readiness stayed false. Automated
tests additionally cover stale/rejected/offline reviews, evidence-gate transitions,
tenant access, private text exclusion, hostile HTML and package tampering.

Visual QA inspected all 19 rendered pages: 10 results, 2 outline, 2 cancelled partial,
and 5 synthetic results. No clipping, overlap or illegible glyphs observed. Browser
smoke check displayed all stages and opened an evidence record; export buttons issued
successful requests with no JavaScript errors. The in-app browser download event timed
out, so native saved-file receipt is not claimed; downloaded HTTP bytes were saved and
validated independently by the acceptance script.

The native LaTeX editor was opened, but its compiler failed with
`Unable to find standard directories for platform`. This is an environment limitation;
the TeX source is preserved and compilation is unverified. The paired PDF is a verified
application-rendered version of the outline, not a TeX compilation.

Staged full suite: 363 passed, one failure because the root `app.py` had not been
included in staging. Copying that unchanged file fixed the failure; it and final package
checks passed (11 tests). Final owner-checkout results are recorded below after adoption.

Final owner-checkout suite: **365 passed**, one existing Starlette/httpx deprecation
warning, 302.04 seconds. Source lint plus every new script/test passed; JavaScript
syntax and scoped Git diff checks passed. Broader lint retained the eight documented
pre-existing issues in untouched migrations/tests. All adopted source hashes matched
staging. Original-return equality, report hashes, synthesis references, identical parent
planning/synthesis thread and distinct child thread, and all turn IDs were rechecked.
No human approvals were added. The temporary browser test server was stopped.
