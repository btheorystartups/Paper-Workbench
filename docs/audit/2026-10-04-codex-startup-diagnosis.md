# Codex startup diagnosis: filesystem sandbox denial

## Confirmed cause

The four-role acceptance attempt failed before its first model turn because the
current Codex desktop filesystem sandbox denied app-server state initialization
in `C:\Users\brian\.paper-workbench-codex`. That configured dedicated runtime
profile is outside this task's writable roots. This was an execution-environment
restriction, not a failed adversarial review or a broken manuscript candidate.

The pinned `codex-cli 0.154.0` binary and launch overrides were held constant:

| Check | Result |
| --- | --- |
| Binary `--version` | Passed |
| Dedicated profile, restricted execution | Exit 1, no RPC response; access denied and failed SQLite state initialization |
| Empty synthetic profile, restricted execution | Exit 0, successful `initialize` response |
| Dedicated profile, approved host execution | Exit 0, successful `initialize`; returned profile matched; no stderr |

The original stderr additionally reported denied stale temporary-directory cleanup
and PATH-alias creation. Diagnostics retained only sanitized messages, classifications
and checksums; no credential files or database contents were inspected.

All diagnostic processes requested only `initialize`, then closed stdin and exited.
They did not request `thread/start`, `turn/start`, account refresh or inference.
This respects the [documented app-server initialization sequence](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server).
No acceptance retry, manuscript agent, or model turn occurred.

## Resolution for a future authorized attempt

Use the explicit tool approval path for host execution so the existing runtime
profile can initialize its own state. Do not alter permissions, copy credentials,
read credential/state databases, or replace the configured profile with an
unauthenticated temporary profile. Preserve the manuscript workers' effective
read-only, approval-never, disabled-tools and other existing restrictions.

Create a new synthetic output folder from the approved host process. The first
host diagnostic's attempt to save into the earlier sandbox-created temporary
folder was denied; a subsequent host diagnostic returned its sanitized receipt
through tool output successfully. Therefore, do not reuse that sandbox-created
folder as the writable destination of a host acceptance run.

The run folder `C:\Users\brian\AppData\Local\Temp\paper-workbench-adversarial-acceptance-agli12ah`
retains `startup-diagnostic.json`, `startup-isolation-diagnostic.json`,
`startup-host-diagnostic.json` and an updated `attempt-finished.json` with the
confirmed cause. Its original failed acceptance and initial plan are preserved.

No runtime-code fix, dependency change, permission-setting change, commit, push
or deployment was needed. Existing dirty code, original manuscripts and frozen
pilot artifacts were preserved. Only the failure receipt and audit documentation
were updated. The earlier 169 focused passing tests remain historical synthetic
verification; today's additional verification is the isolated startup comparison.

## Remaining boundary

The four-role workflow still needs a successful live acceptance. A fresh attempt
requires fresh authorization at the proposed 240,000-token / 900-second ceiling,
with one attempt and no automatic retry. Continue in this thread because the
prepared case, runtime settings and diagnosis are shared active context.
