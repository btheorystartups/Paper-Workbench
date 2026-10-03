# Evidence-grounded client and research proposals: assessment and implementation prompt

Prepared 2026-09-14 from source inspection at commit
`188aa990c79fc7c5adaa4295f64aa74f195ec770`.

## Assessment

Paper-Workbench has reusable foundations, but not a complete client-proposal workflow.
A user can manually create a manuscript with proposal-style sections, assemble relevant
claims/excerpts, discuss and revise each section, and export it. That differs from
uploading two collections of papers and getting an evidence-grounded applicability
analysis, a complete proposal, and named subsequent versions.

| Need | Existing implementation | Remaining work |
| --- | --- | --- |
| Bring in papers and the author's work | `ingest/files.py`: PDF, CSV, text/Markdown/LaTeX/BibTeX and other text formats; preserves original and extracted artifacts with hashes and extraction metadata. Browser upload and local ingestion routes in `main.py`. | Batch intake with source roles, extraction review, automatic retrievable chunks; DOCX intake if required. HTML files are treated as text, not a complete website-import workflow. |
| Read a website | HTTP extraction adapter and safe-fetch utilities exist. | Explicit bounded URL-to-source intake, selected linked documents, durable snapshots, redirect safety, and ingestion UI. Do not equate registering a URL with reading the linked research. |
| Chat using a configured model | `config.py`, `providers/registry.py`, `providers/llm.py`, `services/usage.py`; OpenAI and Anthropic adapters, fake mode, usage tracking and project token ceiling. | Reuse this path for proposal analysis and drafting. Make effective provider/model and simulation status visible; no hard-coded proposal model. |
| Discuss both collections | Pinned objects/sources and manuscript context exist; the current section includes linked claims and excerpts. | Proposal-wide context and retrieval over extracted full text, with author/client/background collections and an explicit client brief. |
| Retrieve relevant passages | `semantic.py` indexes research-object bodies and source title/authors/venue/abstract; results are labeled similarity. | It does not index extracted paper text or excerpt chunks. Pinned source IDs in general chat supply bibliography, not full text. Add bounded passage retrieval and coverage reporting. |
| Establish research fit | Claims, evidence links, support states, integrity audits, contribution assessment, and paper-candidate design exist. | Structured client needs → relevant capability → evidence → limitation → applicability hypothesis → validation plan. Similarity must not become evidence of applicability. |
| Produce a proposal | Custom manuscript structure and sections; generic alternative outputs and paper designs. | First-class proposal intake, outline, reviewable multi-section drafting, and business/research templates. Existing edit “proposals” are pending actions, not client proposal documents. |
| Revise | Section-aware chat, before/after review, human revision, reject, stale-context checks, guarded apply and undo; branches and audit history. | Reuse these protections. Add proposal-wide consistency and immutable named document versions, comparison, and revision-specific export. |
| Versioning | `supersedes` relation, action history, submission revisions and versioned publication packages exist. | These are not a general versioned proposal editor. Do not force a client proposal into a journal submission to obtain versioning. |
| Export | Markdown, HTML, DOCX, LaTeX, bibliography, PDF with runtime-dependent renderer, JATS; provenance/audit manifests. | Proposal-appropriate references and layout, immutable version binding, and no overwritten previous exports. DOCX export is not DOCX re-import/round-trip editing. |

Configuration uses environment-backed settings: `WB_PROVIDER_MODE`, `WB_LLM_PROVIDER`,
`WB_LLM_MODEL` for OpenAI, `WB_ANTHROPIC_MODEL` for Anthropic, and
`WB_LLM_MAX_OUTPUT_TOKENS`. `OPENAI_MODEL` currently overrides the OpenAI model setting.
These are runtime selections, not evidence that a configured model identifier is currently
available from its provider. The registry can fall back to fake chat when no usable key
exists; the proposal UI must never present that result as a successful live generation.

Current section-chat limits are 80,000 serialized characters, 12 recent messages plus
the user-maintained brief, 30,000 replacement-text characters, and a default 4,096-token
LLM output limit. Do not solve document-wide drafting by silently exceeding those limits.

