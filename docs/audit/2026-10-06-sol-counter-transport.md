# Sol bounded-author counter transport — 2026-10-06

## Decision

Pin the official `openai-codex` SDK and bundled CLI to 0.160.1. Put the existing
deterministic `check_manuscript_length` callback in the dedicated `paper_counter`
dynamic-tool namespace, and mark only that namespace as directly model-visible.
The research author default returns to `gpt-5.6-sol` / low. The four specialist
reviewer roles retain their separate Astra policy.

The 0.154.0 bundled catalog exposed Sol's counter only inside `functions.exec`,
while the restricted worker disabled the Code Mode host. Merely registering the
callback did not give the model an executable counter. The 0.160.1
[`direct_only_tool_namespaces` configuration](https://github.com/openai/codex/blob/rust-v0.160.1/codex-rs/core/config.schema.json)
and [tool planner](https://github.com/openai/codex/blob/rust-v0.160.1/codex-rs/core/src/tools/spec_plan.rs)
provide a narrow direct-tool exposure path. The [0.160.1 release](https://github.com/openai/codex/releases/tag/rust-v0.160.1)
and [Python SDK distribution](https://pypi.org/project/openai-codex/0.160.1/)
were checked before upgrading. The lockfile records artifact hashes.

## No-inference proof and security boundary

The runtime test uses the actual pinned Windows CLI, a fresh temporary profile,
the production override builder, a synthetic loopback Responses provider and the
production counter callback. No authenticated model request or manuscript inference
is involved. With Sol, the outgoing request advertises exactly one direct
`paper_counter.check_manuscript_length` function. A synthetic namespaced function
call reaches the bounded callback, returns a three-word count and section-text
hash, and the follow-up request retains the final JSON output schema. The same
test covers gpt-5.5; removing the namespace override restores Sol's unusable
Code Mode exposure. Registration, invocation, and final-text receipt matching
remain distinct provenance facts.

The real runtime's effective configuration is checked for disabled Code Mode host,
shell, unified execution, JS REPL, apps, connectors and multi-agent tools, plus
read-only sandbox, `never` approval, disabled web search and no MCP servers. The
direct namespace override is added only to the research worker, not ordinary chat.
The callback requires the exact namespace, tool name, thread ID, turn ID, unique
call ID and active bounded turn. Invalid arguments consume one of four checks;
other requests fail closed. A Code Mode unavailable warning can still appear,
but the counter does not require the disabled executor. No custom model catalog,
general Code Mode host, file access, shell, network access or fallback model is
introduced.

Independent final word counting, inclusive bounds, matching final-text hashes,
the shared token ledger and deadlines, one correction cycle, four Astra reviewer
roles, and scientific release gates remain in place. Authenticated account/model/
effort preflight and real model behavior remain unverified by the loopback test.
The acceptance launcher subtracts setup time from its task deadline and keeps its
outer stop clock anchored to the same attempt start.

## Verification

The full project pytest suite passed (one skip, two existing FastAPI/Starlette
deprecation warnings). A final focused run covering counter exposure, worker,
model policy, research transport and manuscript length also passed after the
last code edit. Ruff's import, fatal and syntax rules passed on touched Python;
the repository has pre-existing long-line findings outside this change. `uv lock
--check --offline` and `git diff --check` passed. The lockfile resolves both SDK
and CLI binary to 0.160.1.

Any live acceptance outcome is recorded separately after this offline phase.

No model inference was started during the compatibility investigation. The
previous gpt-5.5 live acceptance attempt is historical and was not retried here.
