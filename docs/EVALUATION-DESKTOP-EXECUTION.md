# Desktop execution for the paper pilot

The user selected native desktop agents and their existing ChatGPT usage/credits
for future research. This replaces the proposed direct Responses API production
route. The $75 API estimate is historical preparation, not a desktop budget or an
authorized charge. No API key, credential-store inspection or credit purchase is
needed for native spawning through the current desktop session.

Official documentation says [ChatGPT Work and Codex share usage, credits and limits](https://learn.chatgpt.com/docs/agent-configuration/speed).
[Native subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
perform their own model/tool work and inherit the parent sandbox policy. These
sources establish the product route, not the exact credits charged to a particular
stage. The account-level usage tool is a shared snapshot, not a per-pilot meter.

## What the desktop path establishes

`DesktopDispatch` is a separate, data-only handoff/capture adapter. It makes no
model or network calls. The desktop parent records a spawn attempt first, invokes
the native collaboration tool with the exact returned arguments, attaches the
agent identity from that tool result and captures the returned text. Python does
not pretend to invoke conversation tools. Existing API mock code is unchanged.

The spawn request uses `fork_turns="none"` and explicit requested model/effort.
Prompts, requested configuration, observed agent identity, timestamps, raw results
and accepted report/candidate bytes are preserved under fixed filenames and hashes.
Failed or interrupted work remains partial; there is no automatic retry or resume.
An ambiguous spawn cannot be repeated from the same stage journal. The parent
must use the native interruption tool separately; recording a stop is not proof
of remote cancellation, rollback or settled credit consumption.

The adapter validates basic report/candidate structure. A future desktop role
coordinator must still apply the existing B1 issue-coverage and candidate-handoff
rules before promoting scientific workflow results. The adapter alone does not
implement all twelve workflow roles or either grading pass.

## Guarantees that do not transfer

Fresh conversation context does not remove shared filesystem or tool access.
Instructions to use only a supplied packet are behavioral restrictions. The
available spawn tool provides no per-agent filesystem allowlist, hard token/credit
budget, generation limit or tool-call limit. One spawn request is not one model
generation. Interruption is best effort and cannot undo earlier effects.

The requested model and parent-observed agent identity are recorded, but actual
model use and a complete internal tool transcript are not independently attested
by the exposed tool schema. Missing per-stage credit/token data remains null.
Neither prompt hashes nor account-balance differences establish strict blindness,
exact task charges or independent mathematical correctness.

Consequently, a native run must be labeled a desktop workflow diagnostic. It cannot
inherit the API experiment's enforced 12-generation, 50-tool-call or 25% resource
reserve claims. The stricter API mock controller remains useful qualification
evidence for that different route; it is not silently weakened or relabeled.

## Proposed desktop pilot

The user has approved GPT-6 Astra/high for both arms and adjudication and accepted
the shared-access and credit-cap limitations. Use one fresh native agent for each
of six stages in each arm, then two blinded
presentation/order-swapped grading passes: at most 14 requested agents, serial
within the pilot, no automatic retries or delegated grandchildren. Record that
authorization in the frozen contract before manuscript dispatch; it does not need
to be requested again within this scope. Requested time and output limits are
operational supervision targets, not provider-enforced credit caps.

Use the same two admitted inputs, neutral brief and workflow schedule for both
arms. Preserve initial findings, every candidate and report, issue dispositions,
uncertainty and final limitations. Do not give participant agents this custodian
chat or reference labels. Any observed unintended access invalidates the affected
comparison. General implementation research agents are separate from pilot
participants and must never be recycled as blind reviewers.

Before launch, complete and test desktop role coordination, prepare the exact
participant packets and grading order, and record the applicable account usage snapshot.
No new credit purchases, billing changes, external writes or original-manuscript
edits are implied. Scientific claims remain bounded by actually observed evidence.
