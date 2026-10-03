# Batch A — existing Paper Writer project

**Prepared, not executed.** This batch needs explicit authorization because the user's
AGENTS.md protects local database access. The database path comes from the existing local
launcher; its contents have not been read for this work.

Targets:

- Database: `C:\Users\brian\Documents\PoP\Tools\Paper-Workbench\data\workbench.sqlite3`
- Preserved source artifacts: the same checkout's `data` directory.
- Project: one non-deleted project named exactly `Paper Writer`; stop if missing/ambiguous.
- New private output: `output/research-semantic-owner-batch-01` (must not exist).

Authorized actions if the user approves this batch:

1. Read the named project and its preserved source/report records.
2. Create a consistent private SQLite backup in the new output directory.
3. Build at most one 512-card batch of missing/changed local semantic vectors for that
   project. Reuse current vectors; replace/remove only stale research-card cache entries
   for the selected model. Do not change claims, manuscripts, sources or reviews.
4. Save four retrieval previews: finite ultrametric observations; asymmetric refinement
   and inter-cell distances; prior art on non-Hausdorff distance topologies; counterexamples
   to symmetric lifts. These are discovery previews, not scientific conclusions.
5. Report cache coverage, remaining items, skipped/corrupt evidence, and weak/overlapping
   candidates. Stop after this batch; no automatic continuation or model research agents.

Model: pinned local MiniLM, two CPU threads. Paid API calls and research-agent tokens: zero.
The operation is bounded by 512 newly encoded items, 4,096 characters per semantic input,
and existing source scan limits. It may take several minutes; no hard wall-time claim is
made. Stop on missing/corrupt model assets, fatal integrity failures, schema errors, ambiguous
project selection or inability to create the backup. Do not run migrations or load `.env`.

Reviewable command (without `--execute`, it only prints this plan and never opens the DB):

```powershell
$env:WB_LOAD_DOTENV = 'false'
$env:WB_RESEARCH_SEMANTIC_MODEL = 'minilm'
$env:PYTHONPATH = 'C:\Users\brian\Documents\PoP\Tools\Paper-Workbench\src'
& 'C:\Users\brian\Documents\PoP\Tools\Paper-Workbench\.venv\Scripts\python.exe' `
  'C:\Users\brian\Documents\PoP\Tools\Paper-Workbench\scripts\research_semantic_local_batch.py' `
  --database 'C:\Users\brian\Documents\PoP\Tools\Paper-Workbench\data\workbench.sqlite3' `
  --data-dir 'C:\Users\brian\Documents\PoP\Tools\Paper-Workbench\data' `
  --project-name 'Paper Writer' `
  --output 'C:\Users\brian\Documents\PoP\Tools\Paper-Workbench\output\research-semantic-owner-batch-01'
```

After approval, append `--execute`. The execution path has been exercised against a
disposable synthetic database, including consistent backup, cache reuse and output records.
The private backup/previews may contain project content and should not be published.
