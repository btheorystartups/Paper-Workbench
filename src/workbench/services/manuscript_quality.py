"""Manuscript specialist evidence, linked to the existing graph and revision review."""

import hashlib
import json

from pydantic import ValidationError
from sqlalchemy import select

from .. import storage
from ..manuscript_length import measure
from ..models import Claim, ClaimEvidence, ResearchAgent, ResearchObject, ResearchTask, stable_hash, utcnow
from ..research_contract import ADVERSARIAL_CRITERIA, SPECIALIST_ROLES, ManuscriptDraft, SpecialistReport
from . import authoring, evidence_basis, research, revision_review
from .bibliography import bibliography_markers
from .evaluation import Denied
from .evidence_availability import _ambiguous_flags, _availability_rows, evidence_inventory

POLICY = "manuscript-quality-v2-adversarial"


class ReportValidationError(ValueError):
    """Controlled diagnostics for a rejected report; never an accepted assessment."""

    def __init__(self, issues):
        self.issues = issues
        super().__init__("; ".join(issue["message"] for issue in issues))


class DraftValidationError(ReportValidationError):
    """Author corrections detected before any manuscript graph mutation."""


def campaign_for(session, manuscript_id):
    return next(
        (
            o
            for o in session.scalars(
                select(ResearchObject).where(
                    ResearchObject.kind == "note", ResearchObject.deleted_at.is_(None)
                )
            )
            if o.body.get("quality_assessment") and o.body.get("manuscript_id") == manuscript_id
        ),
        None,
    )


def create_campaign(session, task):
    manuscript = authoring.create_manuscript(session, task.project_id, title="Unreviewed manuscript draft")
    manuscript.ai_suggested, manuscript.accepted_by_user = True, False
    manuscript.body = {
        **manuscript.body,
        "quality_policy": POLICY,
        "quality_task_id": task.id,
        "source_ids": [s["source_id"] for s in task.sources if s.get("source_id")],
    }
    task.contract = {**task.contract, "quality_manuscript_id": manuscript.id}
    campaign = research.create_object(
        session,
        task.project_id,
        kind="note",
        title="Specialist review campaign",
        body={
            "quality_assessment": True,
            "manuscript_id": manuscript.id,
            "quality_task_id": task.id,
            "policy": POLICY,
            "drafts": [],
            "rounds": [],
            "reports": [],
            "packets": [],
            "search_receipts": [],
            "verification_receipts": [],
            "status": "pending",
        },
        ai_suggested=True,
    )
    session.commit()
    return manuscript, campaign


def update_campaign(campaign, **values):
    campaign.body = {**campaign.body, **values}


def author_model_threads(agent):
    if not agent:
        return set()
    identities = [p.get("codex_thread_id") for k, p in agent.provenance.items()
                  if k.endswith("_model") and isinstance(p, dict)]
    identities += [row.get("model_thread_id") for row in agent.provenance.get("draft_attempts", [])]
    identities += [row.get("codex_thread_id") for row in agent.provenance.get("codex_streams", [])]
    return {identity for identity in identities if identity}


def draft_text(candidate):
    return (
        "# "
        + candidate["title"]
        + "\n\n"
        + "\n\n".join("## " + s["heading"] + "\n\n" + s["text"] for s in candidate["sections"])
    )


def task_requirements(task):
    return {"version": 2, **{key: task.contract.get(key) for key in (
        "question", "paper_type", "success_criteria", "manuscript_length",
        "verification_routines", "compute_run_ids", "literature_queries", "allow_public_search")}}


def source_manifest(task):
    return [{k: v for k, v in source.items()
             if k not in {"text", "artifact", "extracted_artifact"}}
            for source in task.sources if source.get("source_id")]


def requirements_match(recorded, task):
    expected = task_requirements(task)
    if recorded.get("version") == 2:
        return recorded == expected
    # Pre-v2 packets bound only these two fields. Retain their historical scope.
    return recorded == {key: expected[key] for key in ("success_criteria", "manuscript_length")}


def length_check(candidate, bounds):
    """Count section text only, including equations/references; never infer prose bounds."""
    measured = measure(candidate["sections"], bounds)
    # Preserve the existing packet/readiness binding shape. Tool receipts carry
    # section IDs and hashes separately from this historical length assertion.
    return {key: measured[key] for key in ("counting_policy", "word_count", "bounds", "status")}


