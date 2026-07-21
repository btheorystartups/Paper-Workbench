# Paper-Workbench

An **evidence-controlled, general-purpose research workbench**: organize any kind of research
as a provenance-preserving research graph, converse naturally with an AI about meaning and
direction, and — when (and only when) publication is warranted — turn selected research into
defensible manuscripts. Not a paper generator: paper creation is optional and downstream.

Standalone by design. Selected components were copied from (and are now owned independently
of) POP Card Studio and Nexus; this repo imports nothing from those projects.

## Status (P1–P6 core — 2026-07-20)

Implemented and tested (33 offline tests; live providers verified with user keys):
- **Research graph** (P1): workspaces, projects, typed research objects, edges, sources
  (access level + license + acquisition mandatory), checksummed excerpts with locators,
  claims with enforced support states and claim→evidence links; audit-in-transaction.
- **Dialogue engine** (P1/P2): persistent threads, pinned context, fenced untrusted
  content, full AI provenance per turn, propose → human-approve → execute pipeline
  (plan-hash bound). Live OpenAI (model from `OPENAI_MODEL`) and Anthropic adapters.
- **Ingestion** (P2): md/txt/tex/bib/csv/pdf → content-addressed artifact copies,
  honestly-labeled extraction; SSRF-guarded live web extraction.
- **Literature core** (P3): OpenAlex + Crossref adapters (normalized, DOI-canonicalized,
  deduped), saved searches (exploratory by default — never auto-"systematic"), explicit
  imports, screening states + literature matrix, novelty map with mandatory coverage notes.
- **Authoring** (P4): paper candidates (16 types / 7 structures), manuscripts, ordered
  sections whose claims are validated references into the claim ledger.
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
- **Figures & tables**: rendered from content-hashed datasets (matplotlib, colour-blind-safe
  palette); records the source data hash so figures go **stale** if the data changes;
  grounded, review-gated captions; export bundles them into `supplements/` with provenance.
- **Export hardening**: JATS validated against a bundled DTD (lxml); PDF via WeasyPrint when
  its GTK libraries are present, else the deterministic fallback (the manifest records which).
- **LLM-quality evals** (`scripts/run_llm_evals.py`): grounding, injection-resistance,
  hallucinated-citation, action-safety, abstention — 6/6 against live gpt-4o
  (docs/llm-eval-report.md). A regression signal, not a correctness certificate.

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
.\.venv\Scripts\python.exe -m pytest              # 19 tests, fully offline
.\.venv\Scripts\uvicorn.exe workbench.main:app --reload   # API on :8000, docs at /docs
```

## Configuration

Copy `.env.example` to `.env`. Everything defaults to offline fake mode. Live providers
require both `WB_PROVIDER_MODE=live` and the relevant key; keys live only in the
environment, never in the database, never in logs.

## Known limitations (P1)

- Schema bootstraps via `create_all`; Alembic migrations arrive with the first post-P1
  schema change.
- No web UI yet (API + /docs only); ingestion of files (PDF/LaTeX/CSV/Markdown) lands in P2.
- Live extraction provider (web page fetch) is intentionally still fake.
- Single-user local deployment; `workspace_id` scoping is in the schema for later multi-user.
