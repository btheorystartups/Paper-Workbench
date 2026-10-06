# Astra reviewer routing and bounded literature discovery

## Scope and authorization

The user asked to continue the proposed Astra per-role routing and literature
work. Scoped implementation, offline verification and read-only runtime/catalog
preflight proceeded. No new model turn or acceptance attempt was started. The
previous one-shot live authorization had already been consumed. Commit/push
preparation continues the user's explicit repository request.

## Implemented behavior

| Role | Model | Effort |
| --- | --- | --- |
| Author / ordinary research | GPT-5.5 | low |
| Proof/method | GPT-6 Astra | xhigh |
| Source/citation | GPT-6 Astra | high |
| Literature/contribution | GPT-6 Astra | high |
| Adversarial | GPT-6 Astra | xhigh |
| Literature discovery | GPT-6 Astra | high |

The operator policy is validated before a worker starts. Each process receives a
bound role and selects its model before runtime preflight. Unsupported catalog
entries/efforts, missing roles and incompatible operations fail closed. The
controller rechecks requested model/effort at turn start and terminal return;
manuscript readiness checks retained specialist policy receipts. No model-authored
query or source can change this operator policy. Author/counter compatibility is
preserved rather than implicitly declaring a new model compatible.

Opt-in literature discovery requires a manuscript task and explicit public search
permission. A separately routed planner refines queries using actual previous
receipts. The controller runs Crossref/OpenAlex searches: at most two rounds,
eight additional queries and five results per query. Each planner turn has at
most a 10,000-token allowance inside the original task budget. Manuscript author,
review, repair and handoff reserves are protected. Duplicate/oversized/invalid
plans are rejected before search execution; cancellation and deadline checks apply
between operations. A provider returning excess results is capped by the
controller. Plans, gaps, coverage notes, search receipts, imported metadata and
usage remain inspectable in the research package.

This is bounded discovery, not exhaustive coverage or automatic full-text
acquisition. Metadata cannot establish source entailment or priority. Workers
retain read-only, tool-disabled model contexts; the controller owns search calls.

## Verification

Read-only pinned-runtime account/catalog preflight passed for both Astra High and
Extra High using the existing dedicated sign-in profile. No model thread or turn
was started by those checks; they establish catalog/settings availability, not
scientific review quality or full manuscript acceptance.

The preceding pushed CI run (`37423042957`, commit `109c92f`) had ten failures:
CI lacked the optional tokenizer and used conservative UTF-8 byte estimates,
while synthetic budget tests and telemetry assertions assumed o200k_base.
Synthetic protocol tests now use explicit deterministic fixture counts. Telemetry
assertions accept the actual recorded counting policy. A separate regression
verifies the conservative fallback. Selected originally failing cases passed with
the tokenizer deliberately unavailable. Production counting/admission was not
weakened, and no extra tokenizer/runtime dependency was added to CI.

- Initial affected-file run: 235 tests passed.
- Final role/discovery controls and acceptance argument guards: 37 tests passed.
- Broad local run: 1,011 passed, one skipped, one failed before the new config
  example entry was added; two dependency deprecation warnings.
- The sole broad-run failure was documentation coverage for
  `WB_RESEARCH_CODEX_ROLE_POLICY`. The tracked public template was updated and both
  configuration tests passed on retest.
- Source and acceptance-script Ruff, JavaScript/PowerShell syntax and in-memory
  Python compilation passed. The final fresh checkout is verified by the CI run
  attached to the resulting commit.

## Prepared live acceptance; not executed

`scripts/research_live_acceptance.py` now accepts
`--manuscript-finite-partitions --allow-public-discovery`. It uses a fresh synthetic
store, a self-contained finite-partition specification and the actual allowlisted
finite verification routine. It requests a 900–1,200-word expository manuscript,
four Astra specialists and at most one funded revision/re-review cycle. A known
false inclusion generalization must be explicitly rejected. The specification is
labelled synthetic, not primary literature or established correctness.

Proposed authorization: one attempt, 320,000 tokens and 2,400 seconds including
setup, no automatic second attempt. Run under an outer supervisor; record setup
start before preparation, subtract elapsed setup and a 30-second shutdown margin
from the task ceiling, and never reset the clock. Existing bounded intake
corrections remain within the same task and ceiling. Use normal existing sign-in,
no API key, no default database or original manuscript changes. Token stopping
remains best effort; missing terminal usage retains conservative reservations.

Verify actual role/model/effort and distinct-thread receipts, query/receipt
bindings, counter invocation, scientific objections and resolutions, complete
usage accounting, package checksums and rendered manuscript output. A diagnostic
partial result remains a partial result; human publication approval stays separate.

Fresh user authorization for this new live budget is still required. GPT-5.5
sign-in retirement also makes replacement author/counter compatibility a separate
pending task; a newer model is not automatically compatible with the pinned
restricted transport.
