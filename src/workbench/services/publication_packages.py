"""Review-gated, local-only publication package assembly.

Packages collect a human-reviewed cover letter, controlled declarations, manuscript
exports, venue findings, and response-to-reviewers material into a checksummed ZIP. They
never contact a journal or imply submission. Approval is bound to a complete snapshot, so
later manuscript, authorship, declaration, venue, or submission changes make it stale.
"""

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import get_settings
from ..models import PublicationPackage, ResearchObject, Submission, VenueProfile, stable_hash, utcnow
from ..vocab import ObjectKind
from . import audits, authorship, export_service, research, venues

PACKAGE_STATES = {"draft", "review_ready", "approved", "rejected", "superseded"}
COVER_LETTER_STATES = {"missing", "draft", "confirmed"}
DECLARATION_STATES = {"missing", "draft", "confirmed", "not_applicable"}
EXPORT_FORMATS = {"md", "tex", "html", "docx", "bib", "pdf", "jats"}
DEFAULT_FORMATS = ["md", "tex", "html", "docx", "bib", "pdf", "jats"]
DECLARATION_TYPES = {
    "competing_interests": "Competing interests",
    "funding": "Funding",
    "data_availability": "Data availability",
    "code_availability": "Code availability",
    "ethics": "Ethics approval and consent",
    "ai_assistance": "AI assistance disclosure",
    "originality": "Originality and exclusive-submission statement",
}


class PackageError(ValueError):
    pass


def _submission(session: Session, submission_id: str) -> Submission:
    submission = session.get(Submission, submission_id)
    if submission is None or submission.deleted_at is not None:
        raise PackageError("submission not found")
    return submission


def _package(session: Session, package_id: str) -> PublicationPackage:
    package = session.get(PublicationPackage, package_id)
    if package is None or package.deleted_at is not None:
        raise PackageError("publication package not found")
    return package


def _record(
    session: Session,
    package: PublicationPackage,
    action: str,
    detail: dict,
) -> None:
    project = research._project(session, package.project_id)
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor="user",
        action=action,
        object_type="publication_package",
        object_id=package.id,
        detail=detail,
    )


def _event(previous: str | None, current: str, note: str) -> dict:
    return {"at": utcnow().isoformat(), "from": previous, "to": current, "note": note}


def _normalise_formats(formats: list[str] | None) -> list[str]:
    values = list(dict.fromkeys(formats or DEFAULT_FORMATS))
    unknown = set(values) - EXPORT_FORMATS
    if unknown:
        raise PackageError(f"formats must be drawn from {sorted(EXPORT_FORMATS)}")
    if not values:
        raise PackageError("publication package requires at least one manuscript format")
    return values


def create_package(
    session: Session,
    submission_id: str,
    *,
    included_formats: list[str] | None = None,
) -> PublicationPackage:
    submission = _submission(session, submission_id)
    manuscript = session.get(ResearchObject, submission.manuscript_id)
    if manuscript is None or manuscript.kind != ObjectKind.MANUSCRIPT:
        raise PackageError("submission manuscript not found")
    latest = session.scalar(
        select(func.max(PublicationPackage.version)).where(
            PublicationPackage.submission_id == submission_id
        )
    )
    version = int(latest or 0) + 1
    declarations = [
        {
            "kind": kind,
            "label": label,
            "state": "missing",
            "text": "",
            "review_note": "",
            "updated_at": None,
        }
        for kind, label in DECLARATION_TYPES.items()
    ]
    package = PublicationPackage(
        project_id=submission.project_id,
        submission_id=submission.id,
        manuscript_id=submission.manuscript_id,
        version=version,
        state="draft",
        included_formats=_normalise_formats(included_formats),
        declarations=declarations,
        history=[_event(None, "draft", "package created; no external submission")],
    )
    session.add(package)
    session.flush()
    _record(
        session,
        package,
        "create_publication_package",
        {"submission_id": submission.id, "version": version, "formats": package.included_formats},
    )
    return package


def get_package(session: Session, package_id: str) -> PublicationPackage:
    return _package(session, package_id)


