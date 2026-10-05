# Length-tool live verification: 320,000 tokens / 2,400 seconds

## Authorization and result

The user explicitly approved one attempt at **320,000 tokens / 2,400 seconds including
setup**, with no automatic retry. The run retained **gpt-5.6-sol / low**, one scientific
revision cycle, four mandatory specialist roles and three concurrent review slots.
The approved host launch succeeded. This attempt consumed that authorization; no retry ran.

Outcome: **`failed_partial`**, with controller reason `executor or report validation
failed`. The initial author returned an admitted **960-word** manuscript with empty
responses, in the required inclusive 900–1,200-word range, without intake correction.
Its counter provenance records **zero tool requests and no matching check**. This
demonstrates an in-range final return; it does not validate live counter invocation
or prove the counter caused the improvement.

The proof/method, source/citation and literature/contribution reviewers started in
three distinct model contexts. None returned text or a complete specialist report.
The proof worker emitted a sanitized **`runtime_error`** during `turn_stream` after
approximately 900 seconds. The controller stopped the campaign and cancelled the
other two reviews. The adversarial reviewer was still deferred behind the occupied
slots. No scientific revision, independent re-review or final model integration ran.
Accepted reports: **0**. Agent checks, human publication approval, release eligibility
and live diagnostic handoff verification are all **false**.

## Time and usage

Setup began at `2026-10-05T14:17:46Z`; the outer deadline was `14:57:46Z`.
Task creation/start was recorded at `14:19:01.579300Z`, approximately 75.58 seconds
after setup began. The task stopped at `14:39:22.555298Z`, and saved artifacts/package
finished after **1,299.748935 seconds including setup**, within the 2,400-second ceiling.
The run failed before the authorized time ceiling. Time admission for scientific
revision was never reached.

| Operation | Controller seconds | Reported actual tokens | Outcome |
| --- | ---: | ---: | --- |
| Author draft | 303.264 | 46,620 | 960 words; admitted; counter unused |
| Proof/method audit | 902.399 | unavailable | Runtime error; no streamed text |
| Source/citation audit | 897.522 | unavailable | Cancelled; no streamed text |
| Literature/contribution audit | 892.721 | unavailable | Cancelled; no streamed text |

Reviewer streaming spans were 899.605, 895.110 and 890.383 seconds respectively;
controller spans also include RPC preparation. **Reported actual usage: 46,620**.
**Charged usage: 229,155**, comprising the author usage plus all three **60,845-token**
review grants. None of those reviews has terminal actual usage, so the grants remain
fully charged. The actual total for interrupted reviews is unknown; do not treat
the charged figure as measured consumption or infer unused computation from it.
No confirmed controller charge exceeded the approved ceiling.

## Diagnosis and limitations

All eight recorded RPCs in the failing proof worker returned successfully, including
account/model/config preflight, ephemeral thread creation and `turn/start`. Its failure
was a later runtime error notification during streaming. The trace distinguishes
this from an intake length rejection or an `unsupported_item` counter/tool failure.
The source and literature workers have cancellation receipts and no recorded runtime
error of their own.

The current boundary deliberately discards raw runtime error messages. It retains a
fixed error class/code, progress, timings and stacks, but not enough structured error
detail to determine whether the underlying cause was service/transport interruption,
queueing, a rate limit or a different runtime problem. The near-900-second no-text
span is an observation, not proof of a particular timeout. Raising token/time limits
again or changing manuscript models is not justified by this evidence alone.

The native draft schema returned successfully with the registered counter descriptor;
no live callback invocation occurred. Therefore the counter's actual invocation and
its usefulness on a correction remain unverified. The new time-admission guard was
not exercised live in this attempt. The prior offline tests and replay remain its
verification evidence. The prior attempt's source/scope objections are not resolved
by this new, scientifically unreviewed draft.

## Preservation and cleanup

Fresh synthetic output only:

`C:\Users\brian\AppData\Local\Temp\paper-workbench-length-tool-acceptance-433bd962c4d747e5b92548f818babd7c`

Saved evidence includes approved/host launch, input and implementation manifests,
snapshot, assessment, readiness, call trace/timing, per-attempt counter receipts,
stream measurements, partial manuscript/reports and a research package. Scoped
post-run reads used this synthetic database/artifacts; no default database or secret
file was inspected. Existing authenticated worker access used the approved launcher.

Verification confirms:

- Implementation hashes unchanged during the run.
- Both frozen primary PDFs unchanged.
- All **131** frozen pilot files unchanged against the saved baseline.
- All **eight** recorded worker/runtime PIDs and launcher PID **5468** absent.
- Package SHA-256: `ee8c2391986d5b24f41b89e1775e04e87ad6465409477ef48c1d3be6ea825275`.
- Task: `8ce0dd24a1954fa7b406027ab4e7d626`.
- Manuscript: `ae2adff6a1564b8d816c03f53be47d9a`.
- Raw admitted draft SHA-256: `21500d5e3df4d450eac92f7a708cbd759a7e02ebb3dd3aa2667a6872c25370fd`.

The prior 349-test offline suite remains the implementation verification baseline.
No application code changed during this live phase, so tests were not rerun merely
to repeat that baseline. Status/stat/diff checks reviewed the existing dirty checkout;
those older changes are not attributed to this run. No manuscript originals, pilot
artifacts or prior acceptance outputs were edited. No commit, push or deployment occurred.

## Next phase

Prioritize a bounded offline diagnostic improvement: retain allowlisted structured
runtime error categories and retryability/status metadata without raw messages,
prompts or credentials; record notification/first-text inactivity and distinguish
reasoning from unavailable progress where the protocol supports it. Test known
errors, malformed/private diagnostics, cancellation, ledger charging and final cleanup
with controlled processes. Investigate why the registered counter was unused without
making valid in-range drafts fail solely for missing a call. Preserve the no-retry
policy and scientific gates.

Continue in this chat because the active patch, bound run evidence and preservation
decisions are needed. **gpt-6.1-sol / medium** is sufficient for that offline work.
Another live verification requires new explicit authorization. No further live run,
larger budget or manuscript model upgrade is initiated or recommended now.
