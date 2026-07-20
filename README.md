# Paper-Workbench

An **evidence-controlled, general-purpose research workbench**: organize any kind of research
as a provenance-preserving research graph, converse naturally with an AI about meaning and
direction, and — when (and only when) publication is warranted — turn selected research into
defensible manuscripts. Not a paper generator: paper creation is optional and downstream.

Standalone by design. Selected components were copied from (and are now owned independently
of) POP Card Studio and Nexus; this repo imports nothing from those projects.

## Status (P1 Foundation — 2026-07-20)

Implemented and tested (offline, fake providers):
- Canonical research graph: workspaces, projects, research objects (typed kinds), edges,
  sources (access level + license + acquisition mandatory), checksummed excerpts with
  locators, claims with enforced support states and claim→evidence links.
- Research dialogue engine: persistent threads, pinned context, fenced untrusted content,
  full AI provenance per turn, and a propose → human-approve → execute → audit pipeline
  (plan-hash bound; speculation is never silently promoted to fact).
- Providers behind protocols with deterministic fakes (default `WB_PROVIDER_MODE=fake`,
  zero network): Brave Search (with response cache), OpenAI and Anthropic chat adapters,
  SSRF-safe URL validation + HTML metadata extraction.
- Audit events written in-transaction for every consequential mutation.

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
