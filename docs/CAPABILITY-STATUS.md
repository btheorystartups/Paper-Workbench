# Capability status — 2026-10-06

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
controlled tests. Historical live manuscript evidence is recorded in the audit
directory; the latest accumulated implementation still needs a complete live
manuscript acceptance run.

## Literature coverage

The application provides Crossref/OpenAlex searches, saved searches, literature
screening and matrices, novelty coverage notes, and bounded citation discovery.
The manuscript acquisition stage executes authorized, task-specified literature
queries and records their results. Novelty claims without completed, nonempty
literature searches are blocking findings.

Specialist workers review the supplied evidence packet. They do not currently
conduct an autonomous, expanding literature search or independently retrieve all
relevant full texts. Search results and metadata alone do not establish source
entailment. A comprehensive prior-art investigation requires deliberate query
coverage, source acquisition, and review; exhaustive coverage is not guaranteed.

## Models and scientific checking

The local launcher currently defaults research workers to GPT-5.5/low. A shared
research model/effort setting applies to author and reviewer workers. The
requested Astra High/Extra High reviewer policy and per-role model routing are
not implemented in this configuration. Having four reviewer roles does not
establish that those requested models were used.

Proof/method and adversarial agents do perform substantive correctness checks.
Their acceptance is an AI review result, not a proof of scientific truth.
Deterministic evidence, receipt, citation, length, and budget gates constrain
what can be accepted, but cannot independently establish every scientific claim.
Formal proofs, reproducible computations, independent experiments, and human
expert review remain necessary where the claim requires them.

The restricted manuscript length counter currently admits only the tested
GPT-5.5/runtime combination. Selecting another model is not sufficient to
establish its counter compatibility. Review replacement compatibility before
another complete live manuscript test. OpenAI documents GPT-5.5 retirement from
ChatGPT, Work, and Codex sign-in on October 14, 2026; API availability is separate.
See [OpenAI model documentation](https://learn.chatgpt.com/docs/models).

## Remaining acceptance work

1. Implement and validate the requested per-role Astra review policy and its
   compatibility with bounded author/counter execution.
2. Run one complete live manuscript production/revision acceptance with a
   separately authorized budget; do not repeat the already passed research run
   merely to change the chat coordinator model.
3. Expand agent-directed literature discovery if comprehensive prior-art search
   is required; keep coverage and source-access limitations explicit.
