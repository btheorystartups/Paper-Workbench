# Counter compatibility implementation — 2026-10-06

## Scope and authorization

The user's continuation approved the recommended offline compatibility guard and
gpt-5.5 / low research selection. This phase used controlled synthetic fixtures
and temporary storage. No live inference, manuscript agents, paid services,
secrets, default databases, original manuscript edits, commits, pushes, or
deployment were performed. The earlier dirty checkout remains intact.

## Implemented changes

- The research settings and worker fallback now select gpt-5.5 / low. The general
  chat model default remains gpt-5.6-sol; explicit environment overrides remain
  authoritative. No existing profiles, environment files, or historical launch
  scripts were edited.
- Bounded draft and revision operations check the reviewed model/runtime pair
  before creating their model thread or starting their model turn. The guard
  allows gpt-5.5 with pinned runtime 0.154.0. It rejects the known gpt-5.6-sol
  Code Mode incompatibility, unreviewed models, and unreviewed runtime versions.
  Text-only operations do not require this counter transport check.
- Counter descriptors explicitly set deferLoading=false. The investigation
  already demonstrated that this flag alone cannot repair Sol's tool mode.
- Provenance separates offline capability review, descriptor registration,
  successful counter invocation, and a counter receipt matching the exact final
  section text. Successful invocation alone does not establish a final match.
- Failures use three fixed reasons, persisted only for the matching failure class
  at input_check and bound to the controller's call span. The UI displays escaped
  diagnostic text. Arbitrary model names and error text are not persisted through
  this diagnostic field.

This is a conservative, version-bound offline compatibility review, not an
attestation of the authenticated provider's current catalog or model availability.
Existing account/model/effort checks remain necessary. No custom production model
catalog, Code Mode host, fallback model, extra revision cycle, or relaxed length
gate was introduced. Conservative ledger charging remains in effect when actual
terminal usage is unavailable, even for a compatibility refusal before inference.
Scientific readiness and release blockers remain independent of tool transport.

## Verification

205 distinct tests passed across these focused runs (overlapping tests counted
once):

1. Counter compatibility, research worker, actual pinned-runtime counter exposure,
   manuscript length, and Codex local tests: **178 passed**.
2. Counter compatibility, pinned-runtime exposure, research transport, and task API:
   **26 passed**, including six additional transport/API tests.
3. Focused manuscript diagnostics, cancellation, revision capacity, and length
   gates: **21 passed**, 101 unrelated cases deselected.

The actual runtime tests use a fake loopback Responses provider, fresh temporary
profiles, and synthetic text. They verify direct counter dispatch and callback
results with final JSON outputSchema retained. They do not test live model
compliance or authenticated backend behavior. The existing missing-invocation
case remains observable separately from registration.

Ruff passed for the new helper and its tests. The touched Python set passed with
existing E501 long-line findings excluded. Node syntax validation and controlled
UI rendering/escaping checks passed. Two existing FastAPI/Starlette deprecation
warnings appeared. git diff --check passed; status/stat were reviewed without
staging or attributing earlier changes to this phase.

All **131 frozen pilot files** retained their baseline SHA-256 hashes. The latest
prior acceptance research-package.zip also remained unchanged at
`1c0864f1a76b2f88a5d2296c64097f9cef50c089fbc89ab0b5ed66ea042f198d`.
See [preservation receipt](2026-10-06-counter-compatibility-preservation.json) and
[offline investigation](2026-10-05-counter-exposure-investigation.md).

## Remaining acceptance step

Live acceptance requires fresh explicit authorization with numeric token and
setup-inclusive time ceilings, one attempt, and no automatic retry. Prepare a
new temporary output folder and launch specification explicitly selecting
gpt-5.5 / low: the previous historical harness hardcodes gpt-5.6-sol and must not
be reused unchanged or edited in place. Preserve the agreed scientific revision
cycle, source bindings, adversarial review, length checks, and release blockers.
If authenticated model/effort preflight refuses the selection, stop without
fallback. Record actual counter requests, successful receipts, exact final text
matches, output-schema behavior, reviewer dispatch, and readiness outcomes.

Continue that acceptance in this thread because it depends on the active patch,
counter investigation, and preservation evidence. No further model run is needed
to complete this offline phase. Model selection does not establish manuscript
quality or readiness for submission.
