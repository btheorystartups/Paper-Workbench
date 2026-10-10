# Capability status — 2026-10-11

Paper-Workbench runs as a local web application on Windows. The local Codex
provider communicates with Codex app-server using ChatGPT account sign-in.
Codex desktop is the development and testing interface; the workbench itself
is a separate application. Hosted production deployment is a separate workflow.

## Research and manuscript production

Delegated research supports independent child threads, bounded token/time
budgets, frozen source packets, validated evidence references, recorded usage,
provenance traces, and checksummed result packages. The latest GPT-5.5/low live
acceptance completed a parent and three children with 58,761 reported tokens,
complete usage accounting, verified handoffs, and a rendered PDF. See the
[acceptance audit](audit/2026-10-06-gpt55-validation-fix-live-acceptance.md).
That run exercised delegated research, not the complete manuscript production
and revision workflow.

Manuscript production requires four specialist roles: proof/method,
source/citation, literature/contribution, and adversarial review. Review receipts
bind the candidate hash and distinct reviewer threads. The adversarial reviewer
must formulate challenges with acceptance criteria; unresolved blocking
objections prevent acceptance. These checks are implemented and covered by
controlled tests. The October 6 Sol acceptance exercised the author counter,
four distinct Astra reviewers, bounded discovery and finite verification. Review
objections and insufficient revision capacity stopped it before revision and
handoff; it did not establish release eligibility. See the
[live acceptance audit](audit/2026-10-06-sol-live-acceptance.md).

## Literature coverage

The application provides Crossref/OpenAlex searches, saved searches, literature
screening and matrices, novelty coverage notes, and bounded citation discovery.
The manuscript acquisition stage executes authorized, task-specified literature
queries and records their results. Opt-in agent literature discovery adds a
separately routed Astra High planner that selects and refines queries using the
actual previous search receipts. The controller executes them through
Crossref/OpenAlex: at most two rounds, eight additional queries, five results per
query, and 10,000 reserved model tokens per planning round. Discovery draws from
the existing task budget and protects manuscript author/review/repair/handoff
reserves. Duplicate, unsupported, oversized and unauthorized plans are rejected.
Novelty claims without completed, nonempty searches remain blocking findings.

Search plans, coverage notes, remaining gaps, usage and search receipts are
preserved. Public discovery requires both `allow_public_search` and
`agent_literature_discovery`; neither grants web browsing or external write tools
to a worker. Full texts are not automatically acquired by this workflow. Metadata
is a discovery lead, not a source-entailment receipt or proof of novelty.
Comprehensive prior-art investigation still requires deliberate coverage and
full-text acquisition/review; exhaustive coverage is not guaranteed.

## Models and scientific checking

Author and ordinary research workers default to GPT-5.6-Sol/low. Manuscript specialists
now have an operator-owned policy: Astra Extra High (`xhigh`) for proof/method and
adversarial review; Astra High for source/citation and literature/contribution.
The discovery planner also uses Astra High. Each process selects its role before
runtime preflight. The model catalog and effective thread settings are verified;
model/effort fallback is rejected at turn start, return and manuscript readiness.

`WB_RESEARCH_CODEX_ROLE_POLICY` is a JSON object keyed by `proof_method`,
`source_citation`, `literature_contribution`, `adversarial`, and
`literature_discovery`, each with `model` and `reasoning_effort`. Missing required
roles fail closed. Author settings remain separate. The saved live acceptance
records the authenticated Sol/low author and all four Astra role/effort selections;
the complete production/revision cycle still needs acceptance.

Proof/method and adversarial agents do perform substantive correctness checks.
Their acceptance is an AI review result, not a proof of scientific truth.
Deterministic evidence, receipt, citation, length, and budget gates constrain
what can be accepted, but cannot independently establish every scientific claim.
Formal proofs, reproducible computations, independent experiments, and human
expert review remain necessary where the claim requires them.

The restricted manuscript length counter uses the pinned 0.160.1 runtime's
direct `paper_counter` namespace. Offline tests cover Sol and GPT-5.5 without
enabling the Code Mode host, shell, browsing or other worker tools. The saved
Sol acceptance includes two successful counter calls and an exact final-text
receipt match. A compatibility record alone does not establish live compliance
or scientific clearance. See the
[counter transport audit](audit/2026-10-06-sol-counter-transport.md).

## Remaining acceptance work

1. Continue reconciling the remaining continuation, evidence-package and
   editorial-closure controller work in the saved acceptance clone before
   selecting a new live acceptance target. The canonical checkout now has the
   integrity/literature guards and a bounded controller-side checkpoint/terminal
   receipt preservation group, but it does not yet claim the clone's full
   recovery or closure workflow. Preserve both dirty checkouts and historical
   artifacts.
2. Complete manuscript production/revision acceptance with a separately
   authorized budget. The October 6 attempt consumed its one-run allowance;
   its counter and specialist calls passed, but scientific review did not.
3. Acquire and review relevant full texts for comprehensive prior-art claims;
   bounded query refinement alone does not establish exhaustive coverage.
