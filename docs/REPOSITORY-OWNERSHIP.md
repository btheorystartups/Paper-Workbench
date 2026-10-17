# Repository ownership and reconciliation

Reconciled on 2026-10-17, Bangkok time.

## Active project

The working project home is `C:\Users\brian\Documents\Paper-Workbench`.
Its version-control repository is `btheorystartups/Paper-Workbench`; develop and
publish reviewed commits there. This is the standalone application described in
[the October 4 integration record](INTEGRATION-2026-10-04.md) and
[the production workflow](PRODUCTION-WORKFLOW.md).

`C:\Users\brian\Documents\PoP\Tools\Paper-Workbench` is retained as a historical
copy. Its source and Git history remain available, but it is no longer a second
active project or the authority for publishing this repository. The old
`Tools/scripts/publish-paper-workbench.ps1` stops before Git or network operations,
including when invoked with `-Push` or `-WhatIf`.

## Evidence and disposition

The comparison pinned standalone commit `3bb4752792e39d7e921d5396faa5b2586dbea267`
and Tools commit `619351d4dae4de6b43ebbb02214e4685cc832a8e`. The shared historical
reference was standalone commit `38c2599e11d5cffd9f9eb7e796b8e2ab522af9c5`.
Both checkouts were clean before the reconciliation edits.

Among 434 tracked paths compared, excluding environment-file paths:

- 276 paths had identical Git blobs in both current copies.
- 109 paths existed only in the standalone application.
- 49 shared paths differed. Three contained changes only on the standalone side
  relative to the historical reference; the other 46 had changed on both sides.
- 34 of those 46 Tools versions exactly matched older standalone commits.
- The remaining 12 differences were inspected directly: current ownership and
  capability documentation, standalone workspace exclusions, expanded evidence
  availability/release checks and tests, a corrected evaluation fixture, and
  test import/formatting cleanup. No additional Tools-only change required porting.

The standalone implementation therefore remains in place. No application source
was overwritten or merged backwards from the older Tools copy. The Tools copy is
labelled historical and its obsolete publisher is retired. Historical reports
that describe a Tools-owned public mirror remain records of that earlier setup.

## Preservation limits

The comparison above covers the two pinned committed trees. It is not a finding
that every linked worktree, ignored file, research artifact, or local database is
redundant or backed up. In particular, `paper-research-delegation-worktree` has
28 changed or untracked source/documentation/fixture files; all have counterparts
here, but differing versions must be retained until their individual changes are
accounted for. `paper-container-compute-worktree` also has a modified environment
template. A separate comparison found its setting names present in this project's
template, including commented placeholders; operational values were not migrated.

Declaring this checkout the active home does not authorize removing those
worktrees, resetting their files or index, or deleting local research material.
Preserve both staged and unstaged changes before any later merge or cleanup.
The independent October 17 audit retained a checksum-verified local recovery
archive of the 28 delegated-research files. That archive is a limited source
snapshot, not a backup of credentials, databases, ignored data, or all projects.

The saved acceptance clone at
`C:\Users\brian\Documents\Codex\2026-10-06\in-c-users-brian-documents-paper\work\paper-workbench-commit`
is another separate source of historical local changes. Its full reconciliation
is not established by the two-tree comparison above. The standalone October 14
commit `3bb4752792e39d7e921d5396faa5b2586dbea267` already includes retained-author
recovery, continuation and usage reconciliation; preserve that newer architecture
when assessing any older clone changes. Earlier October 11 capability notes do
not, by themselves, describe the October 14 implementation status.

## Selective feature reconciliation

The saved acceptance clone contained 35 uncommitted files. Those exact files and
their tracked patch were preserved in a checksum-verified local archive before
integration. The original clone remains unchanged; the archive does not include
ignored research data or credentials and is not an off-machine backup.

The current working changes selectively restore opt-in editorial closure and
portable manuscript evidence packages on the October 14 architecture. They retain
its author recovery, section recovery, accepted-review replay, usage reconciliation,
and explicit continuation budgets. Editorial review adds preflight and confirmation
checks; it never grants human publication approval. Existing tasks keep their
existing policy and authorization. Enabling editorial review requires the task's
explicit `editorial_closure` option; an old authorization envelope is not expanded
automatically. Local revisions preserve previous closure records as history and
require fresh review without author generation in review-only mode.

This is not a wholesale import of the older clone, nor clearance to remove any
saved checkout. The separate delegated-research worktree differences remain
preserved for individual review. Source/test verification and publication status
are recorded in the October 17 audit workspace outputs; a passing offline suite
does not establish successful live long-paper generation.

This reconciliation does not move environment files, credentials, databases,
research material, virtual environments, or generated output. No service restart,
model run, database migration or deployment is part of it. Repository commit and
push status must be verified separately; this document records source ownership.