def validate_draft(task, campaign, raw, *, expected_response_ids=None):
    try:
        draft = ManuscriptDraft.model_validate(raw).model_dump()
    except ValidationError as exc:
        raise DraftValidationError([
            {"code": "draft_schema", "path": "/" + "/".join(map(str, e["loc"])),
             "message": "Draft field does not match its schema: " + e["type"]}
            for e in exc.errors(include_input=False, include_url=False)
        ]) from None
    sources = {s["source_id"] for s in task.sources if s.get("source_id")}
    checks = {r["id"] for r in campaign.body["verification_receipts"]}
    issues = []
    measured = length_check(draft, task.contract.get("manuscript_length"))
    if measured["status"] == "out_of_bounds":
        issues.append({"code": "manuscript_length", "path": "/sections",
            "message": f"Draft contains {measured['word_count']} words; required inclusive range "
            f"is {measured['bounds']['min_words']}-{measured['bounds']['max_words']}. "
            "Count whitespace-delimited tokens in section text, including equations and references; "
            "exclude title, headings, claim metadata and response metadata.", **measured})
    if expected_response_ids is not None:
        expected = set(expected_response_ids)
        returned = {r["comment_id"] for r in draft["responses"]}
        if returned != expected:
            issues.append({"code": "responses", "path": "/responses",
                "message": "Return exactly one response per supplied reviewer comment ID, "
                           "and no responses for controller validation issue codes. "
                           "When expected_response_ids is empty, return responses=[].",
                "expected_response_ids": sorted(expected),
                "missing_response_ids": sorted(expected - returned),
                "unexpected_response_ids": sorted(returned - expected)})
    if task.contract["paper_type"] == "expository" and draft["novelty_claim"]:
        issues.append({"code": "novelty", "path": "/novelty_claim",
                       "message": "an expository task cannot introduce a novelty claim"})
    for index, claim in enumerate(draft["claims"]):
        for field, allowed in (("source_ids", sources), ("verification_ids", checks)):
            unknown = set(claim[field]) - allowed
            if unknown:
                issues.append({"code": "draft_evidence", "path": f"/claims/{index}/{field}",
                    "message": f"Claim {claim['id']} references evidence outside its frozen task: "
                    f"{field} {sorted(unknown)}. Allowed {field}: {sorted(allowed)}. "
                    "Search receipts describe discovery, not executed verification; cite their "
                    "scope in prose, not verification_ids."})
    previous = campaign.body["drafts"][-1]["candidate"] if campaign.body["drafts"] else None
    if previous and (
        not {s["id"] for s in previous["sections"]} <= {s["id"] for s in draft["sections"]}
        or not {c["id"] for c in previous["claims"]} <= {c["id"] for c in draft["claims"]}
    ):
        issues.append({"code": "revision_ids", "path": "/",
                       "message": "revision must preserve IDs, including explicit retractions"})
    if issues:
        raise DraftValidationError(issues)
    return draft


