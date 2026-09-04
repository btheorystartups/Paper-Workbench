"""Controlled vocabularies (Phase 0 decision record, ADR-5).

These state vocabularies are the product's core integrity mechanism: they are stored on
rows, surfaced in every UI/export, and must never be collapsed into vague confidence prose.
"""

from enum import StrEnum


class ClaimSupport(StrEnum):
    RESEARCH_RESULT = "research_result"
    EXTERNAL_SOURCE = "external_source"
    BOTH = "both"
    COMMON_KNOWLEDGE = "common_knowledge"
    INTERPRETATION = "interpretation"
    HYPOTHESIS = "hypothesis"
    UNSUPPORTED = "unsupported"
    VERIFICATION_REQUIRED = "verification_required"


class ResultStrength(StrEnum):
    FORMALLY_ESTABLISHED = "formally_established"
    EMPIRICALLY_ESTABLISHED = "empirically_established"
    COMPUTATIONALLY_VERIFIED_WITHIN_SCOPE = "computationally_verified_within_scope"
    HEURISTICALLY_SUPPORTED = "heuristically_supported"
    CONJECTURED = "conjectured"
    AI_SUGGESTED = "ai_suggested"


class Novelty(StrEnum):
    APPARENTLY_NOVEL_LIMITED_SEARCH = "apparently_novel_limited_search"
    RELATED_WORK_WITH_DISTINCTION = "related_work_with_distinction"
    KNOWN_RESULT_NEW_DERIVATION_POSSIBLE = "known_result_new_derivation_possible"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    PROBABLY_NOT_NOVEL = "probably_not_novel"
    EXPERT_CONFIRMATION_REQUIRED = "expert_confirmation_required"


class SourceAccess(StrEnum):
    METADATA_ONLY = "metadata_only"
    ABSTRACT_ONLY = "abstract_only"
    EXCERPT_AVAILABLE = "excerpt_available"
    FULL_TEXT_AUTHORIZED = "full_text_authorized"
    FULL_TEXT_USER_SUPPLIED = "full_text_user_supplied"


class ObjectKind(StrEnum):
    """Research-object kinds. One typed table + kind keeps the graph extensible without a
    migration per concept; kind-specific payload lives in `ResearchObject.body`."""

    QUESTION = "question"
    HYPOTHESIS = "hypothesis"
    CONJECTURE = "conjecture"
    RESULT = "result"
    METHOD = "method"
    DEFINITION = "definition"
    ASSUMPTION = "assumption"
    LIMITATION = "limitation"
    DECISION = "decision"
    TASK = "task"
    NOTE = "note"
    DATASET = "dataset"
    ANALYSIS = "analysis"
    FIGURE = "figure"
    TABLE = "table"
    MANUSCRIPT = "manuscript"
    SECTION = "section"
    PAPER_CANDIDATE = "paper_candidate"


class Relation(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DEPENDS_ON = "depends_on"
    DERIVES_FROM = "derives_from"
    RELATES_TO = "relates_to"
    SUPERSEDES = "supersedes"
    PART_OF = "part_of"
    CITES = "cites"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    INVALIDATED = "invalidated"


class RiskClass(StrEnum):
    READ_ONLY = "read_only"       # may run without confirmation
    REVERSIBLE = "reversible"     # internal mutation: visible review + undo
    EXTERNAL = "external"         # provider cost or outward effect: explicit confirmation
