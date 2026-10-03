# Authentication and tenant-deployment guide

## Security boundary

The manuscript-chat slice adds shared logout revocation in migration `a91d4e7b620f`.
`POST /auth/logout` commits a revocation record before clearing cookies. Both cookie and
bearer authentication consult it on every request. The stored hash identifies the signed
issuer and session id, so equivalent JWT encodings cannot evade revocation. Other sessions
for the same user remain usable. This revokes a Workbench session, not the upstream IdP
session or independent API credentials. API keys retain their explicit revocation endpoint.
Expired revocation rows may be pruned only after `expires_at` (which includes verification
leeway); raw tokens are never stored. See [slice verification](audit/2026-09-11-manuscript-chat.md).

A Paper-Workbench workspace is a tenant. A user must be an active workspace member before
the API exposes that tenant, and must also hold a project role unless they are a workspace
`admin` or `owner`. Direct resource routes resolve their source, claim, thread, manuscript,
artifact, compute run, submission, or package back to its owning project before route code
runs. Missing and cross-tenant IDs both return `404`.

Local mode (`WB_AUTH_REQUIRED=false`) intentionally retains credential-free bootstrap and
legacy development keys. It is not an internet-facing configuration. Enforced mode rejects
those keys and authenticates every route except health, static UI files, and login/bootstrap
entry points.

## First-user bootstrap

For a fresh password-auth database:

1. Set `WB_AUTH_REQUIRED=true`, a random `WB_AUTH_SECRET` of at least 32 characters, and a
   separate `WB_AUTH_BOOTSTRAP_TOKEN` of at least 24 characters.
2. Send the bootstrap value once as `X-Workbench-Bootstrap` on `POST /auth/register`.
3. Sign in, create the first workspace, and add the necessary tenant/project memberships.
4. Remove `WB_AUTH_BOOTSTRAP_TOKEN` from the environment and restart.

The bootstrap header is rejected as soon as any active user exists. Open registration remains
off unless `WB_AUTH_ALLOW_REGISTRATION=true` is an explicit deployment decision. Password
login can be disabled independently after an OIDC path is verified.

## OIDC integration

OIDC configuration is independent of `WB_PROVIDER_MODE`. An enforced deployment must use
`WB_OIDC_MODE=disabled` or `live`; `fake` accepts deterministic JSON claims for local tests
only and is refused at application startup when auth is required.

Live mode requires:

- an exact HTTPS issuer;
- the application/client audience;
- an explicit HTTPS JWKS URL;
- an asymmetric RS/ES algorithm allowlist; and
- the `PyJWT[crypto]` dependency installed by the project package.

`POST /auth/oidc/login` accepts an ID token for non-browser integrations. When
`WB_OIDC_BROWSER_ENABLED=true`, `/auth/oidc/start` and `/auth/oidc/callback` own the browser
Authorization Code + PKCE flow. A short-lived signed HttpOnly flow cookie binds state, nonce,
the PKCE verifier, and a same-origin return path. The backend exchanges the one-time code and
validates the ID-token signature, issuer, audience, nonce, issued-at/expiry claims, and
configured algorithm before issuing a Workbench session.

Browser sessions keep the Workbench access token in a Secure, HttpOnly, SameSite=Lax cookie;
the token is not returned to browser JavaScript. Unsafe requests must present a readable CSRF
cookie whose random value is also bound inside the signed access token. Bearer authentication
remains available for scoped automation credentials and non-browser clients.

Federated identities are keyed by `(issuer, subject)`, because `sub` is not globally unique.
An unverified email never links an account. Verified-email linking, just-in-time user creation,
and just-in-time workspace membership are three separate switches and all default off.

If `WB_OIDC_TENANT_CLAIM` is configured, every accepted claim value must be mapped by a
workspace owner through `POST /workspaces/{workspace_id}/oidc-bindings`. A binding may grant
only `viewer` or `member`; it cannot grant tenant administration or project membership.

## Roles

Workspace roles, from least to most capable, are `viewer`, `member`, `admin`, and `owner`.
Project roles are `reviewer`, `editor`, `coauthor`, and `owner`. Workspace admins/owners can
recover and administer every project in their tenant. Other workspace members require an
explicit project role. New projects give their creator project ownership.

Access-control changes are audit events. Project/workspace roles are controlled values; the
API rejects unknown roles rather than storing prose.

## Automation credentials

Create an automation credential through `POST /workspaces/{workspace_id}/api-keys` with a
controlled subset of `read`, `write`, and `admin`. `write` implies `read`; `admin` implies
both. Only a workspace owner may issue an admin credential, and a non-admin API credential
cannot mint more credentials.

The raw `wbk_...` value is shown once. The database stores only a SHA-256 digest, display
prefix, owner, workspace, scopes, optional expiration, revocation, and last-use timestamp.
Revocation is immediate. Raw values and hashes are excluded from audit detail.

## Internet-facing controls still owned by deployment

Before exposing the service, the operator must additionally provide and verify:

- TLS termination and trusted proxy/host policy;
- the IdP client, exact redirect URI, logout destination, and account-provisioning policy;
- distributed login throttling and abuse monitoring;
- secret rotation and short token lifetimes appropriate to the deployment;
- database backup/restore, encryption, monitoring, and a production-engine review; and
- a staging tenant that proves cross-tenant denial before production data is loaded.

These controls are deliberately documented as deployment work, not simulated as complete by
the local FastAPI process.

Vercel/PostgreSQL-specific setup and the verified synthetic Preview boundary are documented in
[`VERCEL-DEPLOYMENT.md`](VERCEL-DEPLOYMENT.md).
The database and private Blob store are provisioned. Authorized temporary staging identities
passed password login, cookie/CSRF, and workspace-isolation checks and were removed afterward.
**Logout now revokes the signed session identity across workers.** Cookie and bearer replay,
including alternate JWT encodings, were denied for both synthetic staging users. Real
Auth0/PKCE and authenticated artifact workflows remain open. See
[current verification](audit/2026-09-11-manuscript-chat.md).
