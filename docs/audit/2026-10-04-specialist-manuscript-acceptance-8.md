# Specialist manuscript acceptance: eighth authorized attempt

Date: 2026-10-04. Canonical checkout: `C:\Users\brian\Documents\Paper-Workbench`.

## Authorization and comparison

The user explicitly authorized one further acceptance attempt and described the
supervising models as prior Astra-High and current Sol-Light. These labels are
user-reported, not independently measured model telemetry. Both acceptance
harnesses use `gpt-5.6-sol` / low for the actual manuscript and specialist workers.
The new attempt retained the approved 180,000-token and 900-second limits,
including setup, and used fresh synthetic temporary storage and the existing
authenticated subscription profile. This single-attempt authorization is consumed.

The comparison is observational. Since the prior run, the author/reviewer prompts
changed to separate manuscript content from workflow reports, clarify ordinary
bibliography metadata coverage, and expose the originally reviewed candidate
hash on prior comments. There is no controlled evidence isolating the effect of
the supervising model or showing a billing saving.

| Outcome | Prior attempt 7 | Current attempt 8 |
| --- | ---: | ---: |
| Admitted drafts | 2 | 1 |
| Accepted specialist reports | 6 | 3 |
| Specialist correction calls | 0 | 1 |
| Admitted author revisions | 1 | 0 |
| Observed tokens | 170,863 | 132,013 |
| Complete usage telemetry | Yes | No |
| Seconds including setup | 386.473 | 286.910 |
| Final live handoff verified | No | No |
| Terminal state | limit_reached_partial | limit_reached_partial |

The current draft contained scientific sections and References without a workflow
report section or independent-review status claims. No bibliography-inventory
objection appeared. However, the draft still combined source-specific attribution
in c10, and the proof specialist introduced two search-scope assessment defects.
The run stopped before an author revision could be admitted or re-reviewed.
Lower total usage therefore does not demonstrate better completion efficiency.

## Saved evidence and actual stop

Synthetic run folder:
`C:\Users\brian\AppData\Local\Temp\paper-workbench-advanced-acceptance-afd70be500714fef97733f2c737b9330`.

- Task: `d263f052bbb84ed39a83ef6dce039715`.
- Manuscript: `f465dff0089540e69a62d37a0fe8e37a`.
- Campaign: `188e3f36d86d4f33874ee7289de38159`.
- Admitted candidate SHA-256:
  `71bcfefe4a155529e1a49cafa00a86d8134753400712ed860b66b77c7e9d7b90`.
- Research-package SHA-256:
  `d0d5d25c26c889752be0a3eabdacc57dfd325a5e0ec909ec330c194809004ef8`.
- Evidence saved at 12:19:46.366 UTC / 19:19:46.366 Bangkok.

| Call | UTC start | UTC end | Seconds | Observed tokens |
| --- | --- | --- | ---: | ---: |
| Author draft | 12:15:15.912 | 12:16:20.893 | 64.981 | 13,613 |
| Proof review | 12:16:25.217 | 12:17:21.158 | 55.941 | 18,168 |
| Source review | 12:16:29.323 | 12:17:35.837 | 66.513 | 18,759 |
| Literature review | 12:16:33.413 | 12:17:14.088 | 40.675 | 18,655 |
| Same proof worker correction | 12:17:36.456 | 12:18:23.525 | 47.069 | 32,731 |
| Author revision, stopped | 12:18:24.997 | 12:19:44.338 | 79.340 | 30,087 |

The initial proof report placed search-1 in c11's verification_ids. Structured
intake rejected it with verification_receipt at
`/assessments/10/verification_ids`. The permitted same-worker correction removed
that false receipt reference. It then marked c11, a method/search-scope claim,
not_applicable. The existing deterministic gate retained this as a release
blocker rather than rejecting the entire diagnostic report.

The source and literature reports both found c10's combined attribution invalid:
the supplied 2010 passage supports definitions/refinement but does not support
the overlap/connected-component construction from the 2019 passage. The original
candidate and all reports remain saved with those objections. No saved objection
or candidate was edited to make the run pass.

After the reviews and proof correction, 78,074 tokens remained. The controller
protected 54,000 for the next full specialist wave, granting the author revision
24,074. Its live usage reached 30,087 before the worker could stop, exceeding
that grant by 6,013. The controller ended partial with
`executor exceeded its token allowance; stopped`. The overall observed total
remained below 180,000, but this did not authorize spending the protected review
reservation. The stopped turn has no final usage receipt, so usage_complete is
false; 132,013 is the observed/charged ledger value, not a guarantee of exact
final server usage. In-flight token enforcement remains best effort.

The three specialists overlapped and used distinct model threads, all separate
from the author. The proof correction reused its original worker/thread. The
trace contains 37 controller events with operation spans, stacks and RPC timing
evidence. All eight recorded wrapper/worker PIDs were absent after shutdown.

All seven diagnostic exports succeeded: Markdown, TeX, HTML, DOCX, BibTeX, PDF
and JATS. PDF used WeasyPrint 70.0 with 110 MathJax SVG expressions; JATS passed
the JATS 1.3 archiving DTD check. The export retained 52 audit findings. Successful
export does not clear those findings or establish release eligibility.

## Bounded offline follow-up

Reviewer instructions now explicitly prohibit search receipt IDs in
verification_ids for every specialist role. Search-scope method claims must be
assessed against search_receipts, with evidence described in the rationale and
an empty verification_ids list. The proof role must assess such a method claim
rather than using not_applicable. These are prompt clarifications after the live
attempt; their effect has no new live acceptance evidence.

The source-attribution rule remains enforced, and no model report's reasoning
is promoted to proof that a whole claim follows from its quoted passage. The
author instructions already require splitting source-dependent clauses; the
saved c10 finding still requires author correction followed by independent
review. No deterministic semantic entailment shortcut was added.

After that clarification, all 59 focused worker-boundary and manuscript-quality
tests passed (7 and 52 respectively), including the original/revised candidate
scope regression. Ruff and `git diff --check` passed. The previously passed
desktop, paired-evaluation and publication-package suites were not repeated,
because this follow-up changed reviewer instructions only.

## Remaining boundary

Final live manuscript acceptance remains incomplete. Further live attempts or
budget changes require explicit authorization; this attempt does not authorize
a retry. Continue closely related diagnosis in this thread because it depends
on the current implementation and saved evidence. Keep the manuscript worker
model fixed for comparisons unless the user explicitly requests a worker-model
experiment. A meaningful model comparison would hold implementation, inputs and
budget policy fixed and specify exactly which agent models change.

The dirty checkout was preserved. The protected pilot still has 131 files and
newest write at 2026-10-03 17:40:58 local time. Original manuscripts, PoP checkout,
default database and prior acceptance artifacts were not edited. No commit,
push or deployment occurred.
