"""Venue profiles + compliance audit. Rules are data with provenance: where they came
from (rules_source) and when; a human must mark a profile `verified` before the audit
treats findings as authoritative (unverified profiles produce advisory findings only)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ResearchObject, VenueProfile
from ..vocab import ObjectKind
from . import authoring, research

KNOWN_RULES = {
    "word_limit": int, "abstract_word_limit": int, "required_sections": list,
    "max_figures": int, "max_references": int, "citation_style": str,
    "anonymized_review": bool, "ai_disclosure_required": bool,
}


def create_venue(
    session: Session, workspace_id: str, *, name: str, rules: dict,
    rules_source: str,
) -> VenueProfile:
    if not rules_source.strip():
        raise research.IntegrityError(
            "venue profiles require rules_source (where the rules were obtained)"
        )
    unknown = set(rules) - set(KNOWN_RULES)
    if unknown:
        raise research.IntegrityError(f"unknown rule keys: {sorted(unknown)}")
    venue = VenueProfile(
        workspace_id=workspace_id, name=name, rules=rules,
        rules_source=rules_source, retrieved_at=datetime.now(UTC),
    )
    session.add(venue)
    session.flush()
    return venue


def verify_venue(session: Session, venue_id: str) -> VenueProfile:
    venue = session.get(VenueProfile, venue_id)
    if venue is None:
        raise research.IntegrityError("venue not found")
    venue.verified = True
    return venue


def audit_venue_compliance(session: Session, manuscript_id: str, venue_id: str) -> list[dict]:
    venue = session.get(VenueProfile, venue_id)
    if venue is None:
        raise research.IntegrityError("venue not found")
    manuscript = session.get(ResearchObject, manuscript_id)
    if manuscript is None or manuscript.kind != ObjectKind.MANUSCRIPT:
        raise research.IntegrityError("manuscript not found")
    sections = authoring.manuscript_sections(session, manuscript_id)
    severity = "warning" if venue.verified else "info"
    findings: list[dict] = []
    if not venue.verified:
        findings.append(
            {"severity": "info", "code": "venue-unverified",
             "message": f"venue profile '{venue.name}' is not human-verified; findings are advisory",
             "object_id": venue.id}
        )
    rules = venue.rules
    total_words = sum(len(s.body.get("text", "").split()) for s in sections)
    if "word_limit" in rules and total_words > rules["word_limit"]:
        findings.append(
            {"severity": severity, "code": "venue-word-limit",
             "message": f"manuscript has ~{total_words} words; limit {rules['word_limit']}",
             "object_id": manuscript_id}
        )
    headings = {s.title.strip().lower() for s in sections}
    for required in rules.get("required_sections", []):
        if required.strip().lower() not in headings:
            findings.append(
                {"severity": severity, "code": "venue-missing-section",
                 "message": f"required section '{required}' not present",
                 "object_id": manuscript_id}
            )
    if "abstract_word_limit" in rules:
        abstract = next((s for s in sections if s.title.strip().lower() == "abstract"), None)
        if abstract is not None:
            n = len(abstract.body.get("text", "").split())
            if n > rules["abstract_word_limit"]:
                findings.append(
                    {"severity": severity, "code": "venue-abstract-limit",
                     "message": f"abstract has {n} words; limit {rules['abstract_word_limit']}",
                     "object_id": abstract.id}
                )
    if rules.get("ai_disclosure_required"):
        has_disclosure = any("ai" in s.title.lower() and "disclosure" in s.title.lower()
                             for s in sections)
        if not has_disclosure:
            findings.append(
                {"severity": severity, "code": "venue-ai-disclosure",
                 "message": "venue requires an AI-assistance disclosure section",
                 "object_id": manuscript_id}
            )
    return findings
