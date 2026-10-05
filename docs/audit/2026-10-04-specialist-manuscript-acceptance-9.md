# Specialist manuscript acceptance: ninth authorized attempt

Date: 2026-10-04. Canonical checkout: `C:\Users\brian\Documents\Paper-Workbench`.

## Outcome and authorization

The user explicitly authorized one new attempt following the revision-budget
review. It retained the approved 180,000-token / 900-second ceiling, including
setup, the existing subscription authentication, and `gpt-5.6-sol` / low for all
manuscript workers. The supervising-model label remains user-reported Sol-Light.
Fresh synthetic temporary storage was used. No additional live task was started.

The updated policy admitted a complete author revision and a second specialist
wave. The run then stopped **limit_reached_partial** when the literature review
exceeded its individual grant. Two drafts and five accepted specialist reports
are preserved. No report correction was needed. The second proof and source
reports independently resolved all six prior comments from their roles and
raised no new objections. The second literature report did not reach accepted
intake, so literature dispositions and overall acceptance remain incomplete.
No final integration ran; `agent_checks_complete` and `live_handoff_verified`
remain false. Diagnostic output does not establish release eligibility.

Observed/charged usage was **171,575 tokens**, with incomplete final-turn usage
telemetry, and **352.783 seconds including setup**. The revised literature worker
reached 24,506 against its 23,986 grant, an observed excess of 520. The total
task ceiling was not reached, but available task capacity does not silently
change an already assigned worker allowance. Live token enforcement remains
best effort; the stopped turn has no final usage receipt.

## Evidence and dispatch timing

Synthetic run folder:
`C:\Users\brian\AppData\Local\Temp\paper-workbench-advanced-acceptance-79278bb9524340c8a02f5d1e97495d86`.

- Task: `7b0474fd930241c188a16ff10ea02694`.
- Manuscript: `25cb86988d944361a2ec18c8072e8efe`.
- Campaign: `9f6c333f2d024170a42feab40b6612f9`.
- Revised candidate SHA-256:
  `52b1614a15c5686d4e3a8ab1fd840685ff1fbc8fbca91ba00a15907055637179`.
- Research-package SHA-256:
  `78c1b0638daa4072bebca04f7419196cd739148b6d84416d2fa595c8adb8976b`.
- Evidence saved at 12:54:18.094 UTC / 19:54:18.094 Bangkok.

Controller-observed UTC times on October 4:

| Call | Start | End | Seconds | Observed tokens |
| --- | --- | --- | ---: | ---: |
| Author draft | 12:48:43.823 | 12:49:50.109 | 66.286 | 13,676 |
| Proof review 1 | 12:49:54.538 | 12:50:58.498 | 63.960 | 18,442 |
| Source review 1 | 12:49:58.660 | 12:51:08.562 | 69.902 | 18,777 |
| Literature review 1 | 12:50:03.043 | 12:51:14.452 | 71.409 | 18,785 |
| Author revision | 12:51:15.798 | 12:52:46.461 | 90.663 | 31,799 |
| Proof review 2 | 12:52:52.075 | 12:53:40.413 | 48.338 | 22,087 |
| Source review 2 | 12:52:56.638 | 12:54:03.596 | 66.959 | 23,503 |
| Literature review 2, stopped | 12:53:00.797 | 12:54:14.588 | 73.791 | 24,506 |

The campaign records its revision budget decision: 110,320 remaining, per-role
review reserves 23,053 / 23,472 / 23,482, total 70,007, final handoff reserve
7,000, minimum author grant 30,000, assigned author grant 33,313. The actual
revision used 31,799 and passed intake. Remaining capacity was distributed to
second-wave roles, giving 23,557 / 23,976 / 23,986. This confirms the recorded
per-role planning and practical-author admission paths ran live; it does not
validate the margins as sufficient for every worker return or final integration.

The trace contains 52 controller events with operation spans, call stacks and
worker RPC timings. Both specialist waves overlapped. All fourteen recorded
wrapper/worker PIDs were absent after shutdown. All seven diagnostic exports
succeeded, including WeasyPrint 70.0 PDF with 161 MathJax SVG expressions and
JATS passing the JATS 1.3 archiving DTD. The export retained 51 audit findings.
Neither successful export nor completed proof/source reviews clear the missing
literature review, stale earlier review records or unresolved dispositions.

## Scientific and provenance findings

First-round proof review found the intersection theorem missing from the claim
inventory despite a sound proof. Source/literature review found C2's combined
source attribution broader than the supplied 2010 passage supports. They also
questioned the provenance of the note's historical/earlier false assertion.
The revised proof and source reports resolved the inventory/attribution issues
and their historical-provenance comments. No scientific acceptance can be
inferred for the incomplete literature return.

The historical-provenance objection exposed a genuine packet omission: the
author received a task specification explicitly seeding the false statement,
but specialists received candidate/source/receipt evidence without that task
specification. Thus they could not see its declared test-task provenance.
This is distinct from evidence that the claim occurred in a publication or
earlier manuscript. The test deliberately asks for correction of the seeded
claim; it does not provide such publication history.

After the run, the specialist packet now includes the frozen task instruction
text at `/task_specification`, with its own availability-inventory hash and
packet binding. Reviewer instructions distinguish task-supplied seeds from
publication, candidate and independent-review history. A task specification
does not become scientific source evidence, a computational receipt, or proof
of a historical publication. Existing publication and bibliography gates are
unchanged. Saved candidates/reports were not rewritten to clear their findings.
This bounded context repair has no live acceptance evidence yet.

## Offline verification

After the context repair, all **99 focused tests passed**: manuscript quality
(56), desktop evaluation (14), paired evaluation (22), and worker boundary (7).
The new regression confirms the task seed is available with an exact artifact
hash, cannot be falsely declared absent, and is covered by packet-byte integrity.
It also confirms adding task provenance leaves frozen source manifests and
admitted scientific source text unchanged. Existing availability, quoted
correction, historical scope and bibliography-blocker regressions remain passing.
Ruff on the four touched Python files and `git diff --check` passed.

## Comparison and remaining work

Compared with attempt eight, this run admitted a revision and advanced into
fresh re-review without a report-correction call. Compared with attempt seven,
the author/history prompt fixes remained present, but the literature return
stopped on an individual grant before all six reviews could be accepted. These
are different implementation/input-history outcomes, not a controlled model
comparison or evidence of billing savings.

Before another live attempt, review how fixed concurrent grants and accumulated
model context affect completion, including whether the protected final handoff
allowance is sufficient in the persistent author thread. Do not infer that
adding 520 tokens alone guarantees completion or approval. Such review can be
offline in this thread; another live task or increased ceiling needs explicit
authorization. This single-attempt authorization has been consumed.

The dirty checkout, original manuscripts, PoP checkout, default database and
protected pilot remain preserved. No commit, push or deployment occurred.
The pilot still has 131 files and newest write at 2026-10-03 17:40:58 local time.
