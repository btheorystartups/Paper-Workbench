"""Authoring core (P4): paper candidates, argument-planned manuscripts, sections whose
substantive claims are explicit references into the claim ledger.

Rules:
- A section's `claim_ids` must resolve to Claims in the same project (checked at write).
- Free prose is allowed, but claims are the only citable substance; export and audits
  work off claim references, so unreferenced assertions surface as findings, not silently.
- Paper candidates are proposals (may be AI-suggested); a manuscript is created from an
  approved candidate or from scratch by the user.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Claim, Edge, ResearchObject
from ..vocab import ObjectKind, Relation
from . import research

PAPER_TYPES = {
    "original_empirical", "mathematical_theoretical", "methodological", "computational",
    "applied", "proof_of_concept", "short_communication", "technical_note", "expository",
    "review_survey", "comparative", "replication_validation", "software", "data_resource",
    "working_paper_preprint", "custom",
}

STRUCTURES = {
    "imrad", "definition_theorem_proof_example", "problem_framework_analysis_implications",
    "historical_synthesis", "algorithm_correctness_complexity_experiments",
    "application_method_case_study_validation", "custom",
}


def create_paper_candidate(
    session: Session, project_id: str, *,
    title: str, paper_type: str, central_question: str, thesis: str,
    audience: str = "", structure: str = "imrad",
    included_object_ids: list[str] | None = None,
    excluded: list[dict] | None = None,
    novelty_caveat: str = "", risks: str = "",
    missing_work: list[str] | None = None,
    ai_suggested: bool = False,
) -> ResearchObject:
    if paper_type not in PAPER_TYPES:
        raise research.IntegrityError(f"paper_type must be one of {sorted(PAPER_TYPES)}")
    if structure not in STRUCTURES:
        raise research.IntegrityError(f"structure must be one of {sorted(STRUCTURES)}")
    included = included_object_ids or []
    for oid in included:
        obj = session.get(ResearchObject, oid)
        if obj is None or obj.project_id != project_id:
            raise research.IntegrityError(f"included object {oid} not in project")
    return research.create_object(
        session, project_id, kind=ObjectKind.PAPER_CANDIDATE, title=title,
        ai_suggested=ai_suggested,
        body={
            "paper_type": paper_type,
            "structure": structure,
            "central_question": central_question,
            "thesis": thesis,
            "audience": audience,
            "included_object_ids": included,
            "excluded": excluded or [],  # [{"object_id"|"topic": ..., "reason": ...}]
            "novelty_caveat": novelty_caveat,
            "risks": risks,
            "missing_work": missing_work or [],
            "frozen": False,
        },
    )


def create_manuscript(
    session: Session, project_id: str, *, title: str,
    from_candidate_id: str | None = None,
) -> ResearchObject:
    body: dict = {"section_order": [], "status": "draft"}
    if from_candidate_id:
        candidate = session.get(ResearchObject, from_candidate_id)
        if (
            candidate is None
            or candidate.project_id != project_id
            or candidate.kind != ObjectKind.PAPER_CANDIDATE
        ):
            raise research.IntegrityError("candidate not found in project")
        body["from_candidate_id"] = from_candidate_id
        body["structure"] = candidate.body.get("structure", "custom")
    manuscript = research.create_object(
        session, project_id, kind=ObjectKind.MANUSCRIPT, title=title, body=body
    )
    if from_candidate_id:
        research.link_objects(
            session, project_id, manuscript.id, from_candidate_id, Relation.DERIVES_FROM
        )
    return manuscript


def add_section(
    session: Session, manuscript_id: str, *,
    heading: str, purpose: str = "", text: str = "",
    claim_ids: list[str] | None = None, word_budget: int | None = None,
    position: int | None = None,
) -> ResearchObject:
    manuscript = session.get(ResearchObject, manuscript_id)
    if manuscript is None or manuscript.kind != ObjectKind.MANUSCRIPT:
        raise research.IntegrityError("manuscript not found")
    claim_ids = claim_ids or []
    for cid in claim_ids:
        claim = session.get(Claim, cid)
        if claim is None or claim.project_id != manuscript.project_id:
            raise research.IntegrityError(f"claim {cid} not in project")
    section = research.create_object(
        session, manuscript.project_id, kind=ObjectKind.SECTION, title=heading,
        body={
            "purpose": purpose,
            "text": text,
            "claim_ids": claim_ids,
            "word_budget": word_budget,
        },
    )
    research.link_objects(
        session, manuscript.project_id, section.id, manuscript.id, Relation.PART_OF
    )
    order = list(manuscript.body.get("section_order", []))
    if position is None or position >= len(order):
        order.append(section.id)
    else:
        order.insert(max(position, 0), section.id)
    manuscript.body = {**manuscript.body, "section_order": order}
    return section


def update_section(
    session: Session, section_id: str, *,
    text: str | None = None, purpose: str | None = None,
    claim_ids: list[str] | None = None,
) -> ResearchObject:
    section = session.get(ResearchObject, section_id)
    if section is None or section.kind != ObjectKind.SECTION:
        raise research.IntegrityError("section not found")
    body = dict(section.body)
    if claim_ids is not None:
        for cid in claim_ids:
            claim = session.get(Claim, cid)
            if claim is None or claim.project_id != section.project_id:
                raise research.IntegrityError(f"claim {cid} not in project")
        body["claim_ids"] = claim_ids
    if text is not None:
        body["text"] = text
    if purpose is not None:
        body["purpose"] = purpose
    section.body = body
    return section


def manuscript_sections(session: Session, manuscript_id: str) -> list[ResearchObject]:
    manuscript = session.get(ResearchObject, manuscript_id)
    if manuscript is None or manuscript.kind != ObjectKind.MANUSCRIPT:
        raise research.IntegrityError("manuscript not found")
    order = manuscript.body.get("section_order", [])
    sections = {
        s.id: s
        for s in session.scalars(
            select(ResearchObject).where(
                ResearchObject.kind == ObjectKind.SECTION,
                ResearchObject.project_id == manuscript.project_id,
                ResearchObject.deleted_at.is_(None),
            )
        )
        if any(
            e.dst_id == manuscript_id
            for e in session.scalars(select(Edge).where(Edge.src_id == s.id))
        )
    }
    ordered = [sections[sid] for sid in order if sid in sections]
    ordered += [s for s in sections.values() if s.id not in set(order)]
    return ordered
