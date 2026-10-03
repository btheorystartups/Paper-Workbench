# Local semantic discovery and coverage

Research now offers **Semantic + lexical** matching and **Broad** or **Focused**
discovery. Broad is the UI default because this workflow favors finding distinct leads;
weaker semantic candidates are explicitly labeled. API callers retain lexical/focused
defaults for compatibility. Task creation freezes mode, thresholds, model identity,
matches, potential overlaps, source locators and report lineage in the existing contract.

First click **Build / refresh local semantic index**, then **Preview relevant evidence
and gaps**. Each index request handles at most 512 missing/changed cards. Repeated requests
reuse unchanged vectors and report how many remain. Preview and task creation never
silently build an index, download weights, or select an embedding API. If local setup or
index entries are missing, the response clearly reports lexical fallback or partial indexing.

## Matching and ownership

The local encoder is the Apache-2.0 Sentence Transformers
[all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).
Its ONNX weights and tokenizer are pinned to revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41` with SHA-256 verification. ONNX Runtime
1.30.0 and tokenizers 0.23.2 are optional pinned dependencies. Inference uses two CPU
threads; source text is never sent to a hosted model. Setup alone downloads public assets.

Passage text is embedded without filenames. Structured report fields contribute their
statement/scope or query/coverage/outcome text, not JSON field names. Semantic input is
bounded to the first 4,096 characters per item/query. All tokenizer overflow windows
within that prefix are pooled; MiniLM's normal 256-wordpiece limit does not silently
discard the rest of that prefix. Full evidence text and locators remain unchanged.

Vectors are cached in existing `Embedding` rows under `research_card`, scoped by project,
model version and exact embedding-text hash. Deleted, stale, incompatible, zero, non-finite
or malformed vectors cannot match. Index refresh only removes obsolete research-card cache
rows for its own project/model. It does not touch manuscript text, claims, approvals or
the older object/source embedding index. No schema migration is required.

Hybrid ranking combines lexical relevance with cosine similarity and penalizes repetition
of content and source/task families. Focused candidates require similarity >=0.45; Broad
allows >=0.20 and labels matches below 0.45 as weak leads. These are heuristic discovery
thresholds, **not probabilities or mathematical confidence scores**. Broad discovery trades
precision for recall; topics may still be missed and unrelated candidates may appear.

Selected pairs with similarity >=0.82 are flagged as possible overlap **or disagreement**.
They are never merged or promoted by similarity. Connected groups get one follow-up owner
so agents can compare related passages together. This can produce uneven workloads; distinct
agent counts are not a coverage metric. Scientific independence, entailment, scope and
semantic equivalence still require review. Existing exact-text deduplication now keeps
identical findings with different citation sets separate, preserving both evidence trails.
Simulation records explicitly say they establish neither research nor past search coverage.

## Verification and limits

The real local model was exercised with outbound socket connections blocked. Development
and holdout probes are small hand-authored synthetic datasets, not independent validation
on this manuscript or the scientific literature. No threshold was changed after the holdout.

| Probe set | Lexical expected passage in top 3 | Hybrid expected passage in top 3 |
| --- | --- | --- |
| Development, 8 queries, Focused | 1/8 | 3/8 |
| Development, 8 queries, Broad | 1/8 | 6/8 |
| Holdout, 8 different queries, Broad | 2/8 | 7/8 |

Eight out-of-domain holdout queries plus a cooking query returned no candidates in this
small corpus. Negated and scope-reversed statements stayed separate. A warm index embedded
zero new items and reused all 11 current cards. No external inference calls or network
attempts occurred during the acceptance runs. Actual account/token savings were not measured.

The larger local all-mpnet-base-v2 model tied MiniLM on both development configurations;
MiniLM therefore remains the default (about 23 MB of weights versus 110 MB). MPNet is an
explicit optional selection, not an automatic fallback. It was not selected using the
holdout. The model registry pins both artifacts. No broad mathematical-relevance claim
follows from these examples; corpus-specific evaluation is the next useful validation.

## Setup and reproduction

Use the project virtualenv and set `WB_LOAD_DOTENV=false` and `PYTHONPATH=<checkout>/src`.
Install the `research-semantic` optional extra, then run:

```text
python scripts/setup_research_semantic.py
python scripts/research_semantic_acceptance.py --recall broad --suite development --output <fresh-directory>
python scripts/research_semantic_acceptance.py --recall broad --suite holdout --output <another-fresh-directory>
```

Default assets live in `output/research-semantic-minilm-v1`. An operator can set
`WB_RESEARCH_SEMANTIC_MODEL_DIR` to another explicit model directory. To deliberately
select the alternative, set `WB_RESEARCH_SEMANTIC_MODEL=mpnet` before setup and startup;
its default directory is `output/research-semantic-mpnet-v1`. No environment file is edited.

Routes: authenticated reviewer `POST /projects/{id}/research-retrieval` accepts `mode`
(`lexical`/`hybrid`) and `recall` (`focused`/`broad`); coauthor
`POST /projects/{id}/research-retrieval/index` updates only the bounded local vector cache.
Task creation accepts `retrieval_mode` and `retrieval_recall` alongside `reuse_prior_research`.
Stored source/character/agent/task limits from RESEARCH-RETRIEVAL.md still apply.

No owner database has been accessed for this implementation. The prepared next operation
is described in [Batch A](SEMANTIC-APPROVAL-BATCH.md). No research agents, API spending,
external publishing, migrations, commits or pushes are authorized by this document.

## Final verification — 2026-10-01

The owning checkout passed all 391 tests in 463.58 seconds. The only warning was
Starlette's existing httpx TestClient deprecation. Focused Ruff, JavaScript syntax,
and Git whitespace checks passed.

The separate eight-query synthetic holdout retrieved the intended passage in the top
three for 7/8 hybrid queries versus 2/8 lexical queries. The remaining miss was
“null space”: the intended kernel definition did not appear in the top three.
Eight unrelated negative queries and a cooking query produced no candidates.
These small synthetic results do not establish mathematical equivalence or real-corpus recall.

Browser checks exercised index reuse, weak-lead labels, source titles, and task creation.
An offline task completed with three distinct cards assigned once each across three
children, zero research-model tokens, and a frozen hybrid/broad retrieval contract.
The downloaded private task ZIP passed CRC and every manifest size/hash check; its
retrieval snapshot matched the API task. This was an offline handoff check, not live research.

Evidence is saved in `output/research-semantic-final-20261001`: `verification.json`,
`query-results.json`, `handoff-verification.json`, `tests.xml`, the private synthetic task
ZIP, and browser screenshots. The temporary synthetic server was stopped after verification.
