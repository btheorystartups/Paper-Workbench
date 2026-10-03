# Temporary staging authentication verification — 2026-09-11

> Historical finding: fixed and verified in the subsequent manuscript-chat slice. Both old
> Previews were retired. See [current verification](2026-09-11-manuscript-chat.md).

## Historical outcome: requested checks passed, session revocation finding remained open

Brian explicitly authorized two temporary synthetic users and workspaces in
`paper-workbench-staging-db`, their login/CSRF/logout/cross-tenant tests, and removal afterward.
The tests ran against the existing Preview Function
`dpl_EnHFGu3GHJSfB791FYtQ98wumwQv` at
<https://paper-workbench-9bpamm7mr-brians-projects-09f2f874.vercel.app>.

**All 36 expected HTTP status checks passed.** Two additional copied-token probes exposed
an unresolved security gap: **logout clears the browser cookies but does not revoke the
session token server-side**. Both copied tokens still returned 200 immediately after logout.
Both returned 401 after the synthetic identities were removed. This is not a production
authentication sign-off.

Machine-readable results: [auth report](2026-09-11-staging-auth.json).
Run ID: `a60effb173bc42b5b17aa6ad18ec909e`.
Successful run: `2026-09-11T04:14:22Z` through `2026-09-11T04:18:36Z`.

## Verified behavior

Each identity was pre-provisioned directly into the explicitly approved isolated database
with a generated password, one workspace, and one owner membership. Registration stayed
closed; no bootstrap token or Auth0 configuration was created.

| Check | Both identities |
|---|---|
| Incorrect password | 401 |
| Correct password and identity lookup | 200; correct identity |
| Workspace enumeration | only the identity's own workspace |
| Session cookie | Secure, HttpOnly, SameSite=Lax; no access token in login JSON |
| CSRF cookie | Secure and readable by the browser |
| Missing/wrong CSRF header | 403 |
| Other session's matching CSRF cookie and header | 403; token binding enforced |
| Correct CSRF on own membership write | 200 |
| Own workspace member list | 200 |
| Other workspace member/project lists | 404 |
| Attempted membership grant in other workspace | 404; no extra memberships persisted |
| Login requesting the other workspace | 401 |
| Logout without CSRF | 403; session remains authenticated |
| Logout with CSRF | 200; both app cookies cleared; next protected request 401 |
| Copied session replay after logout | **200 — unresolved server-side revocation gap** |
| Copied session after identity cleanup | 401 |

These are real Function HTTP cookie-session tests using Vercel's existing protection bypass
via its CLI. They do not exercise interactive browser rendering, browser-enforced SameSite
behavior, an Auth0 identity, PKCE against a real IdP, API-key revocation, or authenticated
artifact ingest/export/restore. Those remaining checks are not implied by the result.

## Cleanup and privacy

The harness retained generated passwords and cookies only in process memory and passed
request credentials to curl via stdin. It did not create credential files, print response
bodies, enable debug logs, or read local dotenv files. It ran in the isolated operator directory
using injected Preview environment values. It never changed the schema or provider settings.

Cleanup ran in `finally`, restricted to this run's deterministic synthetic IDs:

| Rows | Deleted | Remaining |
|---|---:|---:|
| Users | 2 | 0 |
| Workspaces | 2 | 0 |
| Workspace memberships | 2 | 0 |
| Synthetic membership-grant audit events | 2 | 0 |

An [independent cleanup rerun](2026-09-11-staging-auth-cleanup.json) at
`2026-09-11T04:25:12Z`–`04:25:37Z` deleted zero rows and confirmed zero remaining again.
It also rechecked fake providers, enforced auth, closed registration, and the unchanged
Alembic revision through the deployed Function and isolated database.

The report retains the synthetic identifiers and outcomes for traceability. The database
revision remained `f3a1c7e9b420`. A deployment-scoped runtime query returned zero HTTP 5xx
records over the preceding hour. Fake providers, enforced authentication, and closed
registration were verified before the run. No research artifacts or real research data were used.

The first attempt stopped at the database preflight before any writes. Removing a PostgreSQL
startup connection option allowed the same run IDs to complete; no application change or
redeployment was needed.

## Local changes and remaining work

Added `scripts/verify_staging_auth.py`, its offline credential-transport/scoped-cleanup/report
classification tests, and these evidence records. Existing deployment changes are preserved;
nothing was staged, committed, pushed, migrated, or redeployed during this verification.

Final verification: **193 offline tests passed**, one existing Starlette/httpx deprecation
warning; Ruff on `src/`, the new harness, and its tests passed; JavaScript syntax and
`git diff --check` passed. The three new offline tests cover credential delivery via stdin,
cleanup that leaves unrelated fixtures untouched, and explicit classification of the
logout replay finding. Git status/diff were reviewed before completion.

Next security priority: persistent server-side session revocation with logout replay-denial
tests. The current `/auth/logout` deletes cookies only; the access-token verifier checks the
user but has no per-session revocation record. Any required staging schema migration remains
subject to Brian's explicit authorization.

Auth0 configuration/real PKCE, authenticated artifact workflows, distributed throttling,
monitoring, backups/restore, and production security review remain open. Real research data
and production aliases remain excluded.
