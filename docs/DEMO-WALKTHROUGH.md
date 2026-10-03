# Paper-Workbench: evidence to a reviewed manuscript

The walkthrough recorded on 2026-09-11 uses the actual local interface, invented research,
and fake application providers. The latest guided version runs about 7 minutes 9 seconds
and uses the account's **Brian** cloned voice through ElevenLabs with a warmer, more expressive
explainer preset. The September 12 fresh take naturally matches the previous overall pace.
Its natural sentence pauses replace the previously inserted silence; a fixed gain replaces
noise gating and adaptive cleanup. The final video uses one uninterrupted audio master.
Earlier versions are retained separately. Fifty-five timed gold outlines and labels point
to the referenced controls on captured screens, including intermediate review states.
The delivered
MP4 has captions and chapter markers retimed to the new narration, with a separate SRT
and transcript. Video files remain outside the Git repository. Reusable capture,
narration, and rendering code is in [scripts/demo_video](../scripts/demo_video/README.md).

## Chapters

| Time | Workflow |
| --- | --- |
| 00:00 | Introduction and demo scope |
| 00:19 | Sources, access levels, excerpts, and locators |
| 00:53 | Claims and evidence links |
| 01:21 | Manuscript sections, purpose, and linked claims |
| 01:47 | Research brief and inspectable context |
| 02:23 | Conversation modes and follow-up questions |
| 02:58 | Requesting a proposed edit |
| 03:36 | Human revision of a proposal |
| 04:06 | Applying the reviewed text |
| 04:35 | Proposing and approving undo |
| 04:57 | Manuscript audit and skeptical review |
| 05:24 | Exporting a draft and provenance manifest |
| 05:54 | Literature, Compute, Figures, and Submissions overview |
| 06:31 | A practical first writing session and current limits |

## Practice alongside the video

Use the [isolated offline demo](MANUSCRIPT-CHAT.md#offline-demo). It creates a prepared
synthetic project and binds to loopback. Both its database and exported artifacts live
under its disposable temporary folder; they are removed when the server exits normally.
Keep any exports you want before stopping the demo. Do not put real research in this demo.

1. Inspect **Sources**, open the synthetic source, and read its excerpt and locator.
2. Inspect **Claims** and its evidence link. The source remains explicitly unverified.
3. Open the manuscript and choose **Discuss section**.
4. Save a **Research brief** that records your question, audience, constraints, and next step.
5. Inspect **Context for the next reply** before asking for a revision.
6. In the fake demo, send the complete replacement below to exercise the review workflow:

   ```text
   revise: Across ten pilot runs, we observed a 12% improvement. These preliminary findings need replication before broader conclusions can be drawn.
   ```

7. Compare **Before** and **Proposed text**. Open **Revise this proposal**, change the
   last sentence to emphasize the small sample, and choose **Save revised proposal**.
8. Review the new proposal and choose **Apply shown edit**. Inspect the current section.
9. Choose **Propose undo**, inspect the pending reversal, and approve it to restore the original.
10. Run the manuscript audit. Export a draft, then inspect the files and their manifest.

## Prompts for a live-provider writing pilot

These are suggested prompts for a future authorized live-provider pilot. In the current
fake demo, ordinary dialogue produces visibly simulated replies; only the special
`revise:` command above supplies deterministic replacement prose.

- **Explore:** “Given this section and its linked evidence, identify three possible
  arguments. Separate evidence-backed observations from assumptions.”
- **Challenge:** “What would a skeptical reviewer challenge? Point to the relevant
  claim or excerpt, and say what evidence is missing.”
- **Explain:** “Explain this paragraph to a methods researcher from another field.
  Preserve uncertainty and do not invent citations.”
- **Compare:** “Compare these two interpretations. Which is supported by the current
  evidence, and where would each overstate the result?”
- **Plan:** “List the work needed before this section is defensible. Distinguish
  writing changes from additional analysis or evidence collection.”
- **Act:** “Propose a shorter version of this section. Preserve all limitations and
  supported numerical statements. Do not add claims or citations.”
- **Follow-up:** “Keep the first sentence. Revise the rest for the audience in my brief,
  and explain why the new wording is supported.”

Update the brief when decisions change. Each reply includes the latest 12 messages,
the saved brief, and current section context; it does not automatically remember the
entire project. Branch a turn when exploring an alternative direction.

## What to expect today

Chat and reviewed edits are implemented. Approving an edit changes one section's prose,
not its evidence or claim support. Stale proposals and stale undo requests are refused.
Audits highlight work to resolve; exports do not submit or certify a paper.

Staging has closed registration and fake providers. Real research remains excluded from
staging, and live-provider writing quality and real IdP/PKCE remain unverified for this
slice. A dedicated terminal CLI/MCP assistant, multi-section edits, and automatic citation
placement remain future work. HTTP dialogue endpoints are available to API clients.

During capture, assertions verified that pending proposals and human revisions preserved
the manuscript, approval applied the exact reviewer text, undo awaited approval and
restored the original, the brief appeared in context, and export completed. The browser
reported no JavaScript errors. The final MP4 passed a complete audio/video decode.

See [manuscript chat](MANUSCRIPT-CHAT.md), the [capability matrix](CAPABILITY-MATRIX.md),
and the [deployment verification record](audit/2026-09-11-manuscript-chat.md).
