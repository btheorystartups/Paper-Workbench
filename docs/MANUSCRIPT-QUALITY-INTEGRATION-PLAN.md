# Plan: agent responsibility for manuscript quality

Status: proposed implementation, requested on 2026-10-04. The existing smoke-test
repairs are implemented and tested; the additional workflow below is not yet implemented.

## Answer: what is already integrated?

Agents already contribute to these checks, but coverage is not automatically
required for every manuscript. A completed research task currently means that
bounded assignments and synthesis completed. It does not mean that the final
manuscript passed three separate specialist reviews.

| Area | Existing code and behavior | Gap to close |
| --- | --- | --- |
| Proofs and counterexamples | `research_contract.py` supports `proof_audit`, proof attempts, located citations and verification artifacts. `research_runner.py` validates structured reports and preserves original returns. | Assignments are free-form; no required proof reviewer or coverage of every final theorem. A model can describe a passed check without an independently executed computation. |
| Source support | `research_tasks.py` freezes sources; report citations carry source IDs and locators. `audits.py` checks claim/evidence links and source-access states. | No mandatory reviewer checks every substantive final claim against the actual cited passage and document version. A valid citation ID alone does not prove entailment. |
| Literature and novelty | `literature.py` saves searches, imports source metadata, records screening and provisional contribution maps with coverage notes. The manuscript path exposes missing novelty review. | The current live research worker reads only supplied frozen text. It does not autonomously run broad external searches; no required novelty reviewer or final claim-to-prior-work comparison. |
| Skeptical review | `audits.skeptical_review` creates objections. `revision_review.py` binds objections, responses and independent dispositions to a candidate version. | The optional skeptical pass supplies only the first 800 characters of each section and produces loosely parsed prose notes. It is not a complete final-manuscript audit. Its legacy response/resolution notes are not automatically the structured revision-review workflow. |
| Publication | `evidence_basis.py`, `audits.py` and `publication_packages.py` bind approval to manuscript evidence and reject recorded blockers. | Missing specialist reviews are not universally materialized as required checks. The project progress view and package readiness must agree on the same manuscript-specific coverage. |

The previous live demonstration explicitly requested proof, finite enumeration and
skeptical scope checking. Its successful agents establish capability on that task,
not automatic coverage for a subsequent manuscript.

## Intended user experience

The normal manuscript-production workflow should automatically prepare the draft,
assign the required specialist reviews, revise supported objections within the
approved limits, and present a final evidence package with unresolved issues.
The user should not have to remember to launch each review manually.

Show three separate outcomes: **draft produced**, **agent checks complete**, and
**human publication approval**. A draft with unresolved issues remains available
for diagnostic export. Agent checks never impersonate a human acceptance action.
The system should state what was checked, by whom, against which version, and what
still needs attention. Manuscript quality is an evidence assessment, not a model
confidence score or guarantee of publication.

## Roles and accountability

Keep the production default at **three child agents at a time plus the parent**.
These are responsibilities and concurrency limits, not the fourteen-stage desktop
experiment. Multiple bounded rounds can require additional sequential workers;
the UI must show the actual total and current active count.

| Role | Required work and structured output |
| --- | --- |
| Coordinating author | Maintain the claim/dependency inventory, write the draft, explain changes or reasoned disagreements, preserve limitations and provenance. Cannot close its own objections or approve release. |
| Proof / method verifier | Inspect all claimed theorems, assumptions and dependencies; check proof steps, edge cases and counterexamples. For empirical or software papers, review method validity, analysis and reproducibility instead. Identify what was proved, checked finitely, merely proposed, or not run. |
| Source / citation verifier | Match every evidence-dependent claim to the frozen source and precise passage; assess support versus contradiction, version, access level and bibliography completeness. Identify uncited claims, unverifiable quotations, unsupported source attributions and faulty metadata. |
| Literature / contribution reviewer | Check closest prior work against each proposed contribution; maintain queries, providers, dates, result limits, access gaps and comparisons. Distinguish known results, limited-search apparent differences, unclear priority, and unsupported novelty claims. |

Required coverage depends on paper type and its claims. An expository paper can
explicitly make no novelty claim; a source-only review can have no new theorem.
Record a reasoned, visible applicability decision. An agent cannot silently mark
a difficult check “not applicable” to remove a blocker.

Independent final reviewers must use fresh worker/thread identities and original
sources, and must not verify prose or proofs they authored. The controller assigns
identities; agents cannot supply alternate display names to pass independence
checks. Fresh context reduces shared assumptions but does not guarantee statistical
independence or remove errors shared by the underlying model.

## Bounded production sequence

1. **Freeze the brief and review requirements.** Record manuscript/project IDs,
   paper type, target claims, source versions, allowed services, total token/time
   ceiling, concurrency and revision limit. Give every theorem, contribution and
   evidence-dependent claim a stable ID linked to its final section. Unmapped
   substantive prose receives a coverage-review flag rather than a semantic verdict
   from a keyword rule.
