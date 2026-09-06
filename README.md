# Paper-Workbench

An **evidence-controlled, general-purpose research workbench**: organize any kind of research
as a provenance-preserving research graph, converse naturally with an AI about meaning and
direction, and — when (and only when) publication is warranted — turn selected research into
defensible manuscripts. Not a paper generator: paper creation is optional and downstream.

Standalone by design. Selected components were copied from (and are now owned independently
of) POP Card Studio and Nexus; this repo imports nothing from those projects.

Public mirror: <https://github.com/btheorystartups/Paper-Workbench>.

## Status (P1–P6 + expansion + hardening — 2026-09-06)

Implemented and tested (144 offline tests; live providers verified separately with user keys):
- **Research graph** (P1): workspaces, projects, typed research objects, edges, sources
  (access level + license + acquisition mandatory), checksummed excerpts with locators,
  claims with enforced support states and claim→evidence links; audit-in-transaction.
- **Dialogue engine** (P1/P2): persistent threads, pinned context, fenced untrusted
  content, full AI provenance per turn, propose → human-approve → execute pipeline
  (plan-hash bound). Live OpenAI (model from `OPENAI_MODEL`) and Anthropic adapters.
- **Ingestion** (P2): md/txt/tex/bib/csv/pdf → content-addressed artifact copies,
  honestly-labeled extraction; PDFs use layout-aware text extraction plus optional local
  OCR for low-text pages, with controlled page states and mandatory review provenance;
  SSRF-guarded live web extraction.
- **Literature core** (P3): OpenAlex + Crossref adapters (normalized, DOI-canonicalized,
  deduped), saved searches (exploratory by default — never auto-"systematic"), explicit
  imports, screening states + literature matrix, novelty map with mandatory coverage notes.
- **Citation graph**: project-scoped backward/forward discovery with canonical DOI/provider
  identities, controlled resolution/review states, append-only provider observations,
  bounded traversal, import-time resolution, and human review. Citation links remain
  discovery-only and never create sources, claims, or evidence automatically.
- **Source integrity**: project-scoped duplicate candidates from controlled DOI/title/year
  signals; conflicts block merging; every merge requires a human note and current plan hash,
  preserves evidence/literature provenance, records an audit event, and invalidates embeddings.
- **Authoring** (P4): paper candidates (16 types / 7 structures), manuscripts, ordered
  sections whose claims are validated references into the claim ledger.
- **CRediT authorship**: project contributors, the 14 controlled CRediT roles, explicit
  proposed/confirmed/disputed/declined review states, and snapshot-bound authorship-order
  proposals. A deterministic discussion draft is available offline, but only a current
  human-approved order appears in manuscript exports.
- **Audits** (P5): claim-coverage/verification-debt/unverified-source/dangling-ref/
  unreferenced-numbers checks + LLM skeptical review (objections persist as open,
  AI-suggested notes).
- **Export** (P6): Markdown, LaTeX, HTML, DOCX, BibTeX + provenance manifest with sha256
  checksums, source access levels, and audit findings at export time. Export ≠ submission.

- **Web UI**: served at `/ui` (dependency-free SPA; light/dark; shows provider mode,
  AI-suggested/simulated badges, support states, approval-gated AI actions).
- **Expansion**: Semantic Scholar + Unpaywall adapters; project-scoped semantic search
  (similarity ≠ evidence); venue profiles with verify-gated compliance audits;
  collaboration roles (local trust model); PDF (fallback renderer) + JATS export;
  cross-project memory (unpublished results, usage tracing, saved-search rerun);
  audit eval harness (docs/eval-report.md — precision/recall 1.00 on 7 codes).

- **Auth** (optional, off by default): bcrypt passwords + short-lived JWTs + OIDC login;
  role enforcement (reviewer<editor<coauthor<owner) activates only when
  `WB_AUTH_REQUIRED=true`. Endpoints under `/auth/*`.