def list_packages(
    session: Session, *, project_id: str | None = None, submission_id: str | None = None
) -> list[PublicationPackage]:
    if (project_id is None) == (submission_id is None):
        raise PackageError("provide exactly one of project_id or submission_id")
    query = select(PublicationPackage).where(PublicationPackage.deleted_at.is_(None))
    if project_id is not None:
        research._project(session, project_id)
        query = query.where(PublicationPackage.project_id == project_id)
    else:
        _submission(session, submission_id or "")
        query = query.where(PublicationPackage.submission_id == submission_id)
    return list(
        session.scalars(
            query.order_by(PublicationPackage.submission_id, PublicationPackage.version.desc())
        )
    )


def _require_draft(package: PublicationPackage) -> None:
    if package.state != "draft":
        raise PackageError("only a draft package can be edited")


def set_cover_letter(
    session: Session,
    package_id: str,
    *,
    text: str,
    state: str = "draft",
    review_note: str = "",
) -> PublicationPackage:
    package = _package(session, package_id)
    _require_draft(package)
    if state not in COVER_LETTER_STATES - {"missing"}:
        raise PackageError("cover-letter state must be draft or confirmed")
    content = text.strip()
    if not content:
        raise PackageError("cover letter text is required")
    note = review_note.strip()
    if state == "confirmed" and not note:
        raise PackageError("confirmed cover letter requires a human review note")
    package.cover_letter = content
    package.cover_letter_state = state
    package.cover_letter_review_note = note
    _record(
        session,
        package,
        "update_cover_letter",
        {"state": state, "review_note": note, "content_hash": stable_hash({"text": content})},
    )
    return package


def draft_cover_letter(
    session: Session,
    package_id: str,
    *,
    significance: str,
    venue_fit: str,
    editor_name: str = "Editor",
) -> PublicationPackage:
    package = _package(session, package_id)
    _require_draft(package)
    significance = significance.strip()
    venue_fit = venue_fit.strip()
    if not significance or not venue_fit:
        raise PackageError("significance and venue_fit are required for the template")
    submission = _submission(session, package.submission_id)
    manuscript = session.get(ResearchObject, package.manuscript_id)
    credit = authorship.export_credit(session, package.manuscript_id)
    approved_names = [author["display_name"] for author in credit["authors"]]
    signer = next(
        (author["display_name"] for author in credit["authors"] if author["corresponding"]),
        approved_names[0] if approved_names else "Corresponding author",
    )
    venue_name = submission.venue_name or "your journal"
    text = (
        f"Dear {editor_name.strip() or 'Editor'},\n\n"
        f'Please consider our manuscript, “{manuscript.title},” for publication in '
        f"{venue_name}.\n\n{significance}\n\n{venue_fit}\n\n"
        "The accompanying package is intended to contain the manuscript files and "
        "declaration statements for author review.\n\nSincerely,\n"
        f"{signer}"
    )
    package.cover_letter = text
    package.cover_letter_state = "draft"
    package.cover_letter_review_note = ""
    _record(
        session,
        package,
        "draft_cover_letter_template",
        {"deterministic": True, "provider_call": False, "venue": venue_name},
    )
    return package


def set_declaration(
    session: Session,
    package_id: str,
    *,
    kind: str,
    state: str,
    text: str = "",
    review_note: str = "",
) -> PublicationPackage:
    package = _package(session, package_id)
    _require_draft(package)
    if kind not in DECLARATION_TYPES:
        raise PackageError(f"declaration kind must be one of {sorted(DECLARATION_TYPES)}")
    if state not in DECLARATION_STATES - {"missing"}:
        raise PackageError("declaration state must be draft, confirmed, or not_applicable")
    content = text.strip()
    note = review_note.strip()
    if state == "confirmed" and (not content or not note):
        raise PackageError("confirmed declaration requires text and a human review note")
    if state == "not_applicable" and not note:
        raise PackageError("not_applicable declaration requires a human review note")
    declarations = [dict(item) for item in package.declarations]
    target = next(item for item in declarations if item["kind"] == kind)
    target.update(
        state=state,
        text=content,
        review_note=note,
        updated_at=utcnow().isoformat(),
    )
    package.declarations = declarations
    _record(
        session,
        package,
        "update_publication_declaration",
        {
            "kind": kind,
            "state": state,
            "review_note": note,
            "content_hash": stable_hash({"text": content}),
        },
    )
    return package


