# Unified production workflow

The application at `C:\Users\brian\Documents\Paper-Workbench` is the working project
home. Its manuscript authoring, evidence graph, delegated research, revision review and
publication packaging operate on the same project and manuscript records. Older linked
worktrees and frozen diagnostics under `working/` remain historical evidence; they are
not runtime dependencies.

## Normal production path

The delegated-research task defaults to at most three child researchers under one
coordinating parent. The parent plans bounded assignments, each child returns a structured
report, and the same parent integrates the returned reports. The “three-agent production
default” therefore means `max_children=3`; it may involve four model processes when the
parent and all three children run. A task's explicit child, token and time limits remain
authoritative.

Specialist proof, citation and literature review are supported building blocks,
but the current runner does not automatically require all three for each final
manuscript. A completed research task is not a completed specialist review campaign.
The proposed [manuscript quality integration plan](MANUSCRIPT-QUALITY-INTEGRATION-PLAN.md)
defines the missing assignments, complete-candidate review and publication checks;
that additional orchestration is not yet implemented.

Research output does not enter a manuscript automatically. A human first reviews the
hash-bound task and report for an explicit purpose. Manuscript promotion creates a linked
claim and scoped section. Subsequent objections and repairs use
`services/revision_review.py`: the responding author cannot close their own objection,
and an independent verification binds the comment, response and candidate hashes.
Publication approval and export continue through the existing manuscript evidence basis
and publication-package checks. Do not create a second review ledger or evidence graph.

For one local application with both live manuscript chat and delegated research, prepare
the dedicated Codex profile and database as documented in `CODEX-LOCAL.md` and
`DELEGATED-RESEARCH.md`, set `WB_CODEX_LOCAL_GATE_SECRET` in the current process, then run:

```powershell
.\scripts\start_paper_workbench_local.ps1 -AccountEmail you@example.com
```

The launcher uses the guarded loopback chat server and configures the research worker in
the same process. It does not load `.env`, run migrations, start a research task, or relax
the per-task acknowledgement and budget checks. Search and extraction remain in fake mode
unless separately configured through their existing reviewed path.

## Fourteen-stage diagnostic

`evaluation_desktop_workflow.DesktopWorkflow` is a separate development experiment: two
six-role arms followed by two order-swapped graders. It requests up to fourteen native
desktop agents and produces diagnostic candidate artifacts. It is not the production
orchestrator, does not write a project manuscript, and does not grant publication
eligibility. Its frozen October 3 artifacts remain unchanged under
`working/desktop-pilot-2026-10-03`.

Evidence-intake v2 accepts diagnostic output independently from release eligibility.
Availability statements intended to support release use exact packet and artifact
identities. Ambiguous prose is retained with a review flag. Historical corrections name
the earlier role, packet hash and artifact path. Unresolved bibliography placeholders and
unresolved review flags remain release blockers.
