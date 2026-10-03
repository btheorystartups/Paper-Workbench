# Saved research retrieval

For the subsequently added local semantic index, Broad/Focused discovery modes, benchmark
results and setup, see [Semantic coverage](SEMANTIC-COVERAGE.md). The lexical path below
remains available. API defaults preserve existing behavior; the UI now defaults to hybrid
Broad discovery and labels weaker leads explicitly.

The Research task form now defaults to **Retrieve saved project evidence and prior
research**. Enter optional coverage topics (one per line), then use **Preview relevant
evidence and gaps**. Creation runs retrieval again and freezes the result in the task
contract; the preview is not a reservation. Later library changes do not rewrite it.
For a blind independent proof audit, turn reuse off to avoid exposing previous findings.
Existing API clients keep their previous behavior unless they opt in.

`POST /projects/{project_id}/research-retrieval` accepts `query` and optional `topics`.
This is a read-only, authenticated reviewer operation. Task creation accepts
`reuse_prior_research: true` and `coverage_topics`. Creating a draft does not start
workers or authorize live execution. No schema migration, new service, embedding API,
or model call is needed for retrieval.

## Evidence and coverage

The library is the existing project storage. Each request derives a bounded index
from ingested extracted text, child findings, recorded searches, unresolved questions,
and research leads. It includes final reports and the last checkpoint when no final
report exists. Deleted tasks, agents and sources are excluded. Other projects are
never searched. Raw prompts, account provenance and worker events are not indexed.

Original source passages carry source/version IDs, original and extracted hashes,
zero-based character ranges, and a SHA-256 of the exact passage. These locators refer
to extracted text. PDF passages additionally carry physical PDF page numbers; PDF
passages never cross a page boundary. Only stored extracted artifacts with hashes
are eligible; metadata-only search hits and legacy file paths are skipped. Source
originals are checked again when retrieved passages are frozen into a new task.

PDF passages are labeled as discovery text. The preview's **Open original PDF** button
opens the preserved original at the relevant physical page (which may differ from the
printed page number). The authenticated, project-scoped original route checks the
artifact hash and serves only PDF content. It does not open arbitrary filesystem paths.
Check formulas and hypotheses on that page before citing them. Missing quality warnings
do not certify math: ordinary-looking text can still have flattened exponents or omitted
symbols. Workers receive the same instruction in their retrieval contract.

PDF intake supports `auto`, `text`, `plain`, and `ocr`. `plain` selects pypdf's plain
reading order explicitly, which can help with interleaved columns; it does not run OCR.
`text` selects layout extraction with a fallback to plain text when layout is unavailable
or expands excessively. `auto` uses the same fallback and attempts optional local OCR
on pages with low text or control, private-use, or replacement glyphs. It never installs
an OCR engine. OCR results remain unreviewed, including outputs with no detected defects.
Page provenance records the selected method, fallback reason, exact character offsets,
quality issues, and retained/truncated status. The extractor never guesses replacement
math symbols. Legacy extracts are still discoverable and marked unreviewed; reingestion
is required to benefit from the new extraction path. Existing frozen tasks do not change.

Prior findings retain citation locators and task/agent/report hashes. Checkpoints and
offline simulations are labeled. A prior finding is a lead, never independent evidence
or transferred human approval. Prior citations may refer to an unavailable original;
the worker must report that limitation instead of treating the old assertion as proof.

Identical passage text is merged within its evidence kind, retaining version-specific
origins. Different versions with different text remain separate. Query matching uses
Unicode word tokens with inverse-frequency weighting. Selection penalizes similarity
to already selected items and favors new query terms. It does not infer semantic
equivalence, recognize every mathematical notation, or establish literature coverage.
Topic match counts are retrieval diagnostics, not completion percentages. A zero count
means no selected lexical match, not no prior art.

The parent sees bounded relevant history and is instructed to propose distinct topics
or methods and explain necessary overlap. The runner gives each selected card exactly
one child owner using question relevance and load balancing. Each child receives only
its historical cards; source-passage text is supplied through the source context rather
than duplicated in the child's retrieval metadata. Sources may still be shared across
assignments. Exclusive card ownership does **not** guarantee distinct scientific work
or a blind independent audit; differently worded overlapping tasks need review.

The ledger records `retrieval_allocation`; child assignments retain their card IDs.
The frozen contract, sources and ledger are included in the existing private task ZIP
and project artifact package. Existing review hashes bind the new context as well.
Uploaded documents added after creation remain usable sources but do not refresh the
frozen retrieval snapshot; create another task to refresh prior-research retrieval.

## Bounds and economics

The scan considers the latest 100 project sources, latest 100 tasks, up to 600 children,
2,000,000 extracted characters per source (the ingestion ceiling) and 8,000 candidate
cards. Passages are at most 1,600 characters; adjacent PDF passages on the same page
overlap by 200 characters. Selection returns at most 12 cards and 18,000 serialized card characters.
Scan/selection limits, skipped sources, and truncated source scans are reported.
`scan_limited` is also true if ingestion already truncated a source, with reasons in
`truncated_sources`; a retained extract is never reported as complete merely because
the index reached its end. A larger corpus may need more than one bounded indexing batch.
The query and topic labels are separately bounded. Oversized cards are omitted rather
than silently clipping their evidence. Existing task source and worker prompt limits
still apply; a small live token allowance may reject the supplied context before a call.

This uses existing saved evidence without a persistent search database. The scan runs
again for each preview/create. It reduces duplicated historical context by construction,
but token or billing savings have not been measured. No web literature search or citation
verification agent has been enabled. Prompt caching is not this evidence library.

## Local verification, 2026-10-01

`scripts/research_retrieval_acceptance.py --output <new-directory>` creates only a fresh
synthetic database, attaches two synthetic sources, runs controlled offline workers,
retrieves prior work and runs a second offline task. The saved `retrieval-preview.json`,
`allocation.json`, and `verification.json` show six distinct items with exclusive
ownership, no match for the deliberately absent astronomy topic, and zero model tokens.

Tests cover deterministic selection, version-aware duplicate origins, corrupt/deleted
sources, project and tenant isolation, checkpoint/simulation labels, locators/hashes,
immutable task context, package preservation and worker allocation. Existing delegation,
task API, Codex worker and artifact-package regressions are included in verification.
The demonstration is transport and retrieval evidence, not scientific validation.

Final owner-checkout verification: **381 tests passed**, one existing Starlette/httpx
deprecation warning, 338.22 seconds. Source/new-test/script Ruff checks passed with
`--no-cache` (the initial default cache directory was outside the writable sandbox).
JavaScript syntax and `git diff --check` passed. Existing unrelated changes were
preserved; the ten adopted files were checked against a SHA-256 adoption manifest.

The browser verified preview results, a zero-match topic, draft creation with frozen
retrieval, and the final six-item allocation (three per child). Temporary servers were
stopped. The final artifacts are in `output/research-retrieval-final-20261001/`, including
the synthetic database/data, JSON evidence, test report and `ui-coverage.png`.
No owner database, live model call, migration, commit, push or deployment was involved.
