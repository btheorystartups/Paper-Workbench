# Paper-Workbench Capability Matrix

Honest status of every capability against the original megaprompt. Legend:
**Implemented** (end-to-end, tested) · **Partial** (works, with documented limits) ·
**Simulated** (fake by default; real path exists behind a key) · **Planned** ·
**Out of scope** (deliberately excluded).

Last updated 2026-07-21. Tests: 65 offline, green. Live providers (OpenAI gpt-4o, Brave,
OpenAlex, Crossref) verified with the user's keys. Code: `src/workbench/`.

## Core model & platform

| Capability | Status | Evidence / notes |
|---|---|---|
| Canonical research graph (objects, edges, sources, excerpts, claims, threads, turns) | Implemented | `models.py`, `services/research.py`; 15+ tables |
| Controlled state vocabularies (claim support, result strength, novelty, source access) | Implemented | `vocab.py`; enforced in services, never collapsed in UI/export |
| Workspace/project isolation + soft delete + timestamps | Implemented | `workspace_id`/`project_id` scoping on every row |
| Provenance that survives export | Implemented | export manifest: checksums, access levels, audit findings, AI provenance |
| Schema migrations | Implemented | Alembic; `db.upgrade_to_head()` runs at startup; 4 migrations, reversibility checked |
| Audit-in-transaction | Implemented | `audit.py`; every consequential mutation writes an AuditEvent |
| Provider abstraction + offline fakes (default) | Implemented | `providers/`, `WB_PROVIDER_MODE=fake` → zero network |

## 1. Natural-language research dialogue & direction engine

| Capability | Status | Notes |
|---|---|---|
| Persistent, pinned-context threads with per-turn provenance | Implemented | `services/dialogue.py`; context assembled from pinned objects/sources, not raw transcript |
| Grounded replies citing context; distinguishes evidence vs inference | Implemented | live gpt-4o 6/6 on the LLM eval; `[ctx:id]` citation contract |
| Prompt-injection resistance (fenced untrusted content) | Implemented | eval `injection_resistance` = 1.00 live; tested |
| Propose → human-approve → execute → audit (plan-hash bound) | Implemented | speculation never auto-promoted; `test_dialogue.py`, `test_api.py` |
| Explicit modes (explore/explain/challenge/compare/plan/act) | Partial | modes not a separate switch; skeptical-review is a distinct mode (audits.py) |
| Branchable threads | Planned | threads persist; branching not yet modeled |

## 2. Project intake & research-object registry

| Capability | Status | Notes |
|---|---|---|
| Ingest md/txt/tex/bib/csv/pdf → sources with provenance, originals preserved | Implemented | `ingest/files.py`; content-addressed artifact copies, extractor+confidence labeled |
| Result cards (plain + formal, strength, provenance) | Implemented | research objects with typed `body` |
| Duplicate / contradiction / weak-support detection | Partial | audits flag verification debt, unverified sources, unaccepted-AI citation; no auto dupe-merge UI |
| OCR / layout-aware PDF extraction | Partial | pypdf text extraction (labeled "lossy"); no OCR/layout model |
| Bulk tagging / version comparison | Planned | single-object versioning via edges; no bulk UI |

## 3. General research & Correspondence-Matrix method profiles

| Capability | Status | Notes |
|---|---|---|
| Method-neutral core (any research type) | Implemented | typed object kinds + JSON bodies; no method hard-coded |
| Correspondence-Matrix as demo corpus | Implemented | `demo.py`, `golden_path.py` ingest the real CM materials |
| Reproducible compute environment (isolated runs, pinned env, seeds) | Out of scope | not built; CM computation lives in the separate CM repos |
| Result-status labeling (proved/empirical/computational/heuristic/conjectured/AI) | Implemented | `ResultStrength` vocab |

## 4. Paper-design & decomposition wizard

| Capability | Status | Notes |
|---|---|---|
| Paper candidates (16 types, 7 structures) with included/excluded, risks, missing-work | Implemented | `services/authoring.py`; not forced into IMRaD |
| Several genuinely different candidates auto-generated | Partial | candidates are created/edited; multi-candidate LLM generation not automated |

## 5. Evidence discovery & literature workspace

| Capability | Status | Notes |
|---|---|---|
| Provider adapters: Brave, OpenAlex, Crossref, Semantic Scholar, Unpaywall | Implemented | `providers/brave.py`, `providers/scholarly.py`; normalized, deduped by DOI |
| Saved searches, exploratory-by-default (never auto-"systematic") | Implemented | `services/literature.py` |
| Screening states + literature matrix | Implemented | `LiteratureEntry`, `literature_matrix()` |
| Semantic / embedding retrieval (similarity ≠ evidence) | Simulated→Implemented | `services/semantic.py`; fake hash vectors offline, OpenAI embeddings live |
| Citation-graph / backward-forward exploration | Partial | cited-by counts captured; no graph-walk UI |
| Systematic-review protocol (flow counts, screening rules) | Out of scope | only exploratory/narrative discovery, honestly labeled |

