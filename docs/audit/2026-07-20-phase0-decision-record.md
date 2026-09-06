# Phase 0 Decision Record — Paper-Workbench

Date: 2026-07-20 · Author: Claude (implementation lead), decisions confirmed by Brian Droncheff where noted.

## Verdict: **GO WITH CONDITIONS**

Build Paper-Workbench as a **standalone, evidence-controlled general research workbench**. Conditions:

1. Live provider calls (OpenAI/Anthropic dialogue, Brave search, scholarly APIs) stay **disabled by default** (`WB_PROVIDER_MODE=fake`); enabling live mode requires the user to supply API keys via environment.
2. Single-user local deployment is the assumed target (Windows, SQLite). Multi-user hosting, collaboration roles, and cloud deployment are deferred until requested (schema keeps `workspace_id` scoping from day one so this is not a rewrite later).
3. Scholarly providers (OpenAlex, Crossref, Semantic Scholar, Unpaywall) are fresh builds added incrementally behind one provider interface; no single provider is load-bearing.
4. WeasyPrint PDF export on Windows requires GTK runtime DLLs; the export pipeline therefore ships with a dependency-free fallback renderer and Markdown/HTML/LaTeX outputs that don't need it.

## Product boundary — DECIDED BY USER (verified)

**Standalone application.** Brian stated (2026-07-20): code may be *copied* from POP Card Studio / Nexus, but the projects are **disjoint** — no runtime integration, no Nexus bridges. All "optional Nexus bridge" items in the original spec are **out of scope**.

## What the surveys established (all verified by direct file inspection; full reports in session transcript)

| Source | Verdict | Take |
|---|---|---|
| `Paper-Workbench/` | empty | Greenfield; this repo is the product. |
| POP Card Studio (`PoP\PoP-Card-Generator-Software\PoPCards`) | healthy, active, tested | Copy: Brave adapter (`providers/brave.py`), `SearchProvider`/`SearchResult` protocol, SSRF-safe fetch + HTML extractor (`modules/research/safe_fetch.py`), evidence-capture pattern, provider registry + fakes, audit/idempotency/jobs patterns, plan→confirm→execute→audit command harness. |
| Nexus (`Documents\Nexus`) | healthy but different domain (outreach ops) | Copy: document renderer (sandboxed Jinja2 + WeasyPrint + minimal fallback), Brave *caching* layer, LLM adapter patterns (OpenAI structured-output with prompt-injection fencing; raw-httpx Anthropic call). |
| CM corpus (`Correspondence_Matrices`, `CM_Computation`, `CM Testing`) | rich, heterogeneous | Demo/eval corpus: incomplete LaTeX manuscript + prior 111 KB draft, 208 KB benchmark driver + hundreds of CSVs + pytest suite, ChatGPT transcripts, notes, publication PNGs. Perfect fixture material. |
| Gaps (nothing to copy anywhere) | — | Multi-turn conversation engine with memory; scholarly API clients; PDF/DOCX *ingestion*; DOCX/LaTeX *output*; embeddings (legacy FAISS skeleton only). These are fresh builds. |

## Architecture decisions (ADRs, condensed)

- **ADR-1 Stack**: Python 3.13 + FastAPI modular monolith, SQLAlchemy 2 + Alembic, Pydantic v2, SQLite (dev/default) with Postgres-compatible schema. Rationale: matches the two donor codebases so copied code stays idiomatic; solo-maintainable; offline-first.
- **ADR-2 Storage**: Relational DB modelling a typed research graph (nodes + edges tables with typed payloads), **not** Neo4j. The query load is lookup/join/provenance-chain, not deep graph traversal; portability and zero-install win. Revisit only if traversal queries demonstrably hurt.
- **ADR-3 Providers**: Every external capability (search, scholarly metadata, LLM text, embeddings, fetch) sits behind a Protocol with a deterministic fake; registry selects fake/live from config. Copied from PoP's registry pattern.
- **ADR-4 Dialogue engine**: New build. Persistent threads + turns in DB; per-turn context assembled from pinned research objects and scoped retrieval (no ever-growing transcript); LLM planner proposes typed actions that go through a plan→confirm→execute→audit pipeline (harness pattern copied from PoP `command` module). Provider-agnostic: OpenAI and Anthropic adapters, fake by default.
- **ADR-5 Evidence rules**: Snippets/search results are discovery, never evidence. Claims carry explicit support states (`research_result`, `external_source`, `interpretation`, `unsupported`, `verification_required`, …); source records carry access level (`metadata_only` … `full_text_user_supplied`) and license/acquisition provenance. Enforced at the schema level, surfaced in UI/exports.
- **ADR-6 Export**: Canonical manuscript is structured (sections + claim references) in DB; renderers produce Markdown/LaTeX/HTML always, PDF via WeasyPrint when GTK present, DOCX via python-docx later. Never PDF-as-source.