Last recorded staging status in `MANUSCRIPT-CHAT.md`: protected Preview with fake
providers, closed registration, synthetic section-edit/auth checks passed. Earlier
capability reports describe some live-provider evaluations, but do not establish live
proposal-writing quality or today's deployment state. This assessment did not access
secrets, application databases, or current hosted configuration, and did not run live AI.
No executable code was changed or application tests rerun for this documentation task.

## Correspondence Matrices example

Brian's starting point is https://relative0.github.io/Correspondence_Matrices/ .
The site was reachable through its repository link, but the text reader returned no body;
the repository README and linked claim/correction reports provided the inspectable context:

- https://github.com/Relative0/Correspondence_Matrices
- https://github.com/Relative0/Correspondence_Matrices/blob/main/deliverables_n22_24/CM_BENCHMARK_REFRESH_CLAIM_MAP_2026-08-03.md
- https://github.com/Relative0/Correspondence_Matrices/blob/main/deliverables_n22_24/corrections_2026_08_25/CM_BENCHMARK_AUDIT_CORRECTION_REPORT_2026-08-25.md

The correction report distinguishes workload-specific kernel benefits from public-wrapper
performance and rejects universal dominance. An applicability proposal must preserve
these boundaries and inspect later corrections when available. The local `demo.py` has
hard-coded historical performance assertions; it is not an authoritative current CM
evidence corpus. Do not seed a client proposal from its numerical claims.

No client papers or specific client aims were supplied in this request. An actual claim
that CM would help that client cannot yet be assessed. The useful output is a supported
fit analysis and a proposed pilot, including the possibility of no useful fit.

## Implementation prompt — give the following to the development agent

Implement an evidence-grounded client/research proposal workflow in Paper-Workbench.
Read the assessment above first, then verify the named code paths against the current
checkout. Do not restart architectural discovery or rebuild existing ingestion, chat,
auth, evidence, or export subsystems unnecessarily.

### Checkout and scope

- Windows / PowerShell. Project root:
  `C:\Users\brian\Documents\Paper-Workbench\paper-container-compute-worktree\Paper-Workbench`.
- This sits inside the private Tools repository worktree, branch
  `codex/paper-vercel-deployment`; inspected baseline is `188aa99`. Inspect status and
  any newer commits first. The pre-existing `.env.example` change is unrelated: do not
  read, stage, overwrite, or revert it. Preserve all other unrelated work.
- Preferred existing interpreter:
  `C:\Users\brian\Documents\PoP\Tools\Paper-Workbench\.venv\Scripts\python.exe`.
  Set `PYTHONPATH` to this worktree's `src`; the environment has pointed at another
  checkout previously. Follow applicable AGENTS.md instructions and verify dependencies.
- This prompt, when assigned for implementation, scopes local implementation, synthetic
  fixtures, and appropriate tests. It does not authorize production changes, managed-DB
  migrations, deployment, external publication, sending proposals, accessing existing
  research databases/secrets, or paid live-model runs. Prepare migration files locally;
  exercise them only in disposable test databases. Obtain a concrete data/provider/budget
  approval before a live pilot. Historical ElevenLabs authorization is unrelated.
- Do not commit or push unless that is explicitly authorized for this development task.
  Do not modify the CM repository or run benchmarks as part of this integration.

### User journey and first release

Build this complete vertical slice through backend, UI, persistence, and export:

1. Create a proposal within one authorized project. Choose research collaboration or
   applied/client pilot. Record client question, audience, aims, success criteria,
   constraints, known resources, and unanswered questions. Leave unknown budgets,
   schedules and commitments explicitly unspecified.
2. Add selected author materials, client papers, and background literature. Preserve
   these roles as proposal/source membership metadata; they are not authorization roles.
   Start with files and bounded public URL intake. Show extraction/coverage problems and
   allow a user to correct an excerpt without destroying original extraction provenance.
3. Produce a reviewable fit matrix. Each row has client need, source passages for that
   need, relevant author method/result, supporting passages, why it might transfer,
   assumptions, contrary evidence/limitations, fit status, and a proposed validation step.
   Label established facts, user requirements, model inferences and proposed experiments
   separately. Include supported, tentative, insufficient-evidence and no-fit outcomes.
