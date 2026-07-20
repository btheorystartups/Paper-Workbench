"""Evaluation harness: labeled scenarios with ground-truth expected audit findings,
scored as precision/recall per finding code. This measures the DETERMINISTIC audit
layer end-to-end (graph → audit); LLM output quality is out of scope here and must
not be inferred from these numbers.

Run: python scripts/run_evals.py  (writes docs/eval-report.md)
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .services import audits, authoring, research
from .vocab import ClaimSupport, ObjectKind, SourceAccess


@dataclass
class Scenario:
    name: str
    build: object  # callable(session, project_id) -> manuscript_id
    expected_codes: set[str] = field(default_factory=set)  # per-code presence expected
    forbidden_codes: set[str] = field(default_factory=set)


def _base(session: Session, project_id: str, *, verified_source: bool = False,
          support=ClaimSupport.BOTH, section_text: str = "Prose only.",
          link_claim: bool = True, with_purpose: bool = True):
    src = research.register_source(
        session, project_id, title="Prior work", access=SourceAccess.EXCERPT_AVAILABLE,
        authors="A. Author", year=2000, doi="10.1/x",
    )
    if verified_source:
        src.human_verified = True
    excerpt = research.capture_excerpt(session, src.id, text="quote", locator="p. 1")
    result = research.create_object(
        session, project_id, kind=ObjectKind.RESULT, title="A result"
    )
    kwargs = {}
    if support in {ClaimSupport.EXTERNAL_SOURCE, ClaimSupport.BOTH}:
        kwargs["excerpt_ids"] = [excerpt.id]
    if support in {ClaimSupport.RESEARCH_RESULT, ClaimSupport.BOTH}:
        kwargs["research_object_ids"] = [result.id]
    claim = research.create_claim(
        session, project_id, text="The claim", support=support, **kwargs
    )
    ms = authoring.create_manuscript(session, project_id, title="MS")
    authoring.add_section(
        session, ms.id, heading="Results",
        purpose="report" if with_purpose else "",
        text=section_text,
        claim_ids=[claim.id] if link_claim else [],
    )
    return ms.id


def scenarios() -> list[Scenario]:
    return [
        Scenario(
            "clean-manuscript",
            lambda s, p: _base(s, p, verified_source=True),
            expected_codes=set(),
            forbidden_codes={"claim-missing-excerpt", "claim-missing-result",
                             "claim-source-unverified", "section-unreferenced-numbers",
                             "claim-verification-debt"},
        ),
        Scenario(
            "unverified-source",
            lambda s, p: _base(s, p, verified_source=False),
            expected_codes={"claim-source-unverified"},
        ),
        Scenario(
            "verification-debt",
            lambda s, p: (
                research.create_claim(
                    s, p, text="Overclaim", support=ClaimSupport.VERIFICATION_REQUIRED
                ),
                _base(s, p, verified_source=True),
            )[-1],
            expected_codes={"claim-verification-debt"},
        ),
        Scenario(
            "numbers-without-claims",
            lambda s, p: _base(
                s, p, verified_source=True,
                section_text="We saw a 2.4x speedup.", link_claim=False,
            ),
            expected_codes={"section-unreferenced-numbers"},
        ),
        Scenario(
            "missing-purpose",
            lambda s, p: _base(s, p, verified_source=True, with_purpose=False),
            expected_codes={"section-no-purpose"},
        ),
        Scenario(
            "empty-manuscript",
            lambda s, p: authoring.create_manuscript(s, p, title="Empty").id,
            expected_codes={"manuscript-empty"},
        ),
        Scenario(
            "unaccepted-ai-citation",
            lambda s, p: _ai_cite(s, p),
            expected_codes={"claim-cites-unaccepted-ai"},
        ),
        Scenario(
            "unresolved-source",
            lambda s, p: _unresolved(s, p),
            expected_codes={"source-unresolved"},
        ),
    ]


def _ai_cite(session: Session, project_id: str) -> str:
    obj = research.create_object(
        session, project_id, kind=ObjectKind.RESULT, title="AI idea", ai_suggested=True
    )
    claim = research.create_claim(
        session, project_id, text="Based on AI idea",
        support=ClaimSupport.RESEARCH_RESULT, research_object_ids=[obj.id],
    )
    ms = authoring.create_manuscript(session, project_id, title="MS")
    authoring.add_section(session, ms.id, heading="R", purpose="p", claim_ids=[claim.id])
    return ms.id


def _unresolved(session: Session, project_id: str) -> str:
    research.register_source(
        session, project_id, title="Mystery memo", access=SourceAccess.METADATA_ONLY
    )
    return _base(session, project_id, verified_source=True)


def run(session_factory) -> dict:
    """Score every scenario. Per finding code: TP (expected & found), FN (expected,
    missing), FP (forbidden-or-clean but found where clean scenario forbids it)."""
    per_code: dict[str, dict[str, int]] = {}
    rows = []
    for i, scenario in enumerate(scenarios()):
        session = session_factory()
        try:
            ws = research.create_workspace(session, f"eval-{i}")
            project = research.create_project(session, ws.id, scenario.name)
            manuscript_id = scenario.build(session, project.id)
            found = {f["code"] for f in audits.audit_manuscript(session, manuscript_id)}
        finally:
            session.rollback()
            session.close()
        for code in scenario.expected_codes:
            bucket = per_code.setdefault(code, {"tp": 0, "fp": 0, "fn": 0})
            if code in found:
                bucket["tp"] += 1
            else:
                bucket["fn"] += 1
        for code in scenario.forbidden_codes & found:
            per_code.setdefault(code, {"tp": 0, "fp": 0, "fn": 0})["fp"] += 1
        rows.append(
            {"scenario": scenario.name,
             "expected": sorted(scenario.expected_codes),
             "found": sorted(found),
             "missed": sorted(scenario.expected_codes - found),
             "false_hits": sorted(scenario.forbidden_codes & found)}
        )
    metrics = {}
    for code, b in sorted(per_code.items()):
        precision = b["tp"] / (b["tp"] + b["fp"]) if (b["tp"] + b["fp"]) else None
        recall = b["tp"] / (b["tp"] + b["fn"]) if (b["tp"] + b["fn"]) else None
        metrics[code] = {**b, "precision": precision, "recall": recall}
    return {"scenarios": rows, "metrics": metrics}
