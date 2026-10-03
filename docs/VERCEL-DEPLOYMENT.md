# Vercel deployment runbook

## Verified Preview — 2026-09-11

Preview is Ready at
<https://paper-workbench-g957bc3ka-brians-projects-09f2f874.vercel.app>
(`dpl_BoCfTGBdWq1DwxoHu8zBMbLZKGjB`), with migration `a91d4e7b620f` applied. Health/UI
checks and 72 authenticated manuscript/auth checks passed; synthetic data was cleaned up
and cleanup independently verified. The initializer and both superseded vulnerable Previews
were removed. There are no active project aliases or custom domains; Vercel's inactive default
domain configuration remains. Deployment protection requires Vercel access to visit Preview.

See [exact evidence, limitations, and remaining gates](audit/2026-09-11-manuscript-chat.md).
**Do not admit real research data.** Temporary authorized staging identities have now passed
password login/CSRF/workspace-isolation checks and were removed. Copied-token replay after
logout is now denied through shared session revocation. Real Auth0/PKCE, authenticated artifact
workflows, monitoring/backups, and security review remain open. See
[current verification](audit/2026-09-11-manuscript-chat.md).

## Current boundary

The repository now contains a Vercel-discoverable FastAPI entry point, Python 3.13 selection,
PostgreSQL/psycopg support, separate pooled runtime and direct migration URLs, explicit
startup-migration control, production security headers, HttpOnly browser sessions with CSRF,
and a backend Authorization Code + PKCE OIDC flow.

This is a **staging foundation, not yet a production-ready hosted workbench**. Content-addressed
private Blob references now cover ingested originals/extractions, figures, manuscript exports,
publication packages, and project-transfer bundles. Reads are checksum-verified and bounded;
browser ingest/restore uploads and export downloads pass through the application authorization
boundary. Vercel's `/tmp` is used only for scratch assembly. The private store and isolated
database are now provisioned and resource-smoke-tested; full authenticated staging remains gated.

## Fail-closed Vercel environment

Use a pooled PostgreSQL URL for requests and the provider's direct URL only for the separately
run Alembic command. The Vercel Neon integration's `DATABASE_URL` and
`DATABASE_URL_UNPOOLED` names are accepted as fallbacks; explicit `WB_` names win. Never put
either URL in source control or command output.

```text
WB_DEPLOYMENT_MODE=vercel
WB_DATABASE_URL=<pooled PostgreSQL URL>
WB_MIGRATION_DATABASE_URL=<direct PostgreSQL URL>
WB_DB_POOL_MODE=null
WB_DATA_DIR=/tmp/paper-workbench
WB_ARTIFACT_STORAGE_BACKEND=vercel_blob
WB_ARTIFACT_MAX_READ_BYTES=100000000
WB_UPLOAD_MAX_BYTES=4000000
WB_RUN_MIGRATIONS_ON_STARTUP=false
WB_AUTH_REQUIRED=true
WB_AUTH_SECRET=<random value, at least 32 characters>
WB_AUTH_COOKIE_SESSIONS_ENABLED=true
WB_AUTH_COOKIE_SECURE=true
WB_COMPUTE_ENABLED=false
WB_PDF_RENDERER=minimal
WB_PROVIDER_MODE=fake
```

Vercel mode refuses to start if SQLite, local artifact storage, startup migrations,
insecure/no cookie sessions, workstation compute, non-minimal PDF rendering, normal SQLAlchemy
pooling, or a non-`/tmp` scratch directory is selected. Provider mode stays `fake` for initial
staging so deployment validation cannot spend API credits.

Function uploads are capped at 4,000,000 bytes to stay below the platform request-body limit.
Larger direct-to-Blob uploads remain future work and must use short-lived, authorization-bound
upload grants rather than public stores or long-lived browser tokens.

## Auth0-compatible OIDC values

After creating the IdP application, additionally configure:

```text
WB_OIDC_MODE=live
WB_OIDC_ISSUER=https://<tenant>/
WB_OIDC_AUDIENCE=<browser application client id>
WB_OIDC_JWKS_URL=https://<tenant>/.well-known/jwks.json
WB_OIDC_BROWSER_ENABLED=true
WB_OIDC_CLIENT_ID=<browser application client id>
WB_OIDC_CLIENT_SECRET=<server-side client secret, if the client type requires it>
WB_OIDC_AUTHORIZATION_URL=https://<tenant>/authorize
WB_OIDC_TOKEN_URL=https://<tenant>/oauth/token
WB_OIDC_REDIRECT_URI=https://<deployment>/auth/oidc/callback
```

Email linking, JIT user creation, IdP tenant-claim mapping, and JIT workspace membership remain
separate opt-ins. Keep them off until a pre-provisioned staging identity has passed the
cross-tenant denial tests. A claim never grants workspace administration.

## Controlled rollout order

1. Run Ruff, the full offline suite, and `vercel build` from a clean review branch.
2. Create an isolated `paper-workbench` Vercel project with no custom domain and fake providers.
3. Attach a non-production Neon database and a private Blob store. Retain pooled and direct
   database URLs separately; never expose Blob credentials to the browser.
4. Run `alembic upgrade head` once, explicitly, against the direct URL; never at Function startup.
5. Deploy with fake providers and verify health, private Blob round-trips, bounded ingest,
   authorized export/package downloads, and project restore using synthetic data only.
6. Configure the IdP callback for the preview URL and test pre-provisioned login, CSRF denial,
   workspace isolation, logout, and credential revocation.
7. Add monitoring/backups and only then consider a production alias or live AI/search keys.

Creating a deployment is not evidence publication, manuscript submission, or provider-mode
authorization. Those boundaries remain independently controlled.

## Repeat synthetic checks safely

Use an isolated local operator directory containing only a copy of this project's non-secret
`.vercel/project.json`; run `vercel env run` there because it otherwise automatically loads
local dotenv files. Do not run `env pull`, print environment values, or reuse a different
project's linkage. In PowerShell, quote the native argument separator as `'--'`.

Run `scripts/verify_staging_resources.py` by absolute path through `vercel env run -e preview`.
The default preflight reports only the selected endpoint hostname and credential availability.
After verifying the linked staging resource and hostname, add `--execute --confirm-project
prj_a4tgpf6rsmYp7H3JroXUH4x6ERk3 --expected-database-host <verified-hostname>` to authorize
one rolled-back workspace and one uniquely identified, finally-deleted private Blob. The
operator script ignores blank custom-sensitive settings locally; this is not evidence of
Function configuration. Verify the deployed Function using `scripts/verify_staging_http.ps1
-DeploymentId <preview-id>` instead. No diagnostic write route is exposed by the application.
