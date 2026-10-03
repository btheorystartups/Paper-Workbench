"""Version-bound review dispositions. An author response never closes its own objection."""

from copy import deepcopy

from ..models import ResearchObject, stable_hash
from . import evidence_basis, research


def candidate_hash(session, manuscript_id: str) -> str:
    session.flush()
    session.expire_all()
    basis = evidence_basis.collect(session, manuscript_id)
    # Review records bind the candidate, but must not recursively hash their own events.
    basis["records"] = {
        key: value
        for key, value in basis["records"].items()
        if not value.get("body", {}).get("revision_review")
    }
    return stable_hash(basis)


def open_round(session, manuscript_id: str, *, comments: list[dict], reviewer: str):
    manuscript = session.get(ResearchObject, manuscript_id)
    if not manuscript or not reviewer.strip() or not comments:
        raise research.IntegrityError("review requires a manuscript, reviewer and comments")
    identifiers = [c.get("id") for c in comments]
    if len(set(identifiers)) != len(identifiers) or any(
        not c.get("id") or not c.get("objection") or not c.get("acceptance_criterion") for c in comments
    ):
        raise research.IntegrityError("review comments require unique IDs and acceptance criteria")
    return research.create_object(
        session,
        manuscript.project_id,
        kind="note",
        title="Revision review",
        body={
            "revision_review": True,
            "manuscript_id": manuscript_id,
            "candidate_hash": candidate_hash(session, manuscript_id),
            "reviewer": reviewer,
            "comments": deepcopy(comments),
            "events": [],
        },
    )


def respond(session, round_id: str, *, comment_id: str, author: str, response: str, changes: str):
    review = _round(session, round_id, comment_id)
    if not author.strip() or not response.strip() or not changes.strip():
        raise research.IntegrityError("response requires author, explanation and exact changes or rejection")
    _append(
        review,
        {
            "kind": "response",
            "comment_id": comment_id,
            "author": author,
            "response": response,
            "changes": changes,
            "candidate_hash": candidate_hash(session, review.body["manuscript_id"]),
        },
    )


def verify(
    session,
    round_id: str,
    *,
    comment_id: str,
    verifier: str,
    response_hash: str,
    expected_candidate_hash: str,
    expected_comment_hash: str,
    criterion_met: bool,
    regression_passed: bool,
    evidence: str,
    disposition: str,
):
    review = _round(session, round_id, comment_id)
    response = next(
        (
            e
            for e in reversed(review.body["events"])
            if e["kind"] == "response" and e["comment_id"] == comment_id
        ),
        None,
    )
    current = candidate_hash(session, review.body["manuscript_id"])
    comment = next(c for c in review.body["comments"] if c["id"] == comment_id)
    if expected_comment_hash != stable_hash(comment):
        raise research.IntegrityError("review criterion changed; verification required")
    if type(criterion_met) is not bool or type(regression_passed) is not bool:
        raise research.IntegrityError("verification assessments must be boolean")
    if (
        not response
        or stable_hash(response) != response_hash
        or response["candidate_hash"] != current
        or expected_candidate_hash != current
    ):
        raise research.IntegrityError("response or candidate changed; verification required")
    if not verifier.strip() or verifier == response["author"] or not evidence.strip():
        raise research.IntegrityError("independent verifier and evidence required")
    if disposition not in {"open", "resolved", "justified_rejection", "regressed"}:
        raise research.IntegrityError("invalid disposition")
    if disposition in {"resolved", "justified_rejection"} and not (criterion_met and regression_passed):
        raise research.IntegrityError("closure requires criterion and regression assessment")
    _append(
        review,
        {
            "kind": "verification",
            "comment_id": comment_id,
            "verifier": verifier,
            "response_hash": response_hash,
            "comment_hash": expected_comment_hash,
            "candidate_hash": current,
            "criterion_met": criterion_met,
            "regression_passed": regression_passed,
            "evidence": evidence,
            "disposition": disposition,
        },
    )


def dispositions(session, review) -> dict[str, str]:
    current = candidate_hash(session, review.body["manuscript_id"])
    result = {c["id"]: "open" for c in review.body["comments"]}
    responses = {}
    for event in review.body["events"]:
        comment = next(c for c in review.body["comments"] if c["id"] == event["comment_id"])
        if event["kind"] == "response":
            responses[event["comment_id"]] = event
        result[event["comment_id"]] = (
            event["disposition"]
            if event["kind"] == "verification"
            and event["candidate_hash"] == current
            and event.get("comment_hash") == stable_hash(comment)
            and event.get("response_hash") == stable_hash(responses.get(event["comment_id"]))
            else "open"
        )
    return result


def _round(session, identifier, comment_id):
    review = session.get(ResearchObject, identifier)
    if (
        not review
        or review.deleted_at
        or not review.body.get("revision_review")
        or comment_id not in {c["id"] for c in review.body["comments"]}
    ):
        raise research.IntegrityError("review comment not found")
    return review


def _append(review, event):
    review.body = {**review.body, "events": [*review.body["events"], event]}
