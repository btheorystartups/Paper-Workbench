# Preview deployment verification — 2026-09-11 (Asia/Bangkok)

> Historical Preview, now retired. The manuscript-chat slice deployed a replacement and
> verified server-side logout revocation. See [current verification](2026-09-11-manuscript-chat.md).

Follow-up: Brian subsequently authorized two temporary staging identities and workspaces.
Their password login/CSRF/workspace-isolation checks passed and all fixtures were removed.
Copied session tokens remained usable after logout at that time; the later slice fixes this.
See the [later authentication report](2026-09-11-staging-auth.md). The sections below preserve
the state at the end of the initial Preview verification.

## Verified staging deployment

- Project: `paper-workbench`, `prj_a4tgpf6rsmYp7H3JroXUH4x6ERk3`.
- Scope/account: `brians-projects-09f2f874` / `btheorystartups-8345`.
- Branch: `codex/paper-vercel-deployment`; base HEAD `f41569d47cbd9d80fc8f1d841871f242d61dcc21`.
- Source: intentional dirty deployment worktree, not a committed release.
- Deployment: `dpl_EnHFGu3GHJSfB791FYtQ98wumwQv`.
- URL: <https://paper-workbench-9bpamm7mr-brians-projects-09f2f874.vercel.app>.
- `vercel inspect`: **target preview, Ready**, FastAPI Function in `iad1`, 43.15 MB.
- Vercel build: Python 3.13, dependencies installed from `uv.lock`, build succeeded.
- The deployment-list API represents this Preview target as JSON `null`; CLI inspection
  explicitly reports `preview`. It is not production-classified.
- Active project aliases: **zero**. No custom domain is attached. Vercel retains its
  default `paper-workbench.vercel.app` domain configuration without an active alias.
- Inert initializer `dpl_HauzT9iX4xSvPCong76sCsoj872Y` was removed only after the checks
  below passed. The corrected Preview remained Ready afterward.

Vercel deployment protection is enabled: a direct anonymous health request redirects (302)
at the platform boundary. Application checks used `vercel curl`; the CLI generated a project
protection-bypass credential automatically on first use. Its value was never printed or
copied into source. No application user was provisioned and application auth remained enforced.

## Application HTTP checks

`scripts/verify_staging_http.ps1` passed against the corrected deployment:

| Path | HTTP status | Verified behavior |
|---|---:|---|
| `/health` | 200 | ok; fake providers; auth required; OIDC disabled; Vercel mode |
| `/auth/config` | 200 | registration closed; cookie sessions on; browser OIDC off; upload limit 4,000,000 |
| `/ui/` | 200 | expected Paper-Workbench HTML |
| `/ui/app.js` | 200 | expected hosted browser authentication code |
| `/workspaces` | 401 | application credentials required |
| `/auth/me` | 401 | application credentials required |

No Blob credential, credential-bearing PostgreSQL URL, or private-key patterns appeared in
these response bodies. This is a bounded output check, not a comprehensive secret-leak audit.
Runtime queries scoped to this deployment returned **zero error records** and **zero HTTP
5xx records** in the preceding hour. Message bodies were suppressed. These point-in-time
checks are not continuous monitoring.

## Synthetic resource checks

Resources were confirmed before testing:

- Neon: `paper-workbench-staging-db`, resource `store_BICQJ5NOXGtC2qkz`, project
  `steep-darkness-52862251`; the Vercel integration lists it on `paper-workbench`.
- Runtime endpoint (hostname only):
  `ep-fragrant-violet-avjxe9qt-pooler.c-11.us-east-1.aws.neon.tech`.
- Blob: `paper-workbench-staging-artifacts`, `store_hxwgjlFglmOVclXl`, **Private**, `iad1`.

`scripts/verify_staging_resources.py` imports this worktree's source, consumes injected
Preview environment values, and requires exact project/endpoint confirmations before writes.
It never runs migrations or provisions users. The successful run reported:

- Alembic revision: **`f3a1c7e9b420`**, unchanged.
- Synthetic workspace ID: `807fb08c8bac4d72b22f924baf060128`.
- Workspace insert/read passed inside a transaction; explicit rollback completed; a subsequent
  query confirmed the synthetic row was absent.
- Synthetic Blob bytes: SHA-256
  `a4da2a1197bafe12caab9cc281353fa5e9a959c51fc5cfa076c70aa7e191d930`.
- Blob namespace: `artifacts/staging-smoke/807fb08c8bac4d72b22f924baf060128/`.
- Private write/read/checksum and repeated-write verification passed. Anonymous read: **403**.
- Exact synthetic object deleted in `finally`; exact-key listing was empty. A fresh store
  inspection subsequently showed **0 blobs, 0 bytes**.

These resource round trips ran from the operator process using Preview resource credentials
and the same application adapter source subsequently deployed. They were **not authenticated
end-to-end Function upload/download tests**; those still require an approved staging identity.

## Fixes and verification

Existing intentional work was preserved. This continuation changed only:

1. `uv.lock`: restored missing multipart and Vercel SDK dependencies; retained existing pins.
2. `.vercelignore`: explicitly excluded pytest/Ruff/Python caches after an inaccessible local
   pytest cache prevented the first upload attempt.
3. `storage.py`: handle current Python SDK buffered `content` results as well as older `stream`
   results. Check Blob metadata before downloading and actual byte length afterward; check local
   file size before reading. The SDK still buffers downloads, so the post-read check is not a
   strict transport-level memory ceiling if remote metadata changes during a read.
4. Storage regression tests, two explicit operator smoke scripts, and deployment documentation.

The first real Blob smoke exposed the SDK response mismatch; its synthetic row was rolled
back and Blob deleted. The corrected adapter then passed the complete resource check. The
earlier Preview `dpl_3BvT2enRc1arEyBuLcy9e1qCve7b` is superseded and should not be used for
artifact operations; it was not removed because only initializer deletion was authorized.

The first CLI environment preflight reported automatically loading `.env.local` (no values
were printed). Subsequent environment runs used an isolated operator directory containing
only the non-secret `.vercel/project.json` linkage; no dotenv file was loaded there. The
resource script and all pytest runs disabled the application's dotenv loader.

- Full offline suite: **190 passed**, one existing Starlette/httpx deprecation warning.
- Focused storage suite: **12 passed**.
- Ruff (`src/` and the new Python operator script): passed.
- JavaScript syntax: passed.
- `uv lock --check --offline`: passed (77 resolved packages).
- `git diff --check`: passed. Git status/diff reviewed; nothing staged, committed, or pushed.

## Remaining gates and roadmap

**No real research data is admitted to staging.** Provider mode remains fake. No new paid
resource, production deployment, production alias, custom domain, IdP, or identity was created.

1. Obtain authorization for a pre-provisioned staging identity (Auth0 configuration and/or
   bootstrap user). Then test login, PKCE with the real IdP, CSRF, logout, revocation,
   cross-tenant denial, and Function-backed ingest/export/restore using synthetic fixtures.
2. Distributed throttling, monitoring, Neon backup/restore drill, and production security review.
   Session-token replay/revocation, hostile artifact descriptors/imports, archive expansion
   limits, and server-side path routes require explicit review before real data.
3. Authorization-bound direct private-Blob uploads above the Function upload limit.
4. Advisory semantic contradiction/weak-support detection with attributable, reviewed output.
5. Bulk tagging and side-by-side object/version comparison UI.
6. Better manuscript figure/table cross-reference detection.
7. Optional local OCR runtime installation and language data, preserving fail-closed forced OCR.
8. Propose a production alias only after staging/auth/backup/monitoring/security gates pass.

Commits, pushes, identity provisioning, live research-provider calls, and production exposure
remain separately approval-gated. Systematic-review protocols and mid-call cancellation remain
out of scope.
