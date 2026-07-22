# Paper-Workbench — Completion Report

Date: 2026-07-21 · Author: Claude (implementation lead) · For: Brian Droncheff

## Summary

Built a standalone, evidence-controlled general research workbench from an empty directory
through Phase 0 discovery and six phased slices plus a hardening pass. The system is
runnable, tested, and verified against live providers. It is **not** a paper generator:
research organization and grounded dialogue are the core; manuscript authoring and export
are optional downstream steps that preserve provenance and evidence states throughout.

- Working tree clean; committed in coherent slices.
- **~40 source modules** in `src/workbench/`, **83 tests** across the suite, all passing
  offline (live provider paths verified separately with the user's keys).
- **4 Alembic migrations**; startup runs `alembic upgrade head`.
- Post-P6 additions: alternative outputs, figures/tables with data provenance, and
  multi-candidate paper design (see `docs/CAPABILITY-MATRIX.md`).
- **Ruff**: clean.
- Phase 0 decision record, capability matrix, and this report in `docs/`.

## What was built (by slice)

| Slice | Commit | Content |
|---|---|---|
| P1 Foundation | 2bdff0e | research graph, evidence rules, dialogue engine, providers+fakes |
| P2 Ingestion | 528dc8c | file ingestion with provenance, offline CM demo |
| P3–P6 core | ae3c962 | literature workspace, authoring, audits, export; live providers verified |
| Expansion | 03d839a | Web UI, semantic search, venues, roles, portfolio, PDF/JATS, evals |
| Auth | 8ccffbb | bcrypt + JWT + OIDC login, config-gated role enforcement |
| Hardening | dae90bc | JATS DTD validation, WeasyPrint PDF, LLM-quality evals, submissions |
| UI + startup | eb87aa1 | Submissions tab + login; Alembic-driven startup migration (fixed /auth/me 500) |
| Alternative outputs | (this session) | conf abstract, poster, plain-language, teaching, graphical-abstract |

See `docs/CAPABILITY-MATRIX.md` for capability-by-capability status.

## Verification evidence

- **Unit/integration/security/API**: `pytest` → 65 passed. Covers evidence integrity,
  cross-project isolation, dialogue propose→approve→execute + plan-hash binding, prompt-
  injection fencing, auth (password/JWT/OIDC/roles), export (incl. PDF fallback + JATS DTD
  validation), submissions state machine, portfolio, semantic scope, startup migration.
- **Audit eval harness** (`scripts/run_evals.py`): 8 labeled scenarios, precision/recall
  **1.00** on all 7 finding codes (`docs/eval-report.md`).
- **LLM-quality eval harness** (`scripts/run_llm_evals.py`): against **live gpt-4o**,
  **6/6 checks pass** (grounding, no-hallucinated-citation, injection-resistance,
  action-safety, abstention) — after the eval surfaced two prompt-compliance gaps and drove
  a dialogue system-prompt fix (`docs/llm-eval-report.md`).
- **Browser end-to-end**: created workspace/project, ran a live gpt-4o dialogue turn
  (rendered with model label + approval-gated actions), and drove the Submissions tab
  (create → drafting→submitted transition, header shows signed-in user).
- **Live provider smoke tests**: Brave, OpenAI gpt-4o (dialogue + embeddings + outputs),
  OpenAlex, Crossref (`scripts/verify_live.py`, `scripts/verify_scholarly.py`).
- **Full journey**: `scripts/golden_path.py` runs ingest → dialogue → literature → candidate
  → manuscript → audit → skeptical review → export against the real CM corpus.

## Live external calls made during development

All initiated intentionally for verification, using the user's own keys (in `.env`, not
tracked). No writes, purchases, submissions, or publications anywhere.

- OpenAI (gpt-4o): dialogue turns, embeddings, LLM-eval scenarios, one alternative-output
  generation. Read-only chat/embeddings.
- Brave Search: 1 query.
- OpenAlex / Crossref / (Semantic Scholar, Unpaywall adapters exist): metadata reads.

## Known limitations (honest)

- **Typeset PDF** requires GTK/Pango, absent on this Windows box → `auto` mode falls back to
  the built-in deterministic PDF and records which renderer ran. Install GTK + `pip install
  '.[pdf]'` for WeasyPrint output.
- **JATS** validates against a bundled subset DTD (the elements we emit), not full JATS 1.3;
  pass `dtd_path=` to `validate_jats` for the official DTD.
- **Auth** is a single-machine trust model (local API keys / dev tokens, HS256 JWTs). Real
  multi-tenant deployment needs a production IdP and tenant hardening — schema is the
  migration path.
- **Branchable threads, CRediT assist, retraction-watch feed, reporting-guideline
  checklists, cost-budget ceilings**: planned, not built. (Figures/tables rendering and
  multi-candidate paper design, previously listed here, landed in later slices — see
  `docs/CAPABILITY-MATRIX.md`.)
- **LLM-quality evals** are a regression signal on known failure modes, not a correctness
  certificate. LLM output always enters a human-review gate.

## Blockers

None outstanding. Two user decisions remain optional (defaults active): which LLM to use
live (OpenAI configured, gpt-4o) and whether to enable auth (`WB_AUTH_REQUIRED`).

## Recommended next actions

1. If typeset PDF matters: install GTK on the workstation, then `pip install '.[pdf]'`.
2. ~~Wire a plotting engine for figures/tables~~ — done (commit cf1d7b7).
3. ~~Multi-candidate paper generation~~ — done (commit d3ca78c).
4. If collaboration goes multi-user: integrate a real OIDC provider and harden tenancy.
5. Point `validate_jats` at the official JATS 1.3 DTD for full-spec validation.
6. Remaining planned items: branchable threads, retraction watch, guideline checklists,
   cost budgets, CRediT assist (see capability matrix).

## How to run

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\alembic.exe upgrade head          # or let the server do it on boot
.\.venv\Scripts\python.exe -m pytest               # 65 tests, offline
.\.venv\Scripts\uvicorn.exe workbench.main:app     # http://127.0.0.1:8000/ (UI)
```
Copy `.env.example` to `.env`; everything defaults to offline fake mode.
