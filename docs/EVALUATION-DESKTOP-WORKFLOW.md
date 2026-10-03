# Native Desktop workflow coordination

`evaluation_desktop_workflow.DesktopWorkflow` is the file-backed counterpart to
the single-stage DesktopDispatch adapter. It makes no provider or native tool
calls. The desktop custodian performs native spawning and passes the observed
agent identity and completion event back to the coordinator.

The sequence is six roles per arm (initial, review, revision, review, revision,
final verification), then two grading passes with reversed anonymous order.
Both arms use the same data-only role builders and validators as the API mock
runner. B1 requires issue identities, evidence hashes, dispositions and final
verification coverage. B0 uses ordinary reports. Neither validator proves the
truth of an assessment.

Call create once, retain its manifest hash externally, and retain the latest
history hash after each acceptance. Reconstruct with both expected hashes.
Prepare records a dispatch before native spawn. Retain the returned dispatch
hash outside participant files. Attach the tool-observed agent identity and
retain its returned identity hash. Accept requires both hashes and that same
identity. It preserves raw submission, completion note, validated result and
candidate source, then writes a chained receipt. Missing or malformed submissions
must end the attempt; pending dispatches cannot be automatically replayed.

Evidence intake contract (v2): each packet inventories supplied text with a JSON
pointer, kind, SHA-256 and byte count. Reviewers receive all preceding author
reports linked to candidate hashes, plus the same original sources, but no other
reviewer's report. Revision and final packets carry bounded manifests of earlier
role packets, including the exact inventory that showed author-history reports in
revision1. The final verifier can distinguish a supplied report from an
authenticated historical execution. The report handoff and inventory apply to
both arms; this mechanism change must be disclosed in any comparison with the
October 3 diagnostic. No grading reference enters a participant packet.

The validator checks that the inventory matches packet bytes. Availability assertions
intended to support release identify an exact artifact path and either the current packet
or a supplied historical packet SHA-256. Their claimed availability and artifact hash are
checked deterministically against that packet alone. A correction to an earlier claim also
identifies the earlier role, packet hash and artifact path. Contradictory structured claims
are rejected. Unstructured or paraphrased absence language is preserved as accepted
diagnostic output with a review flag; it does not establish release eligibility. Quoted
historical wording can be explicitly corrected without preserving the old claim as an
unresolved blocker.

A deterministic scan records unfinished bibliography wording such as "Bibliographic
details to be checked" with source line numbers in author and final results. Diagnostic
acceptance and release eligibility are separate result fields. Unresolved bibliography
markers and unresolved evidence-prose review flags block release eligibility. The scan
does not fill missing citation metadata, authenticate primary sources, or prove a theorem
false.

Frozen inputs, runtime code and previous stage artifacts are rechecked. Receipts
require the complete expected artifact set. Reject duplicate JSON fields and
outputs exceeding declared limits. Two reviews may each have 50 issues, so final
verification permits 100 verdicts. A stale coordinator lock after a crash needs
custodian inspection, not blind deletion or automatic replay.

The approved diagnostic requests GPT-6 Astra/high and fresh context for at most
12 workflow agents plus 2 graders, one agent at a time, without grandchildren or
automatic retries. Eight minutes and 20 tool calls are supervision targets, not
technical credit ceilings. No API calls or credit purchases are part of this
route. Preserve unknown credits/tokens as null.

Native agents share filesystem and tools. Packet-only access is a procedural
instruction; hashes detect changed bytes but cannot attest absent hidden reads.
Actual model identity and full tool transcripts are not attested. Grading labels
hide arm names, but output structure may reveal the mechanism. This is a
development diagnostic, not a technically blinded evaluation or a scientific
readiness certificate. Original manuscripts are read-only; edits stay in local
candidate artifacts. External novelty, bibliography accuracy and PDF layout are
outside the admitted evidence.

Focused synthetic tests cover the complete fourteen-stage sequence, packet
separation, order reversal, no retry, identity/dispatch/history tampering,
malformed output preservation and 100-issue final verification.
