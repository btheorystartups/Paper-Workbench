# Evidence-grounded proposal workflow

This workflow prepares a research-collaboration or applied/client-pilot proposal from
materials that are already authorized within one Paper-Workbench project. It does not
make a client commitment, verify every scientific claim, authorize cross-project reuse,
or establish that a method will benefit a client.

## Use it

1. In **Sources**, ingest selected files through the normal project intake. Review
   extraction warnings before relying on a passage. Then open **Proposals**, create a
   proposal, and record the client question, audience, aims, success criteria,
   constraints, known resources, and unanswered questions. Leave unavailable budget,
   schedule, and commitments blank; the workflow renders those as unspecified.
2. Add each project-local source to an **author**, **client**, or **background**
   collection. These labels describe proposal evidence only; they never change a user's
   access role. Choose **Index current extraction** to create bounded passages with a
   stable source checksum and page or character locator.
3. Review source coverage, use **Inspect bounded evidence pack**, and retrieve passages.
   Metadata-only sources, missing text, unreadable/scanned extraction, stale/deleted
   passages, and failed URL fetches stay visible as limitations. Retrieval is lexical
   discovery, not evidence that a method transfers. Use the project **Dialogue** tab for
   follow-up questions after pinning the selected project sources; its replies remain
   reviewable input rather than client commitments.
4. Generate the fit matrix. Every row separately labels the client requirement,
   established material, model inference, and proposed validation. `tentative`,
   `insufficient_evidence`, and `no_fit` are valid outcomes. An integrity/correction
   notice prevents an unqualified benefit promise.
5. Generate and inspect an outline, then a multi-section draft. Each section is a
   proposal until reviewed. Save manual changes with its displayed revision; the server
   rejects stale/concurrent edits. Approve, reject, or undo the current revision.
6. Save **v1** with a human review note. This atomically snapshots the brief, outline,
   prose, fit matrix, citations, source hashes, evidence passages, and approval state.
   Further edits remain a mutable v2 draft and cannot alter v1. Compare versions before
   exporting.
7. Export a selected version as Markdown, HTML, or DOCX. The output is saved under a
   version-specific content-addressed artifact namespace. PDF is offered only when the
   local renderer probe succeeds; otherwise the API reports that no PDF was produced.

The evidence-pack endpoint is the proposal context inspector. Only listed, current,
proposal-member passages are available for generated citations. A citation resolving to
another project, a deleted passage, or a fabricated ID is rejected server-side.

## Bounded URL intake

The proposal URL form fetches one chosen public HTTP(S) page. It does not execute script,
crawl a site or repository, or automatically import linked documents. The fetcher checks
the initial address and every redirect against private, loopback, link-local, reserved,
and metadata-network destinations; it follows at most four redirects and streams at most
5 MB. A fetch snapshot records URL, date, resolved URL, hash, byte count, and extraction
result. Rendering failure is shown as a limitation.

## Fake mode and live providers

`WB_PROVIDER_MODE=fake` is the default. Proposal generation calls the existing metering
funnel but produces deterministic, visibly simulated, network-free output. It is useful
for exercising workflow integrity, not for measuring writing quality.

In live mode, proposal generation refuses to call a provider unless the request explicitly
sets `use_live=true`, a usable configured provider key exists, and the project has an
available token budget. The configured effective model is recorded with each generation.
If live configuration resolves to a fake provider, the stage fails instead of relabeling
the output as live. Do not provide client material to an external provider without an
explicit permission decision.

## Migration and local demo

Apply migration `b3c4d5e6f708` (the merge head) to a managed database after backing it
up and using the approved maintenance process. For a local disposable database:

```powershell
$env:PYTHONPATH = "$PWD\src"
$env:WB_LOAD_DOTENV = "false"
python -m alembic upgrade head
```

Run the deterministic synthetic demonstration without dotenv, real sources, network, or
paid model calls:

```powershell
$env:PYTHONPATH = "$PWD\src"
python scripts/proposal_workflow_demo.py
```

The script creates a temporary SQLite database and temporary artifact directory, imports
synthetic author/client text, retrieves a passage beyond the start of a document, produces
both a tentative and a no-fit row, creates v1, and writes version-bound synthetic exports.

## Verification boundary

The offline tests cover proposal persistence/migration, extraction limits, injection as
untrusted data, cross-project rejection, idempotent fake generation, stale edits, version
comparison, export binding, URL failure, and provider timeout handling. They cannot
establish real proposal-writing quality, scientific validity, client applicability,
provider availability, live-cost behavior, or deployment readiness.
