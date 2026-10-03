# Manuscript chat and logout revocation

Implemented in the existing deployment worktree; earlier deployment changes preserved.
Brian subsequently authorized continuing routine project operations without repeat approval,
including this staging migration, Preview deployment, and temporary synthetic verification.
No real research, live provider call, commit, or push was involved.

Migration `a91d4e7b620f` was applied to the verified direct endpoint of
`paper-workbench-staging-db`; preflight and after-revision checks passed. The resulting
Preview is `dpl_BoCfTGBdWq1DwxoHu8zBMbLZKGjB`:
[open Preview](https://paper-workbench-g957bc3ka-brians-projects-09f2f874.vercel.app/ui/).
It remains protected, uses fake providers, and has no production promotion.

## Changes

- Manuscript section conversations with current section, claim and linked excerpt context;
  inspector, thread research brief, modes, and branching.
- Server-bound `revise_section` proposals with before/after review, human revision,
  rejection, guarded approval, undo proposals, and retained model/turn provenance.
- Database-backed logout revocation checked by both cookie and bearer authentication.
  Revocation uses a hash of signed issuer/session-id identity, not the JWT's serialized
  spelling, so equivalent base64 signature encodings cannot bypass the denylist. Raw tokens
  are never stored. Expiry includes configured verification leeway.
- Migration `a91d4e7b620f` after `f3a1c7e9b420`; SQLite adds nullable references without
  rebuilding a populated threads table. PostgreSQL uses named foreign keys.

## Verification

- Full offline suite: **212 passed**, with the existing Starlette/httpx deprecation warning.
- New adversarial tests cover foreign tenant/section targets, reviewer write denial,
  malformed model proposals, changed/deleted evidence, concurrent section edits, duplicate
  approval, rejection, revision, undo, source-access limits, context size limits, and branches.
- Password and simulated OIDC logout reject copied tokens; separate sessions survive;
  revocation survives a fresh engine/connection and blocks alternate JWT encodings.
- Migration tests preserve populated conversation/turn data and exercise upgrade/downgrade
  on disposable SQLite databases. No existing local database was read or migrated.
- Browser verification uses only the disposable synthetic demo and fake provider. The
  reviewed edit workflow is exercised through the rendered UI and backed by real local API
  requests; this is not evidence of live-provider drafting quality.
- Browser checks confirmed human revision disables approval until saved, reviewed edits
  apply to the selected section, and reviewed undo restores its original text. The final
  mobile layout measured 375px content width inside a 390px viewport (no horizontal overflow).
  The local browser/server were stopped and the exact synthetic temporary database removed.
- Ruff on the changed Python surfaces, JavaScript syntax, and `git diff --check` passed.
- New Preview health, auth configuration, UI HTML/JS, and anonymous denial checks passed;
  no credential patterns were exposed. See `2026-09-11-staging-chat-http.json`.

## Deployed result

`2026-09-11-staging-chat.json` records **70 expected HTTP checks plus 2 copied-cookie replay
probes, all passed**, from 05:48:53 to 05:59:46 UTC. Manuscript context included the synthetic
source excerpt and saved brief. Proposals did not mutate prose before approval; human
revision, approval, undo, rejected/stale edits, duplicate approval, CSRF, and cross-tenant
denial behaved as expected. Claim support stayed unchanged. Cookie and bearer replay after
logout, including alternate JWT encodings, returned 401 for both users. Findings: none.

The run's finally-cleanup removed both users/workspaces, one project, manuscript/section,
source/excerpt/claim/evidence, thread/turns/proposals, memberships, usage/audit rows, and both
revocation hashes. Remaining test rows: zero. Independent cleanup evidence is in
`2026-09-11-staging-chat-cleanup.json`: the second run at 06:01:39–06:02:17 UTC deleted
zero rows and independently confirmed zero remaining across all fixture tables.

Both superseded Previews were removed after successful replacement checks and verification
that there were no active aliases: `dpl_EnHFGu3GHJSfB791FYtQ98wumwQv` and
`dpl_3BvT2enRc1arEyBuLcy9e1qCve7b`. Final deployment inventory contains only
`dpl_BoCfTGBdWq1DwxoHu8zBMbLZKGjB`, Ready, Preview. This prevents the old shared-database
authentication code from remaining an alternate entry point. A 30-minute log query found
zero 5xx records. No production alias or promotion was created.

Real research and live providers remain excluded from staging. Live IdP/PKCE, real-provider
writing quality, authenticated artifact flows, distributed throttling, monitoring/backups,
and the remaining rollout gates are not established by these results.
