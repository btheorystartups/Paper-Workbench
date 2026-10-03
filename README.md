# Paper-Workbench

An **evidence-controlled, general-purpose research workbench**: organize any kind of research
as a provenance-preserving research graph, converse naturally with an AI about meaning and
direction, and — when (and only when) publication is warranted — turn selected research into
defensible manuscripts. Not a paper generator: paper creation is optional and downstream.

Standalone by design. Selected components were copied from (and are now owned independently
of) POP Card Studio and Nexus; this repo imports nothing from those projects.

Public mirror: <https://github.com/btheorystartups/Paper-Workbench>.

Local delegated research: the **Research** project tab supports bounded tasks,
safe document/ZIP intake, independent child-worker handoffs, source provenance,
human-reviewed promotion and downloadable partial/full research packages.
The offline executor is an explicitly labelled fake. An opt-in Codex worker uses
independent model threads with best-effort token stopping; its full live handoff
remains unverified. See [Delegated research](docs/DELEGATED-RESEARCH.md).

For the optional local ChatGPT-account chat provider, see
[Codex local setup and configurable text limits](docs/CODEX-LOCAL.md).

## Status (P1–P6 + expansion + hardening — 2026-09-11)

The protected Vercel Preview is Ready with fake providers and enforced authentication.
Manuscript-aware chat with reviewed edits and server-side logout revocation passed 72
authenticated staging checks; temporary users, workspaces, paper records, and revocations
were removed. Older vulnerable Previews were retired. Real Auth0/PKCE and live writing
quality remain unverified for this slice; real research stays excluded from staging. See
[current verification](docs/audit/2026-09-11-manuscript-chat.md) and
[writing workflow](docs/MANUSCRIPT-CHAT.md).

Implemented and tested (212 offline tests; live providers verified separately with user keys):
- **Research graph** (P1): workspaces, projects, typed research objects, edges, sources
  (access level + license + acquisition mandatory), checksummed excerpts with locators,
  claims with enforced support states and claim→evidence links; audit-in-transaction.
- **Dialogue engine** (P1/P2): persistent threads, pinned context, fenced untrusted
  content, full AI provenance per turn, propose → human-approve → execute pipeline
  (plan-hash bound). Live OpenAI (model from `OPENAI_MODEL`) and Anthropic adapters.
- **Manuscript-aware chat**: section conversations include current prose, linked claims and
  source excerpts, an inspectable context and editable research brief. Proposed section edits
  support before/after review, human revision, rejection, guarded approval, and reviewed undo.
  Evidence states stay unchanged. See [writing workflow and offline demo](docs/MANUSCRIPT-CHAT.md).
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
  workspace-tenant and project roles; typeset PDF + official JATS 1.3 export;
  cross-project memory (unpublished results, usage tracing, saved-search rerun);
  audit eval harness (docs/eval-report.md — precision/recall 1.00 on 7 codes).

- **Auth** (optional, off by default): bcrypt passwords; audience-bound, short-lived JWTs;
  issuer-qualified OIDC identities; explicit IdP-tenant→workspace bindings; workspace and
  project roles; and revocable, scoped API keys stored only as hashes. Enforced mode protects
  all non-public API routes and hides cross-tenant resource identifiers. Endpoints under
  `/auth/*`, `/workspaces/*/members`, `/workspaces/*/oidc-bindings`, and
  `/workspaces/*/api-keys`.
- **Hosted-deployment foundation**: Vercel FastAPI discovery, PostgreSQL/psycopg URLs with
  separate direct migration configuration, startup-migration control, fail-closed serverless
  checks, Secure HttpOnly browser sessions with token-bound CSRF, and backend OIDC
  Authorization Code + PKCE. Content-addressed local/private-Blob artifacts cover ingest,
  figures, exports, publication packages, and project portability; hosted downloads are
  authenticated and browser uploads are bounded.
- **Submission tracking**: audited state machine (drafting → submitted → under review →
  revision requested → resubmitted → accepted/rejected/withdrawn) with response-to-reviewers.
- **Publication packaging**: versioned package plans with controlled cover-letter and
  declaration review states, snapshot-bound human approval, staleness checks, venue findings,
  response-to-reviewers, manuscript outputs, and a checksummed ZIP manifest. Building a
  package never transmits it or marks it submitted.
- **Reproducible compute**: immutable plans bind an ingested Python script, input artifacts,
  arguments, timeout, seed, interpreter, and installed-package fingerprint. Execution needs
  hash-bound approval plus a separate confirmation; captured logs/outputs remain explicitly
  unreviewed until a human verifies and promotes a controlled result. No shell, package
  install, live provider, or automatic claim creation is involved. The optional Docker
  executor additionally requires a locally cached digest-pinned image (`--pull=never`) and
  enforces no network, a read-only root/input mount, non-root execution, dropped capabilities,
  no-new-privileges, and memory/CPU/PID ceilings.
- **Figures & tables**: rendered from content-hashed datasets (matplotlib, colour-blind-safe
  palette); records the source data hash so figures go **stale** if the data changes;
  grounded, review-gated captions; export bundles them into `supplements/` with provenance.
- **Export hardening**: JATS validates offline against the bundled official NISO JATS 1.3
  Archiving DTD (lxml); PDF uses a real WeasyPrint render probe, publication CSS, page numbers,
  references, and visible support/access states. The manifest records renderer mode, version,
  and any deterministic fallback.
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

