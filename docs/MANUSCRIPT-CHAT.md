# Manuscript-aware conversations and reviewed edits

Implemented and deployed to the protected staging Preview on 2026-09-11, with fake
providers. Manuscript editing and server-side logout revocation passed synthetic deployed
checks. [Open Preview](https://paper-workbench-g957bc3ka-brians-projects-09f2f874.vercel.app/ui/).
Temporary test accounts were removed; registration remains closed.

## Writing workflow

1. Open a manuscript and choose **Discuss section**. An existing conversation for that
   section resumes, or a new one is created. Each section can have independent branches.
2. Ask questions or request a revision. Explore, explain, challenge, compare, plan, and act
   modes retain the same evidence rules. **Research brief** stores your question, intended
   contribution, audience, decisions, and open issues for subsequent replies in that thread.
3. Inspect **Context for the next reply**. The assistant receives the manuscript outline,
   selected section's full text/purpose/word budget, linked claims with support states,
   and their available research objects and source excerpts with locators, checksums,
   access levels, and evidence-link entailment states. Bibliographic metadata alone is
   explicitly not evidence. Unavailable/deleted evidence produces warnings, not invented text.
4. Review **Before** and **Proposed text**. **Apply shown edit** changes only the selected
   section's prose. **Reject** makes no manuscript change. **Revise this proposal** saves a
   new proposal, preserving the original and its model provenance. Unsaved revisions disable
   approval of the old proposal.
5. **Propose undo** creates another pending review; it does not undo immediately. It is
   refused if the section changed after that edit. Accepted/rejected/invalidated proposals
   remain in the conversation's history, with turn lineage and before/after text.

The section/evidence snapshot is captured before the provider call and bound by the server
to each edit. A changed section, support state, or included evidence invalidates approval;
request a fresh proposal. Conditional updates also prevent overwriting a concurrent section
edit or executing the same approval twice. Approving prose does not accept research objects,
upgrade claim support, verify sources, or modify claim/evidence links.

## Offline demo

The [video companion guide](DEMO-WALKTHROUGH.md) provides chapter times, practice steps,
and suggested prompts for a future live-provider writing pilot.

With the project's Python environment active, from this worktree's Paper-Workbench directory:

```powershell
$env:PYTHONPATH = "$PWD\src"
python scripts/preview_manuscript_chat.py
```

Open the loopback URL printed by the script. It creates only synthetic research in a
disposable temporary database, disables dotenv loading, uses fake providers, and binds
to `127.0.0.1:8879`. Stop with Ctrl+C to remove that temporary database.

In this fake demo, use `revise: Your complete replacement text` to exercise reviewed edits.
Other messages receive explicitly simulated replies. This is not live AI writing quality.
The demo does not use any existing local database or staging resource.

## Limits and deployment

- The next reply uses the latest 12 messages, the user-maintained thread brief, and current
  context. It does not automatically summarize the whole project or remember every turn.
- Selected-section context is limited to 80,000 serialized characters; the complete prompt
  also has an 80,000-character ceiling. Oversize requests fail before a provider call.
  Replacement prose is capped at 30,000 characters; model output remains capped at 4,096 tokens.
- Edits replace one section's prose. Outline restructuring, automatic citation placement,
  multi-section patches, semantic support verification, and a dedicated terminal CLI/MCP
  adapter remain future work. Existing HTTP dialogue endpoints are available to API clients.
- Migration `a91d4e7b620f` adds nullable manuscript/section references on threads and the
  shared session-revocation table. Apply it before deploying this code to a managed database.
  Tests migrate only disposable local databases. Existing unmanaged databases still require
  operator migration; `create_all` cannot add columns to existing threads.
- Live providers and real research on staging remain disabled. Synthetic writing and auth
  flows passed against deployed PostgreSQL. Real-provider writing quality and live IdP/PKCE
  remain unverified for this slice.

See [verification record](audit/2026-09-11-manuscript-chat.md).