2. **Acquire and freeze literature.** Use the application's existing search,
   ingestion, deduplication and citation-graph services to build the allowed corpus.
   The controller may execute bounded query proposals through configured adapters;
   text-only agents keep their current filesystem/network restrictions. Store actual
   query receipts and imported result snapshots. Metadata and abstracts remain
   discovery evidence until the relevant full text is lawfully available.
3. **Research and draft.** The parent uses bounded assignments and writes against
   the claim inventory. Preserve conjectures, negative results and unsupported
   gaps. The draft may complete even when some review requirements remain unmet.
4. **Audit the complete candidate.** Launch the three specialist reviewers on the
   same frozen candidate and source set, independently of the author's conclusions.
   Review full sections and cross-section dependencies. If context limits require
   chunks, retain an explicit coverage manifest and an overall consistency pass;
   truncation must produce a gap, never an implicit pass. The current optional
   800-character skeptical-review input is insufficient for this stage.
5. **Revise and recheck.** Turn objections into existing `revision_review` comments
   with measurable acceptance criteria. The author responds and proposes changes.
   A different verifier checks the exact response and revised candidate. Permit at
   most two revision cycles by default, inside the original budget. Preserve
   justified disagreement and unresolved objections; do not decide correctness by
   majority vote. Stop on exhaustion, repeated unchanged failures, cancellation or
   missing evidence, and return the saved partial package.
6. **Final assessment and human review.** Recheck coverage, claim support, citations,
   bibliography and regressions against the final candidate. Present specialist
   results and exact blockers. Use the existing human acceptance, authorship and
   publication approval actions. Build the final bundle only through the existing
   package workflow; a model-produced reviewer report is not publication approval.

An external search failure, unavailable full text, or exhausted result limit is a
coverage gap. The controller must not silently substitute fake provider output or
label an attached-source search as a search of the broader literature. Before
enabling a live adapter, verify its current access requirements and supported error
behavior. This plan does not authorize credentials, paid services or new spending.

## Data and validation contract

Extend the existing versioned research contracts rather than adding a parallel
research system. Each specialist report should record:

- Role, controller-assigned agent/thread identity, authored-input conflicts,
  manuscript and candidate hash, source/packet hashes, and coverage IDs.
- Per-claim assessment: supported within scope, contradicted, unresolved or
  explicitly not applicable; exact limitations and evidence references.
- Objection IDs, severity, acceptance criteria, historical-claim corrections,
  and locators for the statement before and after correction.
- Checks proposed versus actually executed, tool/environment/input/output hashes,
  recorded outcomes and reproduction scope.
- For novelty: actual searches, screened closest works, comparison dimensions,
  dates and gaps. “Nothing found” cannot become an unrestricted novelty assertion.

Use deterministic checks for IDs, report coverage, assignment scope, packet/source
hashes, execution receipts, actor separation, staleness and unresolved bibliography
markers. Semantic support, proof adequacy and ambiguity belong in specialist
assessments and review flags. Quoted corrections must identify the historical
artifact/packet so the old assertion is not treated as the current claim.
Reuse the evidence-availability validation from `evaluation_workflow.py` through
a shared helper where necessary; do not import the fourteen-stage orchestrator
into production or maintain two divergent validation rules.

Required computational checks must bind to actual `compute.py` run manifests or
an equally explicit existing verification artifact. A sentence saying “I ran it”
does not count. Preserve the current approval and execution boundary for ingested
code. For unattended checks, use reviewed, allowlisted deterministic routines;
new model-generated code waits for the existing hash-bound execution approval.
Finite checks support their tested scope and cannot be promoted to a general proof.

### Version binding without circular hashes

Reuse `revision_review.candidate_hash` and `evidence_basis.collect`. Extend their
existing exclusion of review events deliberately for any new assessment records:
the candidate digest must bind scientific content and its source dependencies,
while excluding the assessment's own result fields. Otherwise adding a review
would invalidate itself. Keep a separate final package basis that includes all
review records and their exact versions. Version this policy and test it explicitly.

Adding a response or verification event must not change the scientific candidate
digest; changing a theorem, cited source, source bytes, proof, result or other bound
candidate dependency must invalidate the affected reviews. A changed dependency
can require a new review of an otherwise unchanged section. Existing historical
approvals remain recorded, but cannot be silently relabeled as current coverage.

## Integration points and delivery order

### 1. Make required quality checks enforceable

- Extend `research_contract.py` and `research_tasks.py` with versioned manuscript
  review requirements and specialist result contracts. Preserve ordinary bounded
  research tasks and older snapshots as readable historical data.
- Represent the review campaign using linked existing `ResearchObject` records,
  existing task/agent records and typed evidence references. Add only lifecycle
  orchestration needed to join the current services; do not duplicate their ledgers.
- Extend `audits.py` to require the expected specialist coverage for new production
  manuscripts, including explicit gaps for legacy manuscripts entering that path.
  A missing required record must block even when an agent deletes its reference.
- Have `manuscript_path.py` and `publication_packages.readiness` consume the same
  manuscript-specific assessment. Keep unrelated project research from granting
  readiness or blocking an otherwise unrelated manuscript.

