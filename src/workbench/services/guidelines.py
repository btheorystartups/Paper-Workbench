"""Reporting-guideline checklists (PRISMA 2020, CONSORT 2010, STROBE) attached to
manuscripts as trackable checklist objects.

Rules:
- Checklists are self-reported compliance records: every item starts "unaddressed" and a
  HUMAN marks it addressed / not_applicable (with a reason). Nothing is auto-completed.
- Findings from open items are ALWAYS advisory (info): a checklist documents reporting
  completeness, it never certifies methodology.
- Item texts are condensed from the published guidelines; `source` records which
  guideline and version a pack encodes so the author can consult the original.
"""

from sqlalchemy.orm import Session

from ..models import ResearchObject
from ..vocab import ObjectKind
from . import research

ITEM_STATUSES = ("unaddressed", "addressed", "not_applicable")

PACKS: dict[str, dict] = {
    "prisma-2020": {
        "name": "PRISMA 2020 (systematic reviews)",
        "source": "PRISMA 2020 statement, BMJ 2021;372:n71 (condensed item titles)",
        "items": [
            ("1", "Title identifies the report as a systematic review"),
            ("2", "Abstract per PRISMA 2020 abstract checklist"),
            ("3", "Rationale in the context of existing knowledge"),
            ("4", "Explicit objectives or questions"),
            ("5", "Eligibility criteria for inclusion/exclusion"),
            ("6", "Information sources and date last searched"),
            ("7", "Full search strategies for all sources"),
            ("8", "Selection process (who screened, how, independence)"),
            ("9", "Data collection process"),
            ("10", "Data items: outcomes and other variables"),
            ("11", "Risk-of-bias assessment method per study"),
            ("12", "Effect measures used"),
            ("13", "Synthesis methods (eligibility, preparation, model)"),
            ("14", "Reporting-bias assessment"),
            ("15", "Certainty assessment"),
            ("16", "Study selection results with flow diagram"),
            ("17", "Characteristics of included studies"),
            ("18", "Risk-of-bias results per study"),
            ("19", "Results of individual studies"),
            ("20", "Results of syntheses"),
            ("21", "Reporting biases results"),
            ("22", "Certainty of evidence results"),
            ("23", "Discussion: interpretation, limitations, implications"),
            ("24", "Registration and protocol (or state none)"),
            ("25", "Support: funding and role of funders"),
            ("26", "Competing interests"),
            ("27", "Availability of data, code and other materials"),
        ],
    },
    "consort-2010": {
        "name": "CONSORT 2010 (randomized trials)",
        "source": "CONSORT 2010 statement, BMJ 2010;340:c332 (condensed item titles)",
        "items": [
            ("1a", "Title identifies a randomised trial"),
            ("1b", "Structured abstract"),
            ("2", "Background, objectives and hypotheses"),
            ("3", "Trial design, allocation ratio, changes"),
            ("4", "Participants: eligibility, settings"),
            ("5", "Interventions with sufficient replication detail"),
            ("6", "Outcomes: pre-specified primary/secondary, changes"),
            ("7", "Sample size determination; interim analyses"),
            ("8", "Randomisation: sequence generation, type"),
            ("9", "Allocation concealment mechanism"),
            ("10", "Who generated/enrolled/assigned"),
            ("11", "Blinding: who, how, similarity of interventions"),
            ("12", "Statistical methods for primary/secondary and additional analyses"),
            ("13", "Participant flow with diagram; losses and exclusions"),
            ("14", "Recruitment dates and why the trial ended"),
            ("15", "Baseline table"),
            ("16", "Numbers analysed per group; ITT or not"),
            ("17", "Outcomes and estimation with effect size and precision"),
            ("18", "Ancillary analyses: pre-specified vs exploratory"),
            ("19", "Harms per group"),
            ("20", "Limitations: bias, imprecision, multiplicity"),
            ("21", "Generalisability"),
            ("22", "Interpretation balanced with benefits and harms"),
            ("23", "Registration number and registry"),
            ("24", "Where the protocol can be accessed"),
            ("25", "Funding and role of funders"),
        ],
    },
    "strobe": {
        "name": "STROBE (observational studies)",
        "source": "STROBE statement v4, PLoS Med 2007 (condensed item titles)",
        "items": [
            ("1", "Title/abstract indicate design; informative abstract"),
            ("2", "Background rationale"),
            ("3", "Specific objectives and hypotheses"),
            ("4", "Study design elements stated early"),
            ("5", "Setting, locations, relevant dates"),
            ("6", "Participants: eligibility, selection, matching"),
            ("7", "Variables: outcomes, exposures, confounders, effect modifiers"),
            ("8", "Data sources and measurement methods"),
            ("9", "Efforts to address bias"),
            ("10", "How the study size was arrived at"),
            ("11", "Handling of quantitative variables"),
            ("12", "Statistical methods incl. confounding, subgroups, missing data"),
            ("13", "Participant numbers at each stage; flow diagram"),
            ("14", "Descriptive data: characteristics, missingness, follow-up time"),
            ("15", "Outcome data over time / per group"),
            ("16", "Main results: unadjusted and adjusted estimates with precision"),
            ("17", "Other analyses: subgroups, interactions, sensitivity"),
            ("18", "Key results w.r.t. objectives"),
            ("19", "Limitations: bias, imprecision, direction/magnitude"),
            ("20", "Cautious overall interpretation"),
            ("21", "Generalisability"),
            ("22", "Funding and role of funders"),
        ],
    },
}


