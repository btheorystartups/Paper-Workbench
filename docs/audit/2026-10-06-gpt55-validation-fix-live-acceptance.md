# Successful live acceptance after child-validation hardening

## Authorization and scope

On 2026-10-06, the user freshly authorized continuation with the previous limits:
**one attempt, 320,000 tokens and 2,400 seconds including setup, no automatic
retry**. The attempt used `gpt-5.5` / low through the existing authenticated,
dedicated Codex profile and exercised the full three-source research pilot with
three child workers. No public literature search or additional model attempt was
started.

A preparation-only Git snapshot operation failed inside the Python supervisor
before any model dispatch. The already successful shell reads were saved through
the shell instead. The setup clock was not reset, and this did not start a second
acceptance task.

The supervisor recorded setup at **01:57:31 on 2026-10-06, Asia/Bangkok** and a hard
deadline of **02:37:31**. It launched at **01:59:40**, giving the task **2,240
seconds** after deducting elapsed setup and a 30-second shutdown margin. An outer
watchdog covered setup, execution and packaging. The launcher exited successfully
at **02:02:22.572**, approximately **291.6 seconds** after recorded setup began;
the watchdog did not fire.

## Result

- Task ID: `bb1333a0b2cd426fbaa1d345250c2305`
- State: **completed**
- Actual reported tokens: **58,761**
- Estimated reservation at completion: **0**
- Usage complete: **true**
- Token stopping: **best_effort**
- Live handoff verified: **true**
- Child handoff received and parent integration received: **true**
- Stop reason: `All bounded assignments returned; human scientific review is still required.`

The parent and all three children completed. Their assignments were:

| Agent | Role / assignment | State |
|---|---|---|
| `14ed9bedeeb3430ba91c1726b043924c` | Parent planning and synthesis | completed |
| `8e592363d4ca412782523eb09a47aefb` | `symmetric_ultrametric_lift` | completed |
| `a847cc6872dd475ea28ed049ec18ac85` | `asymmetric_generalized_lift` | completed |
| `b3019bc694034c45a40265e8787c0a98` | `prior_art_finite_check_status` | completed |

Five successful model returns reconcile to the token total: parent plan **4,214**;
children **11,733**, **11,028**, and **12,759**; parent integration **19,027**.
There were no `worker_failed` trace events and no recorded validation failures.

## Evidence verification

The new synthetic database and original package remain under:

`C:\Users\brian\Documents\Codex\2026-10-06\paper-workbench-diagnosis\work\gpt55-validation-acceptance-49b9a7a8bc724091b961c127224e2df6`

The supervisor record is `work/current-live-attempt.json`; its read-only evidence
copy is `outputs/live-acceptance-evidence.json`. The supervision sibling directory
contains the launcher log and pre-launch checkout snapshots.

The user-facing package is
`outputs/gpt55-live-acceptance-after-validation-fix.zip`.

SHA-256:

`3150ee4e309989078d7e287c51cb9384197835814c89fbb80e0c42b235abf27e`

Offline verification after the run confirmed:

- ZIP integrity and all **40** listed package-manifest hashes.
- Three untruncated frozen source snapshots (`task_contract.md`,
  `research_report.md`, and `search_log.md`) with matching content hashes.
- Every child report passes `AgentReport` validation and references only assigned
  source IDs.
- Parent synthesis passes `Synthesis` validation and includes exactly the three
  returned child IDs, each once.
- Four distinct live Codex thread IDs, all selecting `gpt-5.5` / low. The parent
  planning and synthesis share the same thread, as required.
- Five successful returns, with their reported usage totaling **58,761**.
- PDF packaging succeeded using WeasyPrint 70.0 and MathJax 3.2.2 SVG, rendering
  **320** math spans, with no renderer fallback. A copy of `results.pdf` is saved
  as `outputs/gpt55-live-acceptance-results.pdf`.

The six captured launch/validation/rendering code hashes were unchanged throughout
the attempt. Git status and diff statistics matched the pre-launch snapshots;
`git diff --check` passed. This phase made no application-code changes. The new
audit note is the only repository addition from this phase. The previous offline
phase's **186 passing tests** remain the relevant regression evidence; tests were
not redundantly rerun after this execution-only phase.

The prior failed run's package and synthetic database remained unchanged:

- Package: `59816fa1e8f5fb70d75d12663a55fdd31aede79faa9c826ef4d5f29bdfc1ae4f`
- Database: `e9644b22379fbfbdb4bd6531a44f60d61cb806337a57a6862cc9b2e2a379e541`

## Acceptance conclusion and next step

This closes the **full three-source research delegation, report validation,
parent synthesis, and packaging acceptance case** after the offline fixes. It
does not reconstruct the lost validation detail from the earlier failed child,
establish the scientific claims, or validate the separate manuscript-production
quality workflow.

No further live attempt is needed for this case. Stop paid testing here. Human
scientific review remains necessary before relying on or publishing the research
findings; defer that independent work until the findings are intended for use.
No new chat or model run is required to finish this acceptance task.
