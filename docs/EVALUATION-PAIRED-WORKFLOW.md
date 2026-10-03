# Paired evaluation workflow

`PairedEvaluation` now runs the six E1 workflow stages in each arm using the existing
mock Responses transport. It adds fresh role contexts, shared arm accounting and
immutable candidate handoffs. It does not enable production dispatch, authorize
spending or perform mathematical adjudication. All qualification uses synthetic data.

## Matched stages and budgets

Both arms use the same contract, model, original input bytes, schedule and tools.
The controller selects stages and runs B0 followed by B1; participants cannot choose
another arm or role. Order counterbalancing belongs to a later replication protocol.

| Stage | Generation slots | Broker calls | Accounting phase |
| --- | ---: | ---: | --- |
| Initial author assessment and candidate | 3 | 12 | Work |
| Fresh review 1 | 1 | 6 | Verification |
| Revision 1 | 3 | 12 | Work |
| Fresh review 2 | 1 | 6 | Verification |
| Revision 2 | 2 | 8 | Work |
| Fresh final verification | 2 | 6 | Verification |

Each arm has 12 generation slots and 50 broker calls. Four generation slots and
25% of cost and token ceilings are protected for review/verification. The initial
cost/token baselines allocate 25% to each author stage and divide the remaining
25% across the three verification stages. Rounding goes to the final stage.
Unused, settled cost/tokens can carry forward only after protecting all future
baseline allocations and the work/verification limits. Generation and tool slots
do not transfer. Identical rules apply to both arms; consumed resources may differ.

Before creating a child role, the controller durably reserves and dispatches that
role's full grant in its arm ledger. Child count, generation and auxiliary charges
are reconciled into that grant after capture. Reservations are nested: adding
parent and child costs would double-count the same work. The pair ceiling is the
sum of the two separate arm ceilings, with no transfer between arms. Adjudication
has a separate allocation and is not included in this controller.

A role cannot exceed its grant even if the arm has money reserved for later work.
Exact priced token counts can therefore stop an oversized role before generation.
Count fees already incurred remain charged. Unknown usage or capture failure
retains the full parent reservation and stops the pair. There are no retries or
automatic restarts. Opening a new controller at an existing directory is refused.
Per-arm elapsed limits begin at that arm's first stage and include its handoffs;
the second arm does not lose time while the first arm is running.

## Context and candidate boundaries

Every role gets a new Responses session, conversation and cache namespace.
Workflow reviewers see the current candidate, original admitted evidence and
neutral brief; they do not receive earlier reviewers' verdicts or author private
transcripts. Their single-generation packets include both original texts up front,
so fetching evidence does not consume their only generation slot. Revisions receive
the current candidate, ordinary/structured feedback
and the author's prior reports. The final verifier receives the three frozen
candidates, workflow reports and author responses. No opposite-arm outputs or
benchmark references enter any participant packet.

B0 accepts ordinary report text and complete candidate source. B1 additionally
requires issue records tied to admitted evidence hashes, a disposition for each
supplied objection, before/after locations and a reported regression check. The
custodian attaches exact before/after candidate hashes. Final B1 verdicts must
cover every workflow issue. This validates record coverage and byte identity, not
whether the reported mathematics or checks are correct. All outputs remain
labeled synthetic and scientifically unassessed.

Candidates are returned as data in the final response, then saved under fixed
custodian filenames. Participants never choose filesystem paths or invoke a writer.
Original inputs remain unchanged. Each stage preserves its response capture,
handoff, result and usage. Final export contains each arm's latest accepted source,
the outcome, arm accounting and a hash manifest covering the stage artifacts.
An incomplete export is explicitly marked partial; its candidate may precede the
last scheduled revision. Candidate text is never executed or compiled here.

Source, contract, tariff, handoff and candidate identities are checked before each
step and again after a child returns. Tampered handoffs cannot promote another
candidate. Files use exclusive creation and existing path/junction protections.
Private controller state and ledgers remain custodian material. This data-only
boundary is not a sandbox for arbitrary participant Python or TeX.

## Qualification and remaining launch work

The new tests use the actual pinned SDK with synthetic HTTP responses, including
a complete pair, fresh contexts, cross-arm exclusion, protected future grants,
priced count settlement, uncertainty, cancellation, concurrency, tampering,
malformed records, expiry and capture failure. They use dedicated synthetic ledgers.
The earlier sealed network qualification covers the transport composition; it
does not by itself qualify deployment of this new controller.

Before real execution, qualify the complete controller/production-adapter boundary,
freeze account pricing and auxiliary-operation evidence, resolve the participant
model and accept retention and the actual budget. The previously proposed $75 is
a possible future real-pilot ceiling, not a mock charge or spending approval.
Actual prompt/token fit must be established against the complete role packets.
Python/TeX execution, external literature assessment, blinded adjudicator orchestration
and replication remain separate work. GPT-6 Astra/high is the user-selected
mathematical adjudicator; this phase does not call it or establish human gold labels.