def apply_draft(session, task, manuscript, campaign, raw, author_id, *, expected_response_ids=None):
    draft = validate_draft(task, campaign, raw, expected_response_ids=expected_response_ids)
    claim_map = dict(manuscript.body.get("quality_claim_map", {}))
    excerpts = dict(manuscript.body.get("quality_source_excerpt_map", {}))
    for source in task.sources:
        sid = source.get("source_id")
        if (sid and sid not in excerpts and source.get("text")
                and source["access"] != "metadata_only"):
            excerpt = research.capture_excerpt(session, sid, text=source["text"], locator=(
                f"Frozen task {task.id}, version {source['version']}; complete supplied excerpt. "
                "Provisional citation; specialist passages recorded separately."))
            excerpts[sid] = excerpt.id
    for item in draft["claims"]:
        wanted = {excerpts[sid] for sid in item["source_ids"] if sid in excerpts}
        if item["id"] in claim_map:
            claim = session.get(Claim, claim_map[item["id"]])
            claim.text = item["statement"]
            links = research.claim_evidence(session, claim.id)
            for link in links:
                if link.excerpt_id and link.excerpt_id not in wanted:
                    link.deleted_at = utcnow()
            existing = {link.excerpt_id for link in links if not link.deleted_at}
            for eid in wanted - existing:
                session.add(ClaimEvidence(claim_id=claim.id, excerpt_id=eid, entailment="asserted"))
        else:
            claim = research.create_claim(
                session,
                task.project_id,
                text=item["statement"],
                support="verification_required",
                excerpt_ids=sorted(wanted),
                notes="Unreviewed candidate; specialist reports linked.",
            )
            claim_map[item["id"]] = claim.id
    section_map = dict(manuscript.body.get("quality_section_map", {}))
    for item in draft["sections"]:
        ids = [claim_map[i] for i in item["claim_ids"]]
        if item["id"] in section_map:
            section = authoring.update_section(
                session, section_map[item["id"]], text=item["text"], claim_ids=ids
            )
            section.title = item["heading"]
        else:
            section = authoring.add_section(
                session, manuscript.id, heading=item["heading"], text=item["text"], claim_ids=ids
            )
            section_map[item["id"]] = section.id
        section.ai_suggested, section.accepted_by_user = True, False
    manuscript.title = draft["title"]
    manuscript.body = {
        **manuscript.body,
        "quality_claim_map": claim_map,
        "quality_source_excerpt_map": excerpts,
        "quality_section_map": section_map,
        "quality_claims": draft["claims"],
        "novelty_claim": draft["novelty_claim"],
        "limitations": draft["limitations"],
    }
    manuscript.ai_suggested, manuscript.accepted_by_user = True, False
    session.flush()
    candidate_hash = revision_review.candidate_hash(session, manuscript.id)
    update_campaign(
        campaign,
        drafts=[
            *campaign.body["drafts"],
            {"candidate": draft, "candidate_sha256": candidate_hash, "author_id": author_id},
        ],
        status="draft_produced",
    )
    session.commit()
    return draft, candidate_hash


def packet_for(task, campaign, candidate_hash, role, prior_comments):
    candidate = campaign.body["drafts"][-1]["candidate"]
    packet = {
        "role": role,
        "candidate_sha256": candidate_hash,
        "candidate": candidate,
        "task_specification": task.contract.get("instructions", ""),
        "task_requirements": task_requirements(task),
        "length_check": length_check(candidate, task.contract.get("manuscript_length")),
        "admitted_original_evidence": {s["source_id"]: s["text"] for s in task.sources if s.get("source_id")},
        "source_manifest": source_manifest(task),
        "search_receipts": campaign.body["search_receipts"],
        "verification_receipts": campaign.body["verification_receipts"],
        "prior_comments": prior_comments,
        "earlier_packet_manifests": campaign.body["packets"],
    }
    packet["evidence_artifacts"] = evidence_inventory(packet)
    packet["packet_sha256"] = stable_hash(packet)
    return packet