class GuidelineError(ValueError):
    pass


def list_packs() -> list[dict]:
    return [
        {"pack_id": pid, "name": p["name"], "source": p["source"],
         "item_count": len(p["items"])}
        for pid, p in PACKS.items()
    ]


def attach_checklist(session: Session, manuscript_id: str, pack_id: str) -> ResearchObject:
    manuscript = session.get(ResearchObject, manuscript_id)
    if manuscript is None or manuscript.kind != ObjectKind.MANUSCRIPT:
        raise research.IntegrityError("manuscript not found")
    pack = PACKS.get(pack_id)
    if pack is None:
        raise GuidelineError(f"unknown guideline pack '{pack_id}' "
                             f"(available: {sorted(PACKS)})")
    for existing in checklists_for(session, manuscript_id):
        if existing.body.get("pack_id") == pack_id:
            raise GuidelineError(f"checklist '{pack_id}' already attached")
    obj = research.create_object(
        session, manuscript.project_id, kind=ObjectKind.NOTE,
        title=f"Checklist {pack['name']}",
        body={
            "checklist": True,
            "pack_id": pack_id,
            "pack_name": pack["name"],
            "pack_source": pack["source"],
            "manuscript_id": manuscript_id,
            "items": [
                {"id": iid, "text": text, "status": "unaddressed",
                 "location": "", "note": ""}
                for iid, text in pack["items"]
            ],
        },
    )
    return obj


def checklists_for(session: Session, manuscript_id: str) -> list[ResearchObject]:
    from sqlalchemy import select

    manuscript = session.get(ResearchObject, manuscript_id)
    if manuscript is None:
        return []
    return [
        o for o in session.scalars(
            select(ResearchObject).where(
                ResearchObject.project_id == manuscript.project_id,
                ResearchObject.kind == ObjectKind.NOTE,
                ResearchObject.deleted_at.is_(None),
            )
        )
        if o.body.get("checklist") and o.body.get("manuscript_id") == manuscript_id
    ]


def update_item(
    session: Session, checklist_id: str, item_id: str, *,
    status: str, location: str = "", note: str = "",
) -> ResearchObject:
    obj = session.get(ResearchObject, checklist_id)
    if obj is None or not obj.body.get("checklist"):
        raise GuidelineError("checklist not found")
    if status not in ITEM_STATUSES:
        raise GuidelineError(f"status must be one of {ITEM_STATUSES}")
    if status == "not_applicable" and not note.strip():
        raise GuidelineError("not_applicable requires a note explaining why")
    body = dict(obj.body)
    items = [dict(i) for i in body["items"]]
    for item in items:
        if item["id"] == item_id:
            item["status"] = status
            item["location"] = location
            item["note"] = note
            break
    else:
        raise GuidelineError(f"item '{item_id}' not in checklist")
    body["items"] = items
    obj.body = body
    return obj


def audit_checklists(session: Session, manuscript_id: str) -> list[dict]:
    """Advisory (info) findings for open checklist items — reporting completeness is
    documented, never certified."""
    findings: list[dict] = []
    for cl in checklists_for(session, manuscript_id):
        open_items = [i for i in cl.body["items"] if i["status"] == "unaddressed"]
        if open_items:
            findings.append(
                {"severity": "info", "code": "checklist-items-open",
                 "message": f"{cl.body['pack_name']}: {len(open_items)} of "
                            f"{len(cl.body['items'])} items unaddressed "
                            f"(e.g. {open_items[0]['id']}: {open_items[0]['text'][:60]})",
                 "object_id": cl.id}
            )
    return findings