def _snapshot(session: Session, package: PublicationPackage) -> tuple[dict, str]:
    submission = _submission(session, package.submission_id)
    manuscript, sections, claims, sources = export_service._collect(session, package.manuscript_id)
    venue = session.get(VenueProfile, submission.venue_id) if submission.venue_id else None
    findings = audits.audit_manuscript(session, package.manuscript_id)
    venue_findings = (
        venues.audit_venue_compliance(session, package.manuscript_id, venue.id) if venue else []
    )
    artifacts = list(
        session.scalars(
            select(ResearchObject).where(
                ResearchObject.project_id == package.project_id,
                ResearchObject.kind.in_([ObjectKind.FIGURE, ObjectKind.TABLE]),
                ResearchObject.deleted_at.is_(None),
            )
        )
    )
    snapshot = {
        "package": {
            "id": package.id,
            "version": package.version,
            "included_formats": list(package.included_formats),
            "cover_letter": package.cover_letter,
            "cover_letter_state": package.cover_letter_state,
            "cover_letter_review_note": package.cover_letter_review_note,
            "declarations": list(package.declarations),
        },
        "submission": {
            "id": submission.id,
            "venue_id": submission.venue_id,
            "venue_name": submission.venue_name,
            "status": submission.status,
            "deadline": submission.deadline,
            "revisions": list(submission.revisions),
        },
        "venue": None
        if venue is None
        else {
            "id": venue.id,
            "name": venue.name,
            "rules": venue.rules,
            "rules_source": venue.rules_source,
            "retrieved_at": venue.retrieved_at.isoformat() if venue.retrieved_at else None,
            "verified": venue.verified,
        },
        "manuscript": {"id": manuscript.id, "title": manuscript.title, "body": manuscript.body},
        "sections": [
            {"id": section.id, "title": section.title, "body": section.body}
            for section in sections
        ],
        "claims": [
            {"id": claim.id, "text": claim.text, "support": str(claim.support), "notes": claim.notes}
            for claim in claims.values()
        ],
        "sources": [
            {
                "id": source.id,
                "title": source.title,
                "authors": source.authors,
                "doi": source.doi,
                "access": str(source.access),
                "human_verified": source.human_verified,
                "integrity_note": source.integrity_note,
            }
            for source in sources.values()
        ],
        "artifacts": [
            {"id": artifact.id, "kind": str(artifact.kind), "title": artifact.title, "body": artifact.body}
            for artifact in artifacts
        ],
        "authorship": authorship.export_credit(session, package.manuscript_id),
        "audit_findings": findings,
        "venue_findings": venue_findings,
    }
    return snapshot, stable_hash(snapshot)


def readiness(session: Session, package_id: str) -> dict:
    package = _package(session, package_id)
    snapshot, current_hash = _snapshot(session, package)
    blockers: list[dict] = []
    warnings: list[dict] = []
    if package.cover_letter_state != "confirmed":
        blockers.append({"code": "cover-letter-unconfirmed", "message": "cover letter is not confirmed"})
    for declaration in package.declarations:
        if declaration["state"] not in {"confirmed", "not_applicable"}:
            blockers.append(
                {
                    "code": "declaration-unconfirmed",
                    "message": f"{declaration['label']} is {declaration['state']}",
                }
            )
    if snapshot["authorship"]["status"] != "human_approved":
        blockers.append(
            {"code": "authorship-unapproved", "message": "current authorship order is not human-approved"}
        )
    for finding in snapshot["audit_findings"]:
        if finding["severity"] in {"error", "blocker"}:
            blockers.append(
                {
                    "code": "manuscript-audit-blocker",
                    "message": f"{finding['code']}: {finding['message']}",
                }
            )
    if snapshot["venue"] is None:
        warnings.append(
            {
                "code": "venue-profile-missing",
                "message": "no venue profile is attached; venue checks unavailable",
            }
        )
    elif not snapshot["venue"]["verified"]:
        warnings.append(
            {"code": "venue-profile-unverified", "message": "venue profile is not human-verified"}
        )
    warnings.extend(
        {"code": item["code"], "message": item["message"]}
        for item in snapshot["venue_findings"]
    )
    if "jats" in package.included_formats and not get_settings().jats_dtd_path:
        warnings.append(
            {
                "code": "jats-subset-validation",
                "message": "JATS will use the bundled subset DTD, not the full JATS 1.3 DTD",
            }
        )
    stale = package.basis_hash is not None and package.basis_hash != current_hash
    return {
        "ready": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "current_basis_hash": current_hash,
        "stored_basis_hash": package.basis_hash,
        "stale": stale,
    }