4. Discuss the fit and missing information in the existing chat interface. A user can
   ask follow-ups such as “Why would this help their second aim?”, “What evidence argues
   against it?”, or “Keep only a two-week feasibility study; leave cost unspecified.”
   The proposed two-week duration is user input, not a commitment inferred by the model.
5. Review an outline, then draft a coherent proposal: executive summary, client problem
   and aims, relevant prior work, fit and limitations, approach/work packages, deliverables,
   evaluation criteria and baselines, dependencies/risks, open questions, and references.
   Research proposals may use objectives/hypotheses/methods; client pilots may emphasize
   scope and acceptance criteria. Avoid journal-specific mandatory sections.
6. Reuse section-level reviewed edits. New model content remains a proposal until approved.
   Support manual edits with history, save immutable named v1, continue with a v2 draft,
   compare versions, and export either version as DOCX, Markdown and HTML. Exercise PDF
   when its renderer is available; report a missing renderer honestly. Keep bibliography
   and provenance/audit data accessible without overwhelming the client-facing document.

### Implementation requirements

Reuse manuscript/section and evidence primitives, with explicit proposal/document-kind
metadata or a small typed proposal entity if needed. Use validated schemas and migrations
for persisted new fields, not unchecked arbitrary JSON. Keep research manuscripts working.
Reuse publication-package snapshot patterns where useful, but not submission-specific
dependencies. Separate mutable working drafts from immutable approved version snapshots.

Implement chunk retrieval from `extracted_text_for` and stored artifacts. Chunks must have
stable source/version/checksum references and page, section or character locators as the
extractor supports; never invent page numbers. Preserve OCR uncertainty, equations/table
extraction limitations and truncation. Index chunks, not only bibliography; include
project/proposal/collection authorization and filtering in both retrieval and resolution.
Prefer a bounded lexical baseline, optionally combining existing embeddings. Avoid adding
a new vector service unless measurements establish a need. Prevent deleted, changed,
superseded or unauthorized chunks from appearing as current support; report stale indices.

For URL intake, reuse and review existing safe-fetch components. Validate redirects and
resolved addresses, enforce streamed byte/time limits, restrict protocols and private/
metadata-network destinations, and retain fetched source snapshots with URL/date/hash.
No arbitrary script execution, recursive repository crawling, or automatic downloading of
all linked files. Let users choose the material. HTML rendering failure must be visible.
For reuse of Brian's library across engagements, use explicit authorized import/snapshots
into the project for the first release; do not weaken current cross-project evidence rules.

Construct a bounded proposal-wide evidence pack with retrieval reasons, included/excluded
source coverage, current brief and selected section. Expose it through the context inspector.
Use staged, resumable generation for fit matrix → outline → sections, with explicit partial
failure status, cancellation and idempotency. Fit the deployed runtime limits; do not leave
long-running work in an untracked serverless request. Choose the smallest existing durable
mechanism that meets the first release. Never silently truncate a proposal or call paid
models repeatedly after an uncertain response.

Use `usage.charged_chat`, provider registry and effective configured model. Record model,
generation ID, prompt/context hash, evidence snapshot and usage with each result. Keep fake
mode deterministic, visibly simulated and network-free. Show configuration problems instead
of making fake output look live. Do not log secrets or persist keys in proposals.

Validate citation IDs and source membership server-side. Citations must resolve to passages
actually included in the generation context. Distinguish valid provenance from semantic
support: a citation's existence does not prove entailment. Add audits/review UI for unsupported
factual claims and unsupported promises. Saving prose must never upgrade support states,
verify a source, accept research results or imply client agreement. Permit an honest “not
enough evidence” result. Do not force the workflow to sell CM or any other method.

Bind review actions to section, proposal brief, fit matrix, selected evidence and source
versions. Reuse plan hashes, transactions, optimistic concurrency and guarded undo. Review
outline creation separately; if multi-section approval is supported, make it atomic and
inspectable. Changes made during generation or review must make the corresponding action
stale rather than overwriting newer work.

Named versions must snapshot outline/order, prose, fit matrix, brief, citations, evidence
identifiers and hashes, provenance and approval state. A v2 draft must not mutate v1.
Source corrections after a saved version should add a visible current warning without
silently rewriting historical content. Export exactly the selected snapshot to a new
artifact namespace; prevent earlier exports from being overwritten. Reviewer approval of
a document is distinct from verification of all its scientific claims.