## 6. Novelty / contribution / gap assessment

| Capability | Status | Notes |
|---|---|---|
| Provisional contribution map with mandatory coverage note | Implemented | `assess_contribution()`; novelty states from vocab; never asserts novelty without coverage |

## 7. Claim-level evidence ledger & citation integrity

| Capability | Status | Notes |
|---|---|---|
| Every claim: support state, evidence links, locators, access level | Implemented | `services/research.py`; cross-project evidence rejected |
| Block/flag missing excerpts, unresolved sources, retractions, unaccepted-AI | Implemented | `services/audits.py`; eval P/R 1.00 on 7 codes |
| Retraction/correction ingestion feed | Partial | `integrity_note` field + audit flag; no automated retraction-watch feed |

## 8. Argument planner & manuscript studio

| Capability | Status | Notes |
|---|---|---|
| Sections with purpose, claim references, word budgets | Implemented | `authoring.add_section`; claim refs validated |
| Controlled AI modes; structured outputs referencing object IDs | Implemented | dialogue actions + skeptical review; outputs grounded in claims |
| Coauthor/reviewer/editor roles, invitation, permissions | Partial | `services/security.py` + auth; local trust model (not hardened multi-tenant) |
| CRediT / authorship-order assist | Planned | not built |

## 9. Figures, tables & supplements

| Capability | Status | Notes |
|---|---|---|
| Figure/table object kinds + unreferenced/stale detection | Partial | kinds exist; audit flags quantitative prose without claims |
| Canonical data→figure rendering, captions, alt text, color-blind checks | Planned | not built (no plotting engine wired) |

## 10. Journal / audience / submission adaptation

| Capability | Status | Notes |
|---|---|---|
| Venue profiles with rules provenance + human-verify gate | Implemented | `services/venues.py`; compliance findings advisory until verified |
| Venue compliance audit (word/section/abstract/AI-disclosure) | Implemented | `audit_venue_compliance` |
| Reporting-guideline profiles (PRISMA etc.) | Planned | venue rules are extensible; named checklists not shipped |

## 11. Validation & adversarial review

| Capability | Status | Notes |
|---|---|---|
| Composable integrity audits (claims, sources, sections, manuscript) | Implemented | `services/audits.py` |
| Skeptical-review mode (objections as open AI-suggested notes) | Implemented | `audits.skeptical_review` |
| Evaluation harnesses with precision/recall | Implemented | audit evals (`evals.py`, P/R 1.00) + LLM-quality evals (`evals_llm.py`, live 6/6) |

## 12. Export & publishing pipeline

| Capability | Status | Notes |
|---|---|---|
| Markdown, LaTeX, HTML, DOCX, BibTeX | Implemented | `services/export_service.py` |
| PDF | Implemented (fallback) / Partial (typeset) | deterministic PDF always; WeasyPrint typeset when GTK present (absent on this box → auto-fallback, recorded in manifest) |
| JATS XML, DTD-validated | Implemented | validated against bundled JATS-subset DTD via lxml; `dtd_path=` for full JATS 1.3 |
| Provenance manifest (checksums, access levels, audit findings, renderer, JATS validation) | Implemented | `manifest.json` |
| Cover letter / response-to-reviewers / declarations bundle | Partial | response-to-reviewers via submissions; other declaration docs not templated |
| Alternative outputs (conf abstract, poster, plain-language, teaching, graphical-abstract) | Implemented | `services/outputs.py`; live gpt-4o verified |

## 13. Research memory & portfolio

| Capability | Status | Notes |
|---|---|---|
| Unpublished/uncited-result finder, result-usage tracing, saved-search rerun, workspace search | Implemented | `services/portfolio.py`; never crosses workspace boundary |
| Submission tracking (state machine, history, revisions) | Implemented | `services/submissions.py`; migration 847bd078d7c4 |

## Cross-cutting: security, auth, ops

| Capability | Status | Notes |
|---|---|---|
| Auth: bcrypt passwords, JWTs, OIDC login | Implemented | `auth.py`; off by default, enforced when `WB_AUTH_REQUIRED=true` |
| Role enforcement (reviewer<editor<coauthor<owner) | Implemented | wired into object/section/member routes; gated on auth |
| SSRF-safe fetching, secret-as-env, no secret logging | Implemented | `ingest/safe_fetch.py`, `config.py` |
| Web UI (7 tabs + login + submissions) | Implemented | `web/static/`; browser-verified incl. live dialogue |
| Hardened multi-tenant production deployment / real IdP integration | Out of scope | single-machine trust model; documented migration path |
| Cost budgets / token metering / cancellation | Partial | usage recorded in turn provenance; no budget ceiling UI |
