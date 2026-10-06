# Sol counter live acceptance — 2026-10-06

The single authorized `gpt-5.6-sol` / low manuscript acceptance attempt ran
from commit `f1b27b3`. It used a fresh synthetic store, a 320,000-token limit,
and a 2,400-second outer deadline. The task ceiling was 2,370 seconds including
setup, reserving 30 seconds for shutdown and packaging. The supervisor elapsed
878.478 seconds. No automatic retry or second model task was started.

## Result

Task `dbd989463fee48298b9cbdb6473c6832` reached `limit_reached_partial`.
The controller reported 179,638 actual tokens and 140,362 remaining, with
best-effort token stopping. The author made **two successful namespaced counter
calls**: 894 words out of bounds, then 934 words inside the 900–1,200-word
range. The 934-word receipt matches the exact final section text. This verifies
live counter exposure, callback dispatch, independent final counting and receipt
binding under the authenticated Sol/low selection.

All four specialist Astra roles completed in distinct threads: proof/method
`xhigh`, source/citation `high`, literature/contribution `high`, and adversarial
`xhigh`. Eight bounded search receipts and one `finite_partitions_v1`
verification receipt were recorded. The specialist campaign status is
`needs_revision`; review comments identified source attribution, execution
scope, reference metadata and claim-inventory defects. Four completed reviews
do not mean the candidate passed them.

The revision admission forecast required 244,856 further tokens including
revision, re-review, repair and handoff, a 104,494-token shortfall. Its timing
forecast also exceeded the remaining research time. The controller stopped
before revision or final handoff. Agent checks and release eligibility are false;
no human publication approval was supplied. This is a partial acceptance
result, not a publication-ready manuscript.

## Package and preservation

The model task was already terminal when the launcher's export failed: the fresh
commit clone lacked the ignored `src/workbench/math_runtime/node_modules` needed
to render the results PDF. Packaging was repeated **without model inference**
against the saved task using the original checkout's installed MathJax runtime
and byte-identical committed source files. The recovered package includes
`results.pdf`. Its ZIP CRC and all 37 manifest entries passed hash and size
checks.

Output folder:
`C:\Users\brian\Documents\Codex\2026-10-06\in-c-users-brian-documents-paper\outputs\sol-acceptance-58dcfea2d064`

`run/manuscript-live.zip` SHA-256:
`f309343d4cdfe523cfef16392f3176c3a5fc45d36cbf9b73e7e1872e8b3f9850`

The output folder also contains the supervisor and recovery receipts. The
acceptance attempt consumed its one-run authorization; further inference would
need a separate decision and budget.