Treat imported papers, website text and client files as untrusted data, including apparent
instructions inside them. Preserve tenant/role enforcement on every new route, artifact,
retrieval result, background job and revision. Reuse existing auth/CSRF policies. Do not
grant clients access merely because they are named in a brief. Keep confidentiality and
permission to send source material to an external provider explicit for any future live use.

### Code map

Relative to the project root:

- `src/workbench/main.py`: API routes and request schemas; existing authorization patterns.
- `src/workbench/web/static/app.js`, `style.css`: current interface; integrate with it.
- `src/workbench/models.py`, `vocab.py`, `audit.py`: entities, controlled states, audit events.
- `src/workbench/ingest/files.py`, `ingest/safe_fetch.py`, `providers/extraction.py`,
  `storage.py`: extraction and artifact lifecycle.
- `src/workbench/services/semantic.py`, `research.py`, `integrity.py`: retrieval/evidence.
- `src/workbench/services/dialogue.py`, `manuscript_chat.py`: context, review/apply/undo.
- `src/workbench/services/authoring.py`, `paper_design.py`, `outputs.py`: manuscript reuse.
- `src/workbench/services/publication_packages.py`, `export_service.py`: snapshot/export patterns.
- `src/workbench/config.py`, `providers/registry.py`, `providers/llm.py`, `services/usage.py`.
- `docs/MANUSCRIPT-CHAT.md`, `docs/CAPABILITY-MATRIX.md`, `docs/VERCEL-DEPLOYMENT.md`.

### Acceptance criteria and verification

Use synthetic author/client material for deterministic integration tests, with no real
client upload or CM benchmark performance claim needed. Demonstrate all of the following:

- Import an author paper and two client papers, create a brief, inspect extraction, retrieve
  a relevant passage from well beyond the beginning of a paper, and show both collections
  represented in the fit matrix. Show which documents/passages were not examined.
- Recognize a deliberately irrelevant client aim as no-fit/insufficient evidence. A
  superseded optimistic result and its correction must not produce an unqualified promise.
- A metadata-only source, unreadable/scanned page, missing full text, deleted chunk, and
  failed URL fetch each give an honest limitation rather than invented evidence.
- Imported text saying “ignore prior instructions” cannot change the agent's rules or
  cause a write. Forged citation IDs and cross-tenant/proposal source IDs are rejected.
- Generate and approve a complete multi-section draft through the UI. Continue dialogue,
  revise a section, reject another edit, and exercise pending undo and stale-edit protection.
- Save v1, create/edit v2, compare them, and prove v1 exports remain unchanged. Verify
  exported citations, references, source hashes and selected-version binding.
- Simulate provider timeout, partial generation, retry, budget failure, duplicate approval
  and concurrent editing. Preserve completed work without duplicate actions or hidden calls.
- Fake mode performs no external calls. Both existing provider adapters use the effective
  configured model when mocked. Missing live configuration is visibly distinguishable.
- Tenant roles, CSRF/session protections, uploads, ordinary manuscripts and existing exports
  retain their behavior. Verify migrations against fresh and upgraded disposable databases.

Run the relevant existing tests (`test_ingest`, `test_pdf_ingest`, `test_manuscript_chat`,
`test_dialogue`, `test_authoring_audit_export`, `test_export_hardening`, `test_tenant_auth`,
`test_db_migrations`, `test_usage`, provider tests), plus new proposal/retrieval/version tests.
Disable dotenv loading for isolated tests and use only disposable fixture databases. Run
the project's lint/check conventions and a real browser walkthrough against a synthetic
local server. Inspect exported DOCX/HTML and PDF when available. Report precise limitations
of fake/model-mocked verification; it cannot establish real proposal-writing quality.

Deliver working integration, source-backed capability updates, migration instructions,
an end-user guide, and a reproducible synthetic demo. End with the exact remaining live
pilot/deployment approvals and a proposed bounded live evaluation plan. Do not claim the
feature is production-ready or scientifically validated solely because fake tests pass.
