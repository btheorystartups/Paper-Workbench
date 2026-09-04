# Audit eval report

Generated 2026-07-20T15:06:57.346427+00:00 — deterministic audit layer only; LLM output quality is NOT measured here.

| finding code | TP | FP | FN | precision | recall |
|---|---|---|---|---|---|
| claim-cites-unaccepted-ai | 1 | 0 | 0 | 1.00 | 1.00 |
| claim-source-unverified | 1 | 0 | 0 | 1.00 | 1.00 |
| claim-verification-debt | 1 | 0 | 0 | 1.00 | 1.00 |
| manuscript-empty | 1 | 0 | 0 | 1.00 | 1.00 |
| section-no-purpose | 1 | 0 | 0 | 1.00 | 1.00 |
| section-unreferenced-numbers | 1 | 0 | 0 | 1.00 | 1.00 |
| source-unresolved | 1 | 0 | 0 | 1.00 | 1.00 |

## Scenarios

- **clean-manuscript** [OK] expected=[] missed=[] false_hits=[]
- **unverified-source** [OK] expected=['claim-source-unverified'] missed=[] false_hits=[]
- **verification-debt** [OK] expected=['claim-verification-debt'] missed=[] false_hits=[]
- **numbers-without-claims** [OK] expected=['section-unreferenced-numbers'] missed=[] false_hits=[]
- **missing-purpose** [OK] expected=['section-no-purpose'] missed=[] false_hits=[]
- **empty-manuscript** [OK] expected=['manuscript-empty'] missed=[] false_hits=[]
- **unaccepted-ai-citation** [OK] expected=['claim-cites-unaccepted-ai'] missed=[] false_hits=[]
- **unresolved-source** [OK] expected=['source-unresolved'] missed=[] false_hits=[]