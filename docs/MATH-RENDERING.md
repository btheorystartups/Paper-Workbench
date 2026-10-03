# Mathematical PDF rendering

PDF exports now typeset explicit LaTeX math using a pinned offline MathJax SVG worker
and the existing WeasyPrint renderer. Supports inline `\( ... \)` / `$...$`, display
`\[ ... \]` / `$$...$$`, standard base/AMS commands, matrices and aligned equations.
Vectors remain sharp when zoomed. They are SVG paths, so formula text is not reliably
copyable from PDF; machine-readable reports and TeX remain the authoritative text.

Install Node.js and run `npm ci --ignore-scripts --no-audit --no-fund` in
`src/workbench/math_runtime`. The lockfile pins dependencies. Runtime typesetting is
offline: no document JavaScript, web fonts, extension fetching or TeX shell execution.
The worker has a 30-second timeout and equation/input/output bounds. External-resource
and executable TeX commands are rejected, and returned SVG is restricted to vector
elements. This is math notation support, not arbitrary document-TeX execution.

If math is present and the math runtime or WeasyPrint is unavailable, export fails with
an actionable error instead of silently producing a plain-text mathematical PDF.
PDF provenance records renderer and equation count. Plain-text exports retain their
existing behavior. TeX manuscript exports preserve validated math and load AMS packages.
The worker prompt now asks future reports to use delimited standard LaTeX with JSON
escaping. No live model operation was started for this change.

Existing undelimited prose/formulas are not automatically reinterpreted: ambiguity
can change mathematical meaning. Custom macros from an imported manuscript require
explicit expansion or support; documents such as the supplied reference are formatting
examples, not executable instructions. The manuscript's full document layout is not
reconstructed by the math-span renderer.

## Narrow-run presentation demonstration

`output/research-math-20261001/results-math.pdf` has an explicit typeset presentation
of the two previously recomputed finite matrices, their topologies, and the directed
ultrametric inequality, followed by the unchanged original report text. No original
claim or review was modified. `research-artifacts-v3.zip` preserves the byte-identical
research ZIP, links to v2 by hash, and includes presentation source and rendering metadata.

Reproduce with dotenv disabled and the checkout's src on PYTHONPATH:

```powershell
python scripts/research_math_preview.py `
  --input output/live-research-acceptance-narrow-64k-20260930/lifting-live.zip `
  --previous-package output/research-artifacts-final-20261001/research-artifacts-v2.zip `
  --output output/a-new-math-preview-directory
```

The demonstration is bound to the exact narrow input hash. It does not reuse scientific
content from the user's separate Boolean-calculus reference or certify the lifting claim.

## Research and citations distinction

Current live delegated workers read frozen attached sources only; browser/search tools
are disabled. The schema records citations and searches, but a citation record is not
an independently verified source-support judgment. The offline worker's prior-art role
is a transport simulation. Live external literature discovery requires a separately
designed and authorized tool-enabled execution path.

Persist source identity/version, DOI/URL, locators, excerpts, search coverage, and claim
comparisons as reusable evidence. Pass only relevant excerpts to later agents. Prompt
caching can optimize repeated input prefixes; it does not supply missing knowledge or
replace source retrieval. This worker currently records total usage, not measured cache
savings; no ChatGPT-plan quota saving is claimed from API cache documentation.

Verification: 37 focused export/research/worker/publication tests passed; the final
eight math tests (including task PDF and ZIP API downloads) passed. Selections overlap.
Source lint and JavaScript syntax checks passed. All 11 PDF pages were visually
inspected, including full-size equations on page 1. The renderer reports 10 math spans.