def validate_report(raw, packet):
    if packet.get("packet_sha256") != stable_hash({k: v for k, v in packet.items() if k != "packet_sha256"}):
        raise ValueError("specialist packet bytes changed")
    try:
        report = SpecialistReport.model_validate(raw).model_dump()
    except ValidationError as exc:
        raise ReportValidationError([
            {"code": "report_schema", "path": "/" + "/".join(map(str, e["loc"])),
             "message": "Report field does not match its declared schema: " + e["type"]}
            for e in exc.errors(include_input=False, include_url=False)
        ]) from None
    if any(report[k] != packet[k] for k in ("role", "candidate_sha256", "packet_sha256")):
        raise ValueError("specialist report is for another role, candidate or packet")
    claims = {c["id"]: c for c in packet["candidate"]["claims"]}
    sections = {s["id"] for s in packet["candidate"]["sections"]}
    issues = []

    def invalid(code, path, message):
        issues.append({"code": code, "path": path, "message": message})

    if (
        len(report["assessments"]) != len(claims)
        or {a["claim_id"] for a in report["assessments"]} != set(claims)
        or len(report["covered_section_ids"]) != len(sections)
        or set(report["covered_section_ids"]) != sections
    ):
        invalid("coverage", "/", "specialist coverage must include every claim and complete section")
    for field in ("objections", "resolutions"):
        key = "id" if field == "objections" else "comment_id"
        if len({r[key] for r in report[field]}) != len(report[field]):
            invalid("duplicate_record", "/" + field, "duplicate specialist record")
    expected = {c["id"] for c in packet["prior_comments"]}
    if {r["comment_id"] for r in report["resolutions"]} != expected:
        invalid("resolutions", "/resolutions", "every prior objection requires an independent disposition")
    if any(not set(o["claim_ids"]) <= set(claims) for o in report["objections"]):
        invalid("objection_claim", "/objections", "objection references unknown claim")
    assertions, corrections = [], []
    for field, target in (("evidence_assertions", assertions), ("historical_corrections", corrections)):
        for index, row in enumerate(report[field]):
            try:
                a, c = _availability_rows({field: [row]}, packet)
                target.extend(a if field == "evidence_assertions" else c)
            except Denied as exc:
                invalid("evidence_availability", f"/{field}/{index}", str(exc))
    flags = _ambiguous_flags(
        {"report": report["summary"] + "\n" + report["contribution_comparison"]},
        role=report["role"],
        corrections=corrections,
    )
    blockers = list(report["coverage_flags"])
    if report["role"] == "adversarial":
        checks = report["adversarial_checks"]
        if len(checks) != len(ADVERSARIAL_CRITERIA) or {c["criterion"] for c in checks} != set(
            ADVERSARIAL_CRITERIA
        ):
            invalid(
                "adversarial_coverage",
                "/adversarial_checks",
                "every adversarial criterion requires one challenge and outcome",
            )
        for index, check in enumerate(checks):
            if not set(check["claim_ids"]) <= set(claims):
                invalid(
                    "adversarial_claim", f"/adversarial_checks/{index}", "challenge references unknown claim"
                )
            if check["outcome"] != "passed_within_scope":
                blockers.append("adversarial " + check["criterion"] + ": " + check["rationale"])
                objection = next((o for o in report["objections"] if o["id"] == check["objection_id"]), None)
                path = f"/adversarial_checks/{index}"
                if not objection or objection["severity"] != "blocking":
                    invalid(
                        "adversarial_objection",
                        path + "/objection_id",
                        "Unresolved "
                        + check["criterion"]
                        + " must bind an existing blocking objection with an acceptance criterion.",
                    )
                else:
                    uncovered = set(check["claim_ids"]) - set(objection["claim_ids"])
                    if uncovered:
                        invalid("adversarial_objection", path + "/claim_ids",
                                "Unresolved " + check["criterion"] + " binds " + objection["id"]
                                + "; that objection does not cover " + ", ".join(sorted(uncovered))
                                + ". List only claims still challenged, not every claim examined; "
                                "or extend the objection's claim IDs only where its rationale applies.")
            elif check["objection_id"] is not None:
                invalid(
                    "adversarial_objection",
                    f"/adversarial_checks/{index}/objection_id",
                    "a passed challenge cannot retain an unresolved objection binding",
                )
    if any(s.get("status") in {"failed", "not_run"} for s in packet["search_receipts"]):
        blockers.append("requested literature search did not complete")
    sources = {s["source_id"]: s for s in packet["source_manifest"]}
    checks = {c["id"]: c for c in packet["verification_receipts"]}

    def normalize(text):
        return " ".join(text.split())

    for index, item in enumerate(report["assessments"]):
        if item["claim_id"] not in claims:
            continue  # The complete-coverage check already rejects unknown IDs.
        path = f"/assessments/{index}"
        claim = claims[item["claim_id"]]
        if item["status"] in {"unresolved", "contradicted"}:
            blockers.append(item["claim_id"] + ": " + item["rationale"])
        if item["status"] == "not_applicable" and not (
            report["role"] == "proof_method" and claim["kind"] in {"background", "contribution"}
        ):
            blockers.append("unjustified not-applicable assessment: " + item["claim_id"])
        for passage_index, passage in enumerate(item["passages"]):
            passage_path = f"{path}/passages/{passage_index}"
            sid = passage["source_id"]
            counterevidence = item["status"] in {"unresolved", "contradicted"}
            if sid not in sources or (sid not in claim["source_ids"] and not counterevidence):
                invalid("passage_source", passage_path, "passage references a source outside this claim")
                continue
            if normalize(passage["quotation"]) not in normalize(packet["admitted_original_evidence"][sid]):
                invalid("quotation", passage_path + "/quotation",
                        "quotation is absent from the frozen source")
            if sources[sid]["access"] in {"metadata_only", "abstract_only"}:
                blockers.append("source content unavailable for claim verification: " + sid)
        if (
            report["role"] in {"source_citation", "adversarial"}
            and item["status"] == "supported_within_scope"
        ):
            missing = set(claim["source_ids"]) - {p["source_id"] for p in item["passages"]}
            if missing:
                blockers.append("missing passage support: " + item["claim_id"]
                                + " (source_ids: " + ", ".join(sorted(missing)) + ")")
        if not set(item["verification_ids"]) <= set(checks):
            invalid("verification_receipt", path + "/verification_ids",
                    "specialist invented a verification receipt")
        if report["role"] in {"proof_method", "adversarial"} and claim["kind"] == "finite_check":
            if not claim["verification_ids"] or not set(claim["verification_ids"]) <= set(
                item["verification_ids"]
            ):
                blockers.append("finite check has no executed receipt: " + item["claim_id"])
        if any(checks[i].get("outcome") != "passed_within_scope"
               for i in item["verification_ids"] if i in checks):
            blockers.append("required verification did not pass: " + item["claim_id"])
    if any(s.get("context_truncated") for s in sources.values()):
        blockers.append("source coverage was truncated")
    if packet["candidate"]["novelty_claim"]:
        searches = packet["search_receipts"]
        if not searches or any(s.get("status") != "completed" or not s.get("results") for s in searches):
            blockers.append("novelty claim lacks completed nonempty literature searches")
    blockers += [o["objection"] for o in report["objections"] if o["severity"] == "blocking"]
    if issues:
        raise ReportValidationError(issues)
    return (
        report,
        list(dict.fromkeys(blockers)),
        {"evidence_assertions": assertions, "historical_corrections": corrections, "review_flags": flags},
    )


