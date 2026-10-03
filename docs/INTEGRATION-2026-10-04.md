# Paper-Workbench integration record — 2026-10-04

## Destination and preserved material

The application working tree was copied from
`C:\Users\brian\Documents\PoP\Tools\Paper-Workbench` into the requested project home,
`C:\Users\brian\Documents\Paper-Workbench`. The copy included the current manuscript,
research, review, publication, UI, migration, documentation and test sources, including
uncommitted application work. It excluded virtual environments, application databases,
generated output, caches and every `.env*` file.

Existing root material was retained. The `working/desktop-pilot-2026-10-03` directory
contains 131 files; after integration its sorted path-and-file-hash aggregate is
`b56b99f52d827afdd6b12002b128f9c78fefb3f622fa40bd84561d3cb8f222ca`.
The historical workspace directories are ignored by the application `.gitignore` so a
future source review cannot accidentally include them.

## Repository review state

The destination now has local Git metadata anchored to the public repository's `main`
commit, `38c2599e11d5cffd9f9eb7e796b8e2ab522af9c5`. The unified application is therefore a
reviewable, uncommitted working-tree change against the published history. No files were
staged, committed or pushed.

After explicit authorization, the tracked `.env.example` was restored and reconciled
with the integrated settings model. It contains placeholders only, keeps live providers
and delegated execution disabled, and documents the guarded local-chat, research,
deployment, storage, authentication and OIDC controls without copying local secrets.

## Bounded implementation

Evidence-intake v2 now supports exact availability assertions with:

- `packet_scope`: `current` or an admitted historical packet SHA-256;
- `artifact_path`: an allowlisted evidence JSON pointer;
- `availability`: `available` or `unavailable`;
- `artifact_sha256`: the exact supplied hash when available, otherwise `null`.

Contradictory structured assertions are rejected. Unstructured availability language is
accepted as diagnostic output and recorded as a review flag. A historical correction
must name its source role, packet SHA-256, artifact path, corrected availability and
reason. This allows a final verifier to quote and correct an earlier false claim without
silently rewriting the frozen history.

Every role result now distinguishes `diagnostic_status` from `release_eligibility`.
Unresolved bibliography placeholders, unresolved availability-prose flags, and unresolved
structured final verdicts are explicit release blockers. The existing revision-review,
manuscript evidence basis and publication-package services remain the production review
and release authorities.

The unified PowerShell launcher configures guarded local manuscript chat and the bounded
delegated-research worker in one application. It uses the existing loopback launcher,
dedicated Codex profile, explicit account binding, per-task research limits and human
promotion gate. It does not load environment files, migrate a database, or start work.

## Verification

- 59 focused evaluation, paired-workflow and evidence-binding tests passed.
- 8 publication-package tests passed.
- 64 manuscript-chat, delegated-research, research API and manuscript-path tests passed.
- 22 local-chat configuration and research-worker tests passed.
- 1 unified production-path test passed, carrying a synthetic result through delegated
  research, hash-bound human promotion, manuscript chat approval, independent revision
  verification, authorship finalization and evidence-bound publication approval. It also
  confirms that an authorship change reopens the prior verification until it is repeated
  against the new candidate hash.
- The combined evidence-intake, paired-workflow, publication-package and unified-path
  regression run passed all 68 tests.
- The complete offline suite was then run with imports explicitly pinned to this
  destination's `src` directory: 640 tests passed and 1 optional-capability test was
  skipped. The run also exposed and repaired two stale evaluation scenarios so their
  verification-debt claim and unresolved source are actually bound to the manuscript
  evidence basis being audited.
- Ruff passed across the complete `src` and `tests` trees.
- The unified launcher passed PowerShell parser validation.
- All tests used fake providers and disposable pytest storage. No manuscript agent,
  live provider, default database, migration, deployment, commit or push was used.

The public GitHub mirror and the earlier PoP copy were not modified. Publishing or
retiring old working copies requires a separate reviewed source-control phase.