def prepare_for_review(session: Session, package_id: str) -> PublicationPackage:
    package = _package(session, package_id)
    _require_draft(package)
    status = readiness(session, package_id)
    if status["blockers"]:
        codes = ", ".join(item["code"] for item in status["blockers"])
        raise PackageError(f"package is not review-ready: {codes}")
    snapshot, basis_hash = _snapshot(session, package)
    package.snapshot = snapshot
    package.basis_hash = basis_hash
    package.state = "review_ready"
    package.history = [*package.history, _event("draft", "review_ready", "snapshot frozen")]
    _record(
        session,
        package,
        "prepare_publication_package",
        {"basis_hash": basis_hash, "warning_codes": [w["code"] for w in status["warnings"]]},
    )
    return package


def review_package(
    session: Session, package_id: str, *, decision: str, note: str
) -> PublicationPackage:
    package = _package(session, package_id)
    if package.state != "review_ready":
        raise PackageError("only a review_ready package can be approved or rejected")
    if decision not in {"approved", "rejected"}:
        raise PackageError("decision must be approved or rejected")
    review_note = note.strip()
    if not review_note:
        raise PackageError("a human package-review note is required")
    if decision == "approved":
        status = readiness(session, package_id)
        if status["stale"]:
            raise PackageError("package snapshot is stale; create a new package version")
        if status["blockers"]:
            raise PackageError("package no longer satisfies approval requirements")
        for old in session.scalars(
            select(PublicationPackage).where(
                PublicationPackage.submission_id == package.submission_id,
                PublicationPackage.state == "approved",
                PublicationPackage.id != package.id,
                PublicationPackage.deleted_at.is_(None),
            )
        ):
            old.state = "superseded"
            old.history = [
                *old.history,
                _event("approved", "superseded", f"superseded by package {package.id}"),
            ]
    package.state = decision
    package.review_note = review_note
    package.history = [*package.history, _event("review_ready", decision, review_note)]
    _record(
        session,
        package,
        "review_publication_package",
        {"decision": decision, "note": review_note, "basis_hash": package.basis_hash},
    )
    return package


def _declarations_markdown(package: PublicationPackage, credit: dict) -> str:
    lines = ["# Publication declarations", ""]
    for declaration in package.declarations:
        lines += [f"## {declaration['label']}", ""]
        if declaration["state"] == "not_applicable":
            lines += [f"Not applicable. Review note: {declaration['review_note']}", ""]
        else:
            lines += [declaration["text"], ""]
    lines += ["## Author contributions (CRediT)", ""]
    for author in credit["authors"]:
        roles = ", ".join(
            f"{role['label']} ({role['degree']})" for role in author["credit_roles"]
        )
        lines.append(f"- {author['display_name']}: {roles}")
    return "\n".join(lines) + "\n"


def _responses_markdown(submission: Submission) -> str | None:
    if not submission.revisions:
        return None
    lines = ["# Response to reviewers", ""]
    for revision in submission.revisions:
        lines += [f"## Round {revision['round']}", "", revision["summary"], ""]
        lines += [revision["response_to_reviewers"], ""]
        if revision.get("changes"):
            lines += ["### Changes", ""] + [f"- {item}" for item in revision["changes"]] + [""]
    return "\n".join(lines)