## Risk register

| Risk | Mitigation |
|---|---|
| Scope is enormous (13-point definition of done) | Vertical slices; continuation ledger below; each slice leaves repo runnable + tested. |
| LLM hallucinated citations/claims | Structured outputs referencing object IDs only; validation before persistence; claim-support states; citation resolution required before a reference is accepted. |
| Prompt injection via ingested documents/web pages | Untrusted content fenced (Nexus pattern); tools only callable via typed registry; retrieval scoped per project. |
| Provider terms (Brave ≠ full-text license) | Access-level + license fields mandatory on sources; full text stored only when user-supplied/openly licensed; excerpt+hash retention otherwise. |
| WeasyPrint/GTK on Windows | Fallback renderer + non-PDF formats first-class. |
| Solo-user data loss | SQLite file + artifact store under one data dir; export/import of whole projects as ZIP with checksums (PoP pattern). |

## Blocking decisions left with the user (safe defaults chosen meanwhile)

1. **LLM provider + key** for live dialogue (default: fake mode; both OpenAI and Anthropic adapters shipped). The spec says "converse with GPT" — OpenAI assumed primary.
2. **Brave API key** for live discovery (default: fake mode).
3. Whether any corpus files should NOT be ingested into demo fixtures (default: only CM materials listed above, read-only, copies not moves).

## Phased plan and continuation ledger

- **P1 Foundation (this session)**: repo scaffold, config, DB schema + migrations for workspace/project/research-object/source/excerpt/claim/edge/thread/turn/audit, provider protocols + fakes, vendored Brave adapter + safe_fetch, pytest suite, runnable API.
- **P2 Research-first vertical slice**: ingest CM materials (Markdown/CSV/TXT/LaTeX first; PDF via pypdf), result cards, grounded multi-turn dialogue (fake + live adapters), accepted-suggestion → task/object, minimal web or CLI surface.
- **P3 Literature core**: OpenAlex + Crossref adapters, dedup/canonicalization, literature matrix, saved searches, novelty map states.
- **P4 Authoring core**: paper candidates, argument planner, manuscript sections with claim refs, citation integrity audit.
- **P5 Integrity & reproducibility**: audits, adversarial review mode, eval harness.
- **P6 Publishing**: venue profiles, export bundles (MD/LaTeX/HTML/PDF/DOCX), submission package.

Ledger status (2026-07-20, end of second session):
- **P1 DONE** — schema, evidence rules, dialogue engine, providers+fakes, server smoke-tested.
- **P2 DONE** — file ingestion (md/txt/tex/csv/pdf) with artifact copies + extraction labeling; live HTTP extraction provider (SSRF-guarded); live OpenAI (gpt-4o via OPENAI_MODEL env) and Brave verified with user-supplied keys (`scripts/verify_live.py`).
- **P3 DONE** — OpenAlex + Crossref adapters (normalized ScholarlyWork, DOI canonicalization, dedup; live-verified via `scripts/verify_scholarly.py`), saved searches (protocol_note defaults "exploratory", never "systematic"), explicit import (metadata/abstract-only, dedup by DOI), screening states + literature matrix, novelty/contribution map requiring coverage notes.
- **P4 DONE** — paper candidates (16 types, 7 structures), manuscripts, ordered sections with validated claim references, argument-map purposes/word budgets.
- **P5 DONE** — deterministic audits (claim coverage, verification debt, unaccepted-AI citation, unverified sources, dangling refs, unreferenced quantitative prose) + LLM skeptical review persisting objections as open AI-suggested notes.
- **P6 DONE (core)** — export to MD/LaTeX/HTML/DOCX + BibTeX + provenance manifest (sha256, access levels, audit findings at export). PDF deferred (WeasyPrint/GTK on Windows); LaTeX compiles with any standard toolchain.
- **Alembic adopted** — initial migration `115f9e0dd0da` covers full schema; verified against fresh DB. Tests still bootstrap via create_all for speed.
- **End-to-end live proof**: `scripts/golden_path.py` — ingest real CM corpus → grounded live-GPT dialogue → OpenAlex import/screening → contribution map → candidate → manuscript → audit → live skeptical review (3 objections) → export bundle.
- **Expansion slice DONE (2026-07-20, session 3)** — everything previously deferred except noted:
  - **Web UI**: dependency-free SPA at `/ui` (vanilla JS/CSS, light/dark, a11y states); all six tabs (Objects/Sources/Claims/Literature/Dialogue/Manuscripts) verified in-browser including a live GPT-4o dialogue turn rendered with model label and approval-gated action panel.
  - **Semantic Scholar + Unpaywall adapters** (Unpaywall = OA-location lookup, explicitly not a full-text license); **embeddings/semantic retrieval** (fake hash vectors offline / OpenAI text-embedding-3-small live; project-scoped; results labeled kind="similarity", never evidence).
  - **Venue profiles** with rules provenance + human-verify gate; compliance audit downgrades to advisory (info) findings until verified.
  - **Collaboration roles** (users/project_members, reviewer<editor<coauthor<owner, local API-key trust model — honest scope: not hardened multi-tenant auth; grace mode when a project has no members).
  - **PDF export** (dependency-free deterministic MinimalPdf renderer — fallback quality; LaTeX remains the typeset path) and **JATS XML** (structural, not DTD-validated).
  - **Cross-project research memory**: unpublished-results finder, result-usage tracing, saved-search rerun, workspace-scoped title search (never crosses workspaces).
  - **Eval harness**: 8 labeled scenarios scoring the deterministic audit layer — precision/recall 1.00 on all 7 finding codes (docs/eval-report.md; explicitly does NOT measure LLM quality).
  - Migration `87d0b44a3f39` (embeddings/users/members/venues). 40 offline tests green.