The unified local launcher enables the guarded manuscript-chat provider and bounded
delegated-research worker in the same application:
`scripts/start_paper_workbench_local.ps1`. See
[`docs/PRODUCTION-WORKFLOW.md`](docs/PRODUCTION-WORKFLOW.md) for the normal production path
and its separation from the fourteen-stage development diagnostic.

Optional container verification (starts one no-network container from an already-cached,
digest-pinned image and uses only temporary synthetic data):
`python scripts/verify_compute_container.py --image repository@sha256:<digest>`.

See `docs/audit/2026-07-20-phase0-decision-record.md` for the go/no-go record, ADRs,
risk register, and the phased roadmap/continuation ledger.

## Run

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,pdf]"
.\.venv\Scripts\python.exe -m pytest              # fully offline
.\.venv\Scripts\uvicorn.exe workbench.main:app --reload   # API on :8000, docs at /docs
```

## Configuration

Copy `.env.example` to `.env`. Everything defaults to offline fake mode. Live providers
require both `WB_PROVIDER_MODE=live` and the relevant key; keys live only in the
environment, never in the database, never in logs.

### Enforced workspace tenancy and OIDC

A workspace is the tenant boundary. Set `WB_AUTH_REQUIRED=true` and a random
`WB_AUTH_SECRET` of at least 32 characters. Self-registration is denied unless
`WB_AUTH_ALLOW_REGISTRATION=true`; legacy plaintext development keys are never accepted in
enforced mode. Creating a workspace makes the acting user its owner, and creating a project
makes that user the project owner. Workspace owners/admins can administer all projects in
their tenant; other users need explicit project membership.

For a fresh password-auth deployment with registration closed, set a separate
`WB_AUTH_BOOTSTRAP_TOKEN` (at least 24 characters) and send it once in the
`X-Workbench-Bootstrap` header to `/auth/register`. The bootstrap path is refused after any
active user exists; remove the token from the environment afterward.

OIDC is configured independently of search/LLM providers. Set `WB_OIDC_MODE=live` plus an
HTTPS issuer, audience, and JWKS URL. Algorithms are restricted to an explicit asymmetric
allowlist. Automatic account linking, user provisioning, and tenant membership are each
separate opt-ins. If an IdP organization claim is used, an owner must first bind each trusted
claim value through `POST /workspaces/{id}/oidc-bindings`; a claim never grants admin/owner.
`POST /auth/oidc/login` accepts a resulting ID token for non-browser clients. For hosted browser
sessions, enable the backend `/auth/oidc/start` → `/auth/oidc/callback` Authorization Code +
PKCE flow. It binds state, nonce, and verifier in a signed short-lived HttpOnly cookie, then
stores the Workbench token in a Secure HttpOnly cookie with token-bound CSRF protection.

Create automation credentials with `POST /workspaces/{id}/api-keys`. The raw `wbk_...` value
is returned once; only its SHA-256 digest, prefix, tenant, scopes, expiration, revocation, and
last-use metadata are stored. Credential creation/revocation, tenant bindings, and membership
grants are audit events. See `.env.example` for every fail-closed switch.
The rollout sequence and remaining deployment-owned controls are in
[`docs/AUTH-DEPLOYMENT.md`](docs/AUTH-DEPLOYMENT.md) and
[`docs/VERCEL-DEPLOYMENT.md`](docs/VERCEL-DEPLOYMENT.md).

## Backup / portability

`POST /projects/{id}/export` writes a checksummed ZIP bundle (every project row + referenced
artifacts) to the configured durable store. `/projects/{id}/export/download` returns it through
the authorization boundary. `POST /projects/import` restores a local bundle path, while
`/projects/import/upload` accepts a bounded browser upload. Both refuse overwrite and verify
every checksum before restoring portable artifact references.

## Known limitations

- WeasyPrint library use on Windows needs Pango. Install MSYS2's
  `mingw-w64-x86_64-pango` package; without a usable runtime, `auto` runs the deterministic
  fallback and records why. `weasyprint` mode fails closed instead.
- JATS uses the official JATS 1.3 Archiving/Interchange DTD because it validates research
  drafts without fabricating absent journal identifiers, ISSNs, abstracts, or references.
  Set `WB_JATS_DTD_PATH` to a stricter venue-specific entry point when those fields exist.
  Validation never downloads schemas at runtime.
- The workspace-tenant authorization, real-ID-token verification, browser Authorization Code
  + PKCE, cookie session, CSRF, and private durable-artifact foundation is built.
  Preview database/Blob provisioning and synthetic resource checks are complete. Operation
  with real data still needs server-side logout revocation, real IdP/PKCE verification,
  authenticated artifact Function smoke tests,
  distributed login throttling, backup/monitoring, and a production-engine review.
  Those operational controls are not simulated as complete.
- Local-Python compute is reproducibility capture, not a security sandbox: network, filesystem,
  and descendant-process isolation are explicitly unenforced. Prefer the optional Docker
  executor for enforceable containment. Docker still trusts the selected image and daemon;
  images must be inspected, already cached, and digest-pinned because runtime pulls are refused.
- Local OCR is optional: install `.[ocr]` plus Tesseract language data. Without it, automatic
  PDF ingestion retains layout text and explicitly labels low-text pages unresolved; forced
  OCR fails closed. OCR output is always `ocr_unreviewed`/`mixed_unreviewed`.
- See `docs/CAPABILITY-MATRIX.md` for the full honest status per capability.
