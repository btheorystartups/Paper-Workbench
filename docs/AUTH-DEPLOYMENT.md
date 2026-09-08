# Authentication and tenant-deployment guide

## Security boundary

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

`POST /auth/oidc/login` accepts an ID token acquired by a deployment-owned Authorization Code
+ PKCE client or authenticating gateway. The backend validates the signature, issuer,
audience, issued-at/expiry claims, and configured algorithm. Paper-Workbench does not yet
initiate the browser redirect or exchange an authorization code.

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
- the IdP client, redirect URIs, Authorization Code + PKCE flow, and logout/session policy;
- distributed login throttling and abuse monitoring;
- secret rotation and short token lifetimes appropriate to the deployment;
- database backup/restore, encryption, monitoring, and a production-engine review; and
- a staging tenant that proves cross-tenant denial before production data is loaded.

These controls are deliberately documented as deployment work, not simulated as complete by
the local FastAPI process.