def assessment(session, manuscript_id):
    manuscript = session.get(ResearchObject, manuscript_id)
    if not manuscript or manuscript.deleted_at or manuscript.kind != "manuscript":
        raise research.IntegrityError("manuscript not found")
    campaign = campaign_for(session, manuscript_id)
    required = bool(manuscript and manuscript.body.get("quality_policy")) or bool(campaign)
    if not required:
        required = any(
            t.contract.get("quality_manuscript_id") == manuscript_id
            for t in session.scalars(
                select(ResearchTask).where(ResearchTask.project_id == manuscript.project_id)
            )
        )
    if not required:
        return {"required": False, "agent_checks_complete": False, "blockers": []}
    blockers = []
    release_flags = []
    if not campaign or not campaign.body.get("drafts"):
        return {
            "required": True,
            "agent_checks_complete": False,
            "blockers": ["required specialist campaign or draft is missing"],
        }
    task = session.get(ResearchTask, campaign.body["quality_task_id"])
    current = revision_review.candidate_hash(session, manuscript_id)
    sections = authoring.manuscript_sections(session, manuscript_id)
    measured = length_check({"sections": [{"text": section.body.get("text", "")} for section in sections]},
                            task.contract.get("manuscript_length") if task else None)
    if measured["status"] == "out_of_bounds":
        blockers.append("manuscript length is outside required bounds")
    latest = campaign.body["reports"][-len(SPECIALIST_ROLES):]
    receipts = [*campaign.body["search_receipts"], *campaign.body["verification_receipts"]]
    try:
        frozen = [json.loads(storage.read_bytes(ref)) for ref in manuscript.body.get("quality_evidence", [])]
        if frozen != receipts:
            blockers.append("execution or search receipts changed")
        for receipt in campaign.body["verification_receipts"]:
            reproduction = receipt.get("reproduction")
            if receipt.get("executed_by") != "workbench_allowlisted_routine":
                continue
            if not reproduction:
                blockers.append("reviewed verifier reproduction evidence unavailable")
                continue
            implementation = storage.read_bytes(reproduction["implementation_artifact"])
            if (hashlib.sha256(implementation).hexdigest() != receipt["implementation_sha256"]
                    or implementation.decode("utf-8") != reproduction["implementation_text"]):
                blockers.append("reviewed verifier implementation changed")
    except (OSError, ValueError, KeyError, storage.ArtifactStorageError):
        blockers.append("execution or search receipts unavailable")
    author_ids = {d["author_id"] for d in campaign.body["drafts"]}
    authors = [session.get(ResearchAgent, aid) for aid in author_ids]
    author_threads = set().union(*(author_model_threads(a) for a in authors))
    roles, threads = [], []
    for record in latest:
        agent = session.get(ResearchAgent, record["agent_id"])
        if (
            not agent
            or agent.deleted_at
            or not task
            or agent.task_id != task.id
            or agent.assignment.get("specialist_role") != record["role"]
            or stable_hash(agent.report) != record["report_sha256"]
        ):
            blockers.append("specialist identity or original report changed")
            continue
        roles.append(record["role"])
        identity = agent.provenance.get("specialist_report_model", {}).get("codex_thread_id", agent.id)
        threads.append(identity)
        if record["candidate_sha256"] != current:
            blockers.append("specialist review is stale")
        if agent.id in author_ids or identity in author_threads or agent.parent_id not in author_ids:
            blockers.append("author cannot verify their own manuscript")
        try:
            packet = record["packet"]
            if (
                packet["candidate"] != campaign.body["drafts"][-1]["candidate"]
                or ("task_requirements" in packet
                    and not requirements_match(packet["task_requirements"], task))
                or (task.contract.get("manuscript_length") and "task_requirements" not in packet)
                or ("length_check" in packet and packet["length_check"] != measured)
                or packet.get("task_specification") != task.contract.get("instructions", "")
                or packet["source_manifest"] != source_manifest(task)
                or packet["verification_receipts"] != campaign.body["verification_receipts"]
                or packet["search_receipts"] != campaign.body["search_receipts"]
                or packet["admitted_original_evidence"]
                != {s["source_id"]: s["text"] for s in task.sources if s.get("source_id")}
                or agent.assignment.get("candidate_sha256") != current
                or agent.assignment.get("packet_sha256") != packet["packet_sha256"]
            ):
                blockers.append("specialist assignment or evidence changed")
            _report, issues, flags = validate_report(agent.report, packet)
            blockers.extend(issues)
            release_flags.extend({**flag, "agent_id": agent.id, "packet_sha256": packet["packet_sha256"]}
                                 for flag in flags["review_flags"] if not flag.get("resolved"))
            attempts = agent.provenance.get("report_attempts", [])
            if attempts:
                original = attempts[-1]
                if (stable_hash(original["report"]) != original["report_sha256"]
                        or original["packet_sha256"] != packet["packet_sha256"]
                        or SpecialistReport.model_validate(original["report"]).model_dump() != agent.report):
                    blockers.append("accepted specialist report differs from its original return")
        except (ValueError, KeyError, TypeError):
            blockers.append("specialist evidence or coverage is invalid")
    if sorted(roles) != sorted(SPECIALIST_ROLES) or len(set(threads)) != len(SPECIALIST_ROLES):
        blockers.append("four distinct specialist reviewers, including adversarial review, are required")
    if task is not None and task.deleted_at:
        blockers.append("required manuscript production task is unavailable")
    if task is None or task.contract["executor"] == "offline":
        blockers.append("simulated research cannot pass production review")
    if campaign.body.get("status") != "agent_checks_complete":
        blockers.append("specialist campaign has not completed its checks")
    for round_id in campaign.body["rounds"]:
        review = session.get(ResearchObject, round_id)
        if (
            not review
            or review.deleted_at
            or any(
                d not in {"resolved", "justified_rejection"}
                for d in revision_review.dispositions(session, review).values()
            )
        ):
            blockers.append("unresolved or stale specialist objection")
    basis = evidence_basis.collect(session, manuscript_id, scientific_only=True)
    blockers.extend(basis["problems"])
    for section in sections:
        if bibliography_markers(
            section.body.get("text", ""),
            bibliography_context=section.title.casefold() in {"references", "bibliography"},
        ):
            blockers.append("unresolved bibliography markers")
    review_blockers = list(dict.fromkeys(blockers))
    if (task is None or task.state != "completed"
            or not task.ledger.get("parent_integration_received")
            or not task.ledger.get("child_handoff_received")):
        blockers.append("manuscript production task has not completed its final handoff")
    return {
        "required": True,
        "agent_checks_complete": not review_blockers,
        "draft_produced": bool(campaign.body["drafts"]),
        "agent_review_grants_publication_approval": False,
        "manuscript_id": manuscript_id,
        "campaign_id": campaign.id,
        "candidate_sha256": current,
        "length_check": measured,
        "task_requirements": task_requirements(task) if task else None,
        "release_review_flags": release_flags,
        "blockers": list(dict.fromkeys(blockers)),
    }


def campaign_export(session, task):
    from .manuscript_readiness import report

    mid = task.contract.get("quality_manuscript_id")
    campaign = campaign_for(session, mid) if mid else None
    return {
        "campaign": campaign.body if campaign else None,
        "assessment": assessment(session, mid) if mid else None,
        "readiness": report(session, mid) if mid else None,
        "notice": "Agent checks do not grant human acceptance or publication approval.",
    }


def report_text(report):
    return json.dumps(report, indent=2, ensure_ascii=False)
