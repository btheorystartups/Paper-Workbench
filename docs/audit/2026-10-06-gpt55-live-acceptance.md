# gpt-5.5 live acceptance attempt

The user authorized one fresh live acceptance attempt at **320,000 tokens /
2,400 seconds including setup**, with no automatic retry. The attempt ran once
from a new temporary output folder:

`C:\Users\brian\AppData\Local\Temp\paper-workbench-gpt55-acceptance-e9e6cee3906345c780c24b7f4a4c18bf`

The launch path selected **gpt-5.5 / low** for research workers. This exercised
the reviewed direct-tool path rather than the previously observed gpt-5.6-sol
Code Mode incompatibility. No second live attempt was started.

## Result

The task reached terminal state **failed_partial**.

- Task ID: `78f9c5e53d4e479ba00bacb5744738cc`
- Actual reported tokens: `50,871`
- Estimated reservation at terminal state: `41,486`
- Token mode: `best_effort`
- Stop reason: `executor or report validation failed`
- Live handoff verified: `false`
- Worker counter failure reason: `null`

The parent and children were dispatched through the live Codex worker using
`gpt-5.5 / low` under the ChatGPT account profile. Four agents were recorded:

- Parent: `cancelled`
- Child `1ca6260d9a6d435986e8943aa431eaaf`: `completed`
- Child `05f3e522862c4752b828eb9b0d894d28`: `completed`
- Child `1fe7163c329d4d98bcbd2c0dc0b44ee3`: `failed`

The failed child was assigned the asymmetric generalized-ultrametric and prior
art/status track. Its provenance records `invalid or failed child response`.
Because one child failed, the parent did not complete a verified synthesis and
the run does not close live acceptance.

## Saved evidence

After the terminal task state, initial packaging failed in the PDF export step
because live model output contained DEL control characters inside explicit TeX
spans such as `\delta` and `\pi`. MathJax returned an error SVG, which the
sanitizer correctly refused. This was an export hardening issue, separate from
the research task failure.

The math renderer now removes non-printing control characters from explicit TeX
spans before calling MathJax. The saved failed-partial task was then packaged
without rerunning any live model work.

Package:

`C:\Users\brian\AppData\Local\Temp\paper-workbench-gpt55-acceptance-e9e6cee3906345c780c24b7f4a4c18bf\lifting-live.zip`

SHA-256:

`59816FA1E8F5FB70D75D12663A55FDD31AEDE79FAA9C826EF4D5F29BDFC1AE4F`

The package includes `call-trace.json`, `call-timing-summary.json`,
`agent_lineage.json`, per-agent reports, `results.pdf`, `results-rendering.json`,
`task_settings.json`, source manifests, synthesis output, and finite-check
artifacts for the completed children.

## Local fixes and verification

Launch defaults were aligned with the reviewed research model:

- `scripts/research_live_acceptance.py`
- `scripts/start_research_codex_local.ps1`
- `scripts/start_paper_workbench_local.ps1`

The math export fix touched:

- `src/workbench/services/math_typesetting.py`
- `tests/test_math_typesetting.py`

Focused verification after the live attempt:

- Counter compatibility, research worker, pinned runtime counter exposure:
  **118 passed** before launch.
- Counter compatibility and research worker after launcher alignment:
  **110 passed**.
- Math renderer, counter compatibility, and research worker after the export
  hardening fix: **119 passed**, with two existing FastAPI/Starlette warnings.
- `git diff --check` passed for the launcher edits before launch.

## Remaining work

This attempt verifies that the gpt-5.5 worker path can dispatch the parent and
children, and it produced packaged evidence from the failed-partial task. It
does not verify successful end-to-end live acceptance. The next offline task is
to diagnose why the asymmetric/prior-art child returned an invalid or failed
response, using the saved package and database. A further live attempt would
need separate authorization with explicit token and setup-inclusive time limits.