Acceptance: a manuscript cannot become agent-reviewed or release-ready with a
missing role, uncovered claim, stale result, unresolved serious objection, missing
required execution receipt, or bibliography marker. Diagnostic exports still work.

### 2. Orchestrate independent reviews and bounded repair

- Extend `research_runner.py` and the existing worker operations/schemas for draft,
  audit, response and final recheck. Preserve the parent lineage, original child
  reports, progress backpressure and cancellation handling.
- Reserve capacity for required final review before drafting. The recent unused
  allowance reclamation applies only to verified unused capacity; no phase may
  consume another required future phase's protected reservation.
- Use one campaign-wide budget across linked stages. Starting another stage or
  task must not reset its token/time ceiling. Missing usage retains reservations.
- Persist phase IDs and dispatch state before model calls. On restart, recover
  interrupted work without duplicating a call or silently starting a new campaign.
- Create/verify objections through `revision_review.py`, with controller-bound
  identities and hashes. Existing human approval requirements stay explicit.

Acceptance: three-role review, two bounded repair cycles and final assessment can
complete with at most three concurrent children. Partial output survives every
failure; no self-verification, unlimited retry or hidden budget extension occurs.

### 3. Connect literature and reproducibility evidence

- Reuse `literature.py`, `providers/scholarly.py`, ingestion, citation graph,
  source deduplication and `compute.py` for acquisition and receipts.
- Add bounded, persisted search proposals and coverage checks. Provider outages,
  simulated results, unavailable access and unexecuted plans remain visible gaps.
- Add source passage support assessments and contribution-to-prior-work comparisons
  to the existing evidence graph. Recheck metadata against its cited source.
- Permit authenticated or paid integrations only when separately configured and
  authorized; do not weaken text-only worker permissions to perform acquisition.

Acceptance: a fabricated citation, abstract-only inference about an unseen proof,
claimed-but-unrun computation, or empty search cannot satisfy its required check.

### 4. Expose one production workflow and validate it

- Extend `research_api.py`, existing manuscript endpoints and the Research/
  Manuscript UI with required roles, coverage, active phase, remaining limits,
  unresolved objections and review actions. Default new production manuscript
  runs to this sequence; label ordinary exploratory research separately.
- Generate the evidence package with the original draft, reviewed revisions,
  source/search manifests, role reports, execution receipts and dispositions using
  existing research artifact and publication exporters.
- Update `PRODUCTION-WORKFLOW.md` and the acceptance record. Leave the frozen pilot
  and fourteen-stage experiment unchanged.

Acceptance: an unattended bounded run produces a coherent manuscript and a complete
review history or an honest partial handoff. The user can inspect every release
blocker without decoding worker logs.

## Verification and first advanced manuscript

Add focused regressions to the existing research, publication, manuscript-path,
literature and unified-workflow tests. Cover:

1. Missing specialist, duplicate role, uncovered theorem and truncated input.
2. Wrong-source citation, unsupported quotation, duplicate DOI/version conflict,
   unavailable full text and source substitution after review.
3. Missing search receipts, incomplete provider coverage, simulated search and
   unsupported novelty claims; expository “no novelty claim” remains explicit.
4. Self-verification under a different display name, stale candidate/response/
   criterion, and re-opening an objection after a relevant revision.
5. A fabricated execution receipt, finite checking overstated as general proof,
   circular assessment hashes, and unlinked project evidence incorrectly reused.
6. Paraphrased false absence, quoted correction, different missing reports and
   historical packet scope; accepted diagnostics with bibliography placeholders
   still blocked from release.
7. Protected final-review budget, conservative missing usage, cancellation,
   duplicate dispatch, maximum concurrency and the revision-cycle ceiling.

Use temporary synthetic storage for implementation tests. Then run one more
advanced bounded manuscript acceptance case on finite partitions and function
algebras: refinement, intersections/coarsening, separating functions, proof
dependencies and an intentionally false generalization. Include a small frozen
set of genuine primary references with checked locators and known related results.
Require the agents to identify the seeded error, correct it, and describe any
contribution as exposition unless the evidence supports a narrower novelty claim.
Independently reproduce finite checks using reviewed routines.

For the first live acceptance attempt, start with the previously exercised
96,000-token / 900-second ceiling and at most two repair cycles. Stop with a partial
package if that budget cannot cover the added review work; a larger allowance must
be explicitly authorized, not obtained by launching another full-budget task.
Use the already authenticated local profile, no paid API services, and no original
manuscript edits. Keep the diagnostic draft and its evidence in temporary storage.

Proceed to an original manuscript from the publication collection only after this
quality workflow passes, with a selected question, frozen source set and explicit
research limits. Agent checks should reduce the human review burden while leaving
scientific responsibility and the publication decision with the author.

## Next decision

Approve implementation of steps 1–4 as a scoped follow-up, then perform the advanced
acceptance test above. This planning request does not itself implement those steps.
Continue in this thread while the reviewed integration context is useful. For
implementation, use `gpt-6-sol` at high reasoning: the cross-service identity, budget
and evidence-binding changes warrant careful reasoning. Use deterministic tests
before spending live research usage.