- **Hardening slice DONE (2026-07-20, session 4)** — all five items previously listed as deferred:
  - **Auth**: bcrypt passwords, HS256 workbench JWTs (short-lived, fail-closed on default secret), OIDC login behind a verifier (live JWKS RS256/ES256; offline FakeOidc), api-key bearer path; `/auth/register|login|oidc/login|me`. Role enforcement wired into object/section/member routes, gated on `WB_AUTH_REQUIRED` (default off → local single-user stays frictionless). Migration c1d55f7b04f1.
  - **DTD-validated JATS**: bundled JATS-subset DTD validated with lxml (honest scope — the element subset we emit, not full JATS 1.3; `dtd_path=` accepts the official DTD). Validation result recorded in the export manifest. lxml now a core dep.
  - **Typeset PDF**: WeasyPrint renderer behind a capability probe that catches the GTK `OSError` (not just ImportError). `pdf_renderer=auto|weasyprint|minimal`; `auto` falls back to the deterministic renderer when GTK is absent (as on this box) and records which renderer ran. WeasyPrint is an optional `[pdf]` extra.
  - **LLM-output-quality evals**: provider-agnostic harness (evals_llm.py) scoring grounding, hallucinated-citation, injection-resistance, action-safety, abstention. Deterministic on the fake (CI); **live gpt-4o run: 6/6 checks 1.00** after the eval surfaced two prompt-compliance gaps and drove a system-prompt fix (docs/llm-eval-report.md). Honestly labeled as a regression signal, not a correctness certificate.
  - **Submission tracking**: audited state machine (drafting→submitted→under_review→revision_requested→resubmitted→accepted/rejected/withdrawn) with append-only history and response-to-reviewers revisions; migration 847bd078d7c4. UI Submissions tab + login added.
  - 59 offline tests + both eval harnesses green.
- **Still deferred (smaller/lower-value)**: full JATS 1.3 DTD validation, PDF via a
  typeset engine on this box (needs GTK install), hardened multi-tenant deployment
  (current auth is single-machine trust), OCR/layout-aware extraction, citation-graph
  traversal, CRediT assistance, and a reproducible compute runner. None block local use.

Ledger status (2026-09-06, source-integrity and maintenance slice):
- **Repository ownership clarified** — `Paper-Workbench/` in the private Tools monorepo is
  authoritative; the public `btheorystartups/Paper-Workbench` repository is its one-way
  standalone mirror.
- **Public CI added** — Python 3.13, fake-provider mode, Ruff on `src/`, and the complete
  offline pytest suite. The workflow is inert inside the nested Tools path and becomes a
  root workflow when the subtree is published.
- **Guarded mirror publisher added** — the Tools-level PowerShell script defaults to a
  dry run, refuses uncommitted Paper-Workbench changes, audits tracked paths for common
  secret/local-data patterns, verifies exact tree equality, checks for a public-main race,
  and only writes remotely with explicit `-Push`.
- **Duplicate-source review added** — deterministic candidates use controlled exact DOI,
  normalized-title, and title/year signals. Conflicting identifiers or years are explicit
  blockers. Merging is never automatic: an editor supplies a human review note against a
  current plan hash. Excerpts, claim-evidence links, compatible literature records, thread
  pins, access metadata, and a full pre-merge snapshot are preserved; embeddings are
  invalidated and the operation is audited.
- **Verification** — 108 offline tests and Ruff green; no provider calls made.