def build_bundle(session: Session, package_id: str) -> dict:
    package = _package(session, package_id)
    if package.state != "approved":
        raise PackageError("only an approved publication package can be built")
    status = readiness(session, package_id)
    if status["stale"]:
        raise PackageError("approved package is stale; create and approve a new version")
    if status["blockers"]:
        raise PackageError("approved package no longer satisfies build requirements")

    export = export_service.export_manuscript(
        session, package.manuscript_id, formats=list(package.included_formats)
    )
    if "jats" in package.included_formats:
        validation = export.get("jats_validation") or {}
        if validation.get("valid") is False:
            raise PackageError("JATS validation failed; package was not assembled")

    submission = _submission(session, package.submission_id)
    snapshot, basis_hash = _snapshot(session, package)
    if basis_hash != package.basis_hash:
        raise PackageError("package changed during export; package was not assembled")
    credit = snapshot["authorship"]
    files: dict[str, bytes] = {
        "cover-letter.md": ("# Cover letter\n\n" + package.cover_letter + "\n").encode(),
        "declarations.md": _declarations_markdown(package, credit).encode(),
        "declarations.json": json.dumps(
            {"declarations": package.declarations, "authorship": credit}, indent=2
        ).encode(),
        "venue-compliance.json": json.dumps(
            {
                "venue": snapshot["venue"],
                "findings": snapshot["venue_findings"],
                "advisory_when_unverified": True,
            },
            indent=2,
            default=str,
        ).encode(),
    }
    response = _responses_markdown(submission)
    if response:
        files["response-to-reviewers.md"] = response.encode()
    for _format_name, path_text in export["files"].items():
        path = Path(path_text)
        files[f"manuscript/{path.name}"] = path.read_bytes()

    checksums = {name: hashlib.sha256(payload).hexdigest() for name, payload in files.items()}
    manifest = {
        "format_version": 1,
        "package_id": package.id,
        "package_version": package.version,
        "submission_id": package.submission_id,
        "manuscript_id": package.manuscript_id,
        "venue_name": submission.venue_name,
        "built_at": datetime.now(UTC).isoformat(),
        "basis_hash": package.basis_hash,
        "review_state": package.state,
        "review_note": package.review_note,
        "local_bundle_only": True,
        "external_submission_performed": False,
        "warnings": status["warnings"],
        "files": {name: {"sha256": checksum} for name, checksum in checksums.items()},
    }
    manifest_bytes = json.dumps(manifest, indent=2).encode()
    files["package-manifest.json"] = manifest_bytes

    out_dir = Path(get_settings().data_dir) / "exports" / "submissions" / submission.id
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = out_dir / f"publication-package-v{package.version}.zip"
    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            archive.writestr(name, files[name])
    bundle_sha = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    build = {
        "at": datetime.now(UTC).isoformat(),
        "filename": bundle_path.name,
        "sha256": bundle_sha,
        "basis_hash": package.basis_hash,
        "file_count": len(files),
    }
    package.builds = [*package.builds, build]
    _record(session, package, "build_publication_package", build)
    return {
        "path": str(bundle_path),
        "sha256": bundle_sha,
        "file_count": len(files),
        "manifest": manifest,
        "external_submission_performed": False,
    }


def package_out(session: Session, package: PublicationPackage) -> dict:
    status = readiness(session, package.id)
    return {
        "id": package.id,
        "project_id": package.project_id,
        "submission_id": package.submission_id,
        "manuscript_id": package.manuscript_id,
        "version": package.version,
        "state": package.state,
        "included_formats": list(package.included_formats),
        "cover_letter": package.cover_letter,
        "cover_letter_state": package.cover_letter_state,
        "cover_letter_review_note": package.cover_letter_review_note,
        "declarations": list(package.declarations),
        "basis_hash": package.basis_hash,
        "review_note": package.review_note,
        "history": list(package.history),
        "builds": list(package.builds),
        "readiness": status,
    }