- **Submission tracking**: audited state machine (drafting → submitted → under review →
  revision requested → resubmitted → accepted/rejected/withdrawn) with response-to-reviewers.
- **Publication packaging**: versioned local package plans with controlled cover-letter and
  declaration review states, snapshot-bound human approval, staleness checks, venue findings,
  response-to-reviewers, manuscript outputs, and a checksummed ZIP manifest. Building a
  package never transmits it or marks it submitted.
- **Reproducible compute**: immutable plans bind an ingested Python script, input artifacts,
  arguments, timeout, seed, interpreter, and installed-package fingerprint. Execution needs
  hash-bound approval plus a separate confirmation; captured logs/outputs remain explicitly
  unreviewed until a human verifies and promotes a controlled result. No shell, package
  install, live provider, or automatic claim creation is involved.
- **Figures & tables**: rendered from content-hashed datasets (matplotlib, colour-blind-safe
  palette); records the source data hash so figures go **stale** if the data changes;
  grounded, review-gated captions; export bundles them into `supplements/` with provenance.
- **Export hardening**: JATS validated against a bundled DTD (lxml); PDF via WeasyPrint when
  its GTK libraries are present, else the deterministic fallback (the manifest records which).
- **LLM-quality evals** (`scripts/run_llm_evals.py`): grounding, injection-resistance,
  hallucinated-citation, action-safety, abstention — 6/6 against live gpt-4o
  (docs/llm-eval-report.md). A regression signal, not a correctness certificate.
- **Maintenance**: public-mirror CI runs Ruff and the offline test suite on Python 3.13;
  the parent Tools repository includes a guarded, dry-run-by-default subtree publisher.

Demos: `python -m workbench.demo` (offline) · `python -X utf8 scripts/golden_path.py`
(full live journey) · `scripts/verify_live.py`, `scripts/verify_scholarly.py` (providers) ·
`scripts/run_evals.py` (audit evals) · `scripts/run_llm_evals.py` (LLM evals).
Migrations: `alembic upgrade head`.
UI: `uvicorn workbench.main:app` then open http://127.0.0.1:8000/ (redirects to /ui).

See `docs/audit/2026-07-20-phase0-decision-record.md` for the go/no-go record, ADRs,
risk register, and the phased roadmap/continuation ledger.

## Run

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest              # 144 tests, fully offline
.\.venv\Scripts\uvicorn.exe workbench.main:app --reload   # API on :8000, docs at /docs
```

## Configuration

Copy `.env.example` to `.env`. Everything defaults to offline fake mode. Live providers
require both `WB_PROVIDER_MODE=live` and the relevant key; keys live only in the
environment, never in the database, never in logs.

## Backup / portability

`POST /projects/{id}/export` writes a checksummed ZIP bundle (every project row + the
content-addressed artifact files it references) under `data/exports/projects/`.
`POST /projects/import` restores a bundle on any machine (refuses to overwrite an existing
project; verifies every checksum first; rewrites artifact paths to the local data dir).

## Known limitations

- Typeset PDF needs GTK (WeasyPrint); without it the deterministic fallback renderer runs
  and the manifest records which. LaTeX is the publication-quality path.
- JATS validates against a bundled subset DTD by default. Set `WB_JATS_DTD_PATH` to the
  local entry-point file from an official JATS 1.3 DTD distribution for full validation;
  the app never downloads a DTD at runtime.
- Auth is a single-machine trust model; hardened multi-tenant deployment is out of scope.
- Local compute is reproducibility capture, not a security sandbox: network, filesystem, and
  descendant-process isolation are explicitly unenforced. Run only inspected, trusted scripts;
  use a future container-backed executor for enforceable isolation.
- Local OCR is optional: install `.[ocr]` plus Tesseract language data. Without it, automatic
  PDF ingestion retains layout text and explicitly labels low-text pages unresolved; forced
  OCR fails closed. OCR output is always `ocr_unreviewed`/`mixed_unreviewed`.
- See `docs/CAPABILITY-MATRIX.md` for the full honest status per capability.
