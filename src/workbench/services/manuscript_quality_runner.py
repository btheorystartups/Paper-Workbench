"""Bounded specialist manuscript production using the existing Runner and review ledger."""

import json
import time
from types import SimpleNamespace

from ..models import ResearchAgent, ResearchObject, stable_hash
from ..providers.research_executor import ExecutorError
from ..research_contract import (
    MANUSCRIPT_HANDOFF_TOKEN_RESERVE,
    MAX_REVISION_COMMENTS,
    SPECIALIST_ROLES,
    Synthesis,
)
from . import manuscript_acquisition, research_trace, revision_review
from . import manuscript_closure as closure
from . import manuscript_quality as quality
from .research_recovery import (
    ReplayHandle,
    normalization_authority,
    normalize_review_report,
    retained_reviews,
)
from .research_runner import StopResearch, allocation_charge

FINAL_HANDOFF_RESERVE = MANUSCRIPT_HANDOFF_TOKEN_RESERVE
CLOSURE_CALL_RESERVE = 45000


def _protected_reserve(runner):
    return FINAL_HANDOFF_RESERVE + (CLOSURE_CALL_RESERVE if closure.enabled(runner.task) else 0)


def _historical(runner, field):
    return [item for run in getattr(runner.task, "ledger", {}).get("previous_runs", [])
            for item in run["ledger"].get(field, [])]


def _cycle_timing(runner):
    events = [*_historical(runner, "call_trace"),
              *getattr(runner.task, "ledger", {}).get("call_trace", [])]
    calls = research_trace.summary(events)["calls"]
    kinds = {a.get("span_id"): a.get("operation_kind")
             for a in [*_historical(runner, "allocations"), *runner.allocations]}
    durations, author, author_repairs, report_repairs = {}, None, [], []
    for call in calls:
        if call["status"] != "return":
            continue
        seconds = call["duration_seconds"]
        if kinds.get(call["span_id"]) == "draft_correction":
            author_repairs.append(seconds)
            continue
        if kinds.get(call["span_id"]) == "report_correction":
            report_repairs.append(seconds)
            continue
        if call["operation"] == "audit" and call["role"] in SPECIALIST_ROLES:
            durations[call["role"]] = max(durations.get(call["role"], 0), seconds)
        elif call["operation"] in {"draft", "revise"}:
            author = max(author or 0, seconds)
    review = None
    if set(durations) == set(SPECIALIST_ROLES):
        first = [durations[role] for role in SPECIALIST_ROLES[:3]]
        review = max(max(first), min(first) + durations[SPECIALIST_ROLES[3]])
    deadline = getattr(runner, "research_deadline", None)
    remaining = max(0, deadline - time.monotonic()) if deadline is not None else None
    cycle = author + review if author is not None and review is not None else None
    # Dispatch-to-return includes worker RPC setup. New reviewer process startup
    # happens before dispatch; budget four serial launches using observed spans.
    starts = {e["span_id"]: e["elapsed_seconds"] for e in events if e["event"] == "spawn_started"}
    spawns = [max(0, e["elapsed_seconds"] - starts[e["span_id"]]) for e in events
              if e["event"] == "spawn_finished" and e["span_id"] in starts]
    startup = max(5.0, 4 * max(spawns, default=0) * 1.25)
    author_repair = max([author, *author_repairs]) if author is not None else None
    report_repair = (
        max(report_repairs, default=max(durations.values(), default=0)) if review is not None else None
    )
    closure_time = (90.0 if getattr(runner.task, "contract", {}).get("quality_policy")
                    == closure.QUALITY_POLICY else 0.0)
    required = (1.25 * (cycle + author_repair + report_repair) + startup + closure_time
                if cycle is not None else None)
    return {
        "observed_author_seconds": author,
        "observed_role_seconds": durations,
        "review_wave_seconds": review,
        "revision_and_review_seconds": cycle,
        "author_repair_seconds": author_repair,
        "report_repair_pool_seconds": report_repair,
        "author_repair_basis": "observed" if author_repairs else "ordinary_author_fallback",
        "report_repair_basis": "observed" if report_repairs else "largest_reviewer_fallback",
        "startup_reserve_seconds": startup,
        "editorial_confirmation_reserve_seconds": closure_time,
        "margin": 1.25,
        "required_remaining_seconds": required,
        "shortfall_seconds": max(0, required - remaining)
        if required is not None and remaining is not None
        else None,
        "remaining_research_seconds": remaining,
        "policy": "observed-duration-with-repair-margin-v1",
        "status": "unestimated"
        if cycle is None
        else (
            "insufficient_time"
            if remaining is not None and required > remaining
            else "observed_duration_estimate"
        ),
        "notice": "Three-slot review forecast plus one author correction and one shared report-repair pool, "
        "25% duration margin and reviewer startup reserve. Handoff time stays outside the research "
        "deadline. This estimate cannot guarantee service latency or fund every possible repair.",
    }


def _admit_author_time(runner, campaign, *, revision, correction):
    """Recompute immediately before dispatch; a prior forecast is not an admission receipt."""
    timing = _cycle_timing(runner)
    if correction:
        repair = timing["author_repair_seconds"]
        # The first draft has no observed specialist wave. Protect the known repair
        # cost without inventing review timings. Revision corrections need follow-through.
        required = None if repair is None else 1.25 * (repair + (
            (timing["review_wave_seconds"] or 0) + (timing["report_repair_pool_seconds"] or 0)
            if revision else 0)) + timing["startup_reserve_seconds"]
        if required is not None:
            required += timing["editorial_confirmation_reserve_seconds"]
    else:
        required = timing["required_remaining_seconds"]
    remaining = timing["remaining_research_seconds"]
    denied = required is not None and remaining is not None and required > remaining
    plan = {
        "operation": "revise" if revision else "draft",
        "correction": correction,
        "candidate_sha256": campaign.body["drafts"][-1]["candidate_sha256"]
        if campaign.body["drafts"]
        else None,
        "time_limit_seconds": runner.task.contract["time_limit_seconds"],
        "token_limit": runner.task.contract["token_limit"],
        "required_remaining_seconds": required,
        "remaining_research_seconds": remaining,
        "shortfall_seconds": max(0, required - remaining)
        if required is not None and remaining is not None
        else None,
        "status": "insufficient_time"
        if denied
        else "unestimated"
        if required is None or remaining is None
        else "admitted",
        "timing": timing,
    }
    quality.update_campaign(campaign, author_time_plans=[*campaign.body.get("author_time_plans", []), plan])
    research_trace.record(runner, "author_time_planned", **plan)
    runner.session.commit()
    if denied:
        raise StopResearch(
            "limit_reached_partial",
            "insufficient research time for author operation and reserved "
            "follow-through; accepted evidence and handoff reserve preserved",
        )


def _revision_budget(runner, campaign=None):
    """Plan a complete revision cycle from final usage; never release pending grants."""
    limit = runner.task.contract["token_limit"]
    # Estimate the frozen input separately from output/reasoning headroom.
    # Missing synthetic inputs use the calibrated fresh-review baseline.
    from ..providers.research_codex_worker import json_prompt, prompt_token_count

    input_tokens = prompt_token_count(json.dumps(getattr(runner.task, "sources", []), default=str))
    repair_input_tokens = input_tokens
    author_input_tokens = 0
    author_payload = {}
    role_inputs = dict.fromkeys(SPECIALIST_ROLES, input_tokens)
    if campaign and campaign.body.get("drafts"):
        digest = campaign.body["drafts"][-1]["candidate_sha256"]
        prompts, repair_prompts = [], []
        for role in SPECIALIST_ROLES:
            packet = quality.packet_for(
                runner.task, campaign, digest, role, _prior(runner.session, campaign, role))
            prompts.append(json_prompt("audit", {"packet": packet}))
            role_inputs[role] = prompt_token_count(prompts[-1])
            for agent in runner.agents:
                if agent.assignment.get("specialist_role") != role:
                    continue
                attempts = agent.provenance.get("report_attempts", [])
                if not attempts:
                    continue
                original = attempts[-1]["report"]
                issues = next((r["issues"] for r in reversed(campaign.body.get("rejected_reports", []))
                               if r["agent_id"] == agent.id), [{"code": "format_repair"}])
                repair_prompts.append(json_prompt("audit", {"packet": packet,
                    "original_report": original, "original_report_sha256": stable_hash(original),
                    "report_corrections": issues}))
        input_tokens = max(map(prompt_token_count, prompts))
        repair_input_tokens = max([input_tokens, *map(prompt_token_count, repair_prompts)])
        author_payload = _author_payload(runner, campaign, revision=True)
        author_input_tokens = prompt_token_count(json_prompt("revise", author_payload))
    length = runner.task.contract.get("manuscript_length") or {}
    declared_max_words = length.get("max_words", 0)
    review_output_headroom = max(6000, declared_max_words + 4000)
    repair_reserve = max(20000, repair_input_tokens + 6000)
    review_usage = {role: max(25000, (role_inputs[role] + review_output_headroom) * 5 // 4)
                    for role in SPECIALIST_ROLES}
    observed_reviews = {}
    author_usage = 0
    revision_usage = 0
    recovery_author_usage = 0
    seen_audits = set()
    roles = {a.id: a.assignment.get("specialist_role") for a in runner.agents}
    prompt_counts = {s["call_span_id"]: s["prompt_tokens"] for a in runner.agents
                     for s in getattr(a, "provenance", {}).get("codex_streams", [])}
    for run in getattr(runner.task, "ledger", {}).get("previous_runs", []):
        prompt_counts.update({s["call_span_id"]: s["prompt_tokens"] for a in run.get("agents", [])
                              for s in a.get("provenance", {}).get("codex_streams", [])})
    for allocation in [*_historical(runner, "allocations"), *runner.allocations]:
        if not allocation.get("final_actual") and allocation.get("usage_kind") != "actual":
            continue
        observed = allocation.get("actual_tokens") or 0
        legacy_repair = (allocation["phase"] == "audit"
                        and not allocation.get("operation_kind")
                        and allocation["agent_id"] in seen_audits)
        if allocation["phase"] == "audit":
            seen_audits.add(allocation["agent_id"])
        if legacy_repair:
            # Pre-policy report repairs retained cumulative context. They remain
            # charged but cannot forecast a future fresh correction or review.
            continue
        if allocation.get("operation_kind") in {"report_correction", "draft_correction"}:
            if (allocation.get("operation_kind") == "report_correction"
                    or not author_payload.get("section_recovery")):
                repair_reserve = max(repair_reserve, (observed * 5 + 3) // 4)
            if allocation["operation_kind"] == "draft_correction":
                recovery_author_usage = max(recovery_author_usage, (observed * 5 + 3) // 4)
            continue
        if allocation["phase"] == "audit" and roles.get(allocation["agent_id"]) in review_usage:
            role = roles[allocation["agent_id"]]
            supplied = allocation.get("prompt_tokens", prompt_counts.get(allocation.get("span_id")))
            if supplied is None and campaign:
                old_packet = next((r["packet"] for r in campaign.body.get("reports", [])
                                   if r["agent_id"] == allocation["agent_id"]), None)
                if old_packet:
                    old_input = prompt_token_count(json_prompt("audit", {"packet": old_packet}))
                    observed += max(0, role_inputs[role] - old_input)
            forecast = ((role_inputs[role] + max(review_output_headroom, observed - supplied)) * 5 // 4
                        if supplied is not None else (observed * 5 + 3) // 4)
            observed_reviews[role] = max(observed_reviews.get(role, 0), forecast,
                                         25000 if observed >= 10000 else 0)
        elif allocation["phase"] in {"draft", "revise"}:
            author_usage = max(author_usage, (observed * 5 + 3) // 4)
            if allocation["phase"] == "revise":
                revision_usage = max(revision_usage, (observed * 5 + 3) // 4)
    review_usage.update({role: max((role_inputs[role] + review_output_headroom) * 5 // 4, amount)
                         for role, amount in observed_reviews.items()})
    review_reserve = sum(review_usage.values())
    remaining = runner.remaining_tokens()
    minimum_author = (max(20000, (author_input_tokens + 12000) * 5 // 4)
                      if author_payload.get("section_recovery") else
                      max(12000, recovery_author_usage if getattr(runner, "recoverable_author_return", None)
                          else author_usage, author_input_tokens + 6000,
                          2 * author_usage if campaign and campaign.body.get("rounds")
                          and not revision_usage else 12000))
    if (campaign and campaign.body.get("drafts")
            and campaign.body["drafts"][-1].get("local_revision")
            and runner.task.ledger.get("continuation", {}).get("max_report_corrections") == 0):
        repair_reserve = 0  # Explicitly disabled calls require no reservation.
    required = review_reserve + _protected_reserve(runner) + repair_reserve + minimum_author
    # Fund the author from capacity left after protecting the complete review cycle.
    author_grant = min(minimum_author, max(0,
        remaining - review_reserve - _protected_reserve(runner) - repair_reserve))
    return {
        "candidate_sha256": campaign.body["drafts"][-1]["candidate_sha256"]
                            if campaign and campaign.body.get("drafts") else None,
        "token_limit": limit,
        "time_limit_seconds": runner.task.contract.get("time_limit_seconds"),
        "remaining_tokens": remaining,
        "review_role_reserves": review_usage,
        "review_reserve": review_reserve,
        "handoff_reserve": _protected_reserve(runner),
        "repair_reserve": repair_reserve,
        "input_token_estimate": input_tokens,
        "repair_input_token_estimate": repair_input_tokens,
        "author_input_token_estimate": author_input_tokens,
        "review_output_headroom": review_output_headroom,
        "minimum_author_grant": minimum_author,
        "author_grant": author_grant,
        "unallocated_contingency": max(0, remaining - author_grant - review_reserve
                                       - _protected_reserve(runner) - repair_reserve),
        "required_remaining_tokens": required,
        "shortfall_tokens": max(0, required - remaining),
        "author_slice_shortfall_tokens": 0,
        "minimum_total_token_limit": limit - remaining + required,
        "capacity_status": "funded" if author_grant >= minimum_author else "insufficient_tokens",
        "timing": _cycle_timing(runner),
        "policy": "operation-input-and-observed-overhead-v2",
    }


def _initial_capacity_plan(runner, campaign):
    """Forecast one conditional revision before paying for the first review wave."""
    current = _revision_budget(runner, campaign)
    digest = campaign.body["drafts"][-1]["candidate_sha256"]
    manifests = []
    for role in SPECIALIST_ROLES:
        packet = quality.packet_for(runner.task, campaign, digest, role, [])
        manifests.append({"role": role + "-0", "packet_sha256": packet["packet_sha256"],
                          "evidence_artifacts": packet["evidence_artifacts"]})
    # Forecast the known history growth without inventing future reviewer comments.
    projected = SimpleNamespace(body={**campaign.body,
        "packets": [*campaign.body["packets"], *manifests]})
    future = _revision_budget(runner, projected)
    revisions = int(runner.task.contract["max_revision_cycles"] > 0)
    base = current["review_reserve"] + _protected_reserve(runner)
    repairs = current["repair_reserve"]
    if revisions:
        base += future["minimum_author_grant"] + future["review_reserve"]
        repairs += future["repair_reserve"]
    required = base + repairs
    remaining = runner.remaining_tokens()
    return {"candidate_sha256": digest, "token_limit": runner.task.contract["token_limit"],
            "time_limit_seconds": runner.task.contract.get("time_limit_seconds"),
            "remaining_tokens": remaining, "initial_review_reserve": current["review_reserve"],
            "initial_repair_reserve": current["repair_reserve"],
            "conditional_revision": future if revisions else None,
            "forecast_revision_cycles": revisions,
            "additional_cycles_not_forecast": max(0, runner.task.contract["max_revision_cycles"] - revisions),
            "required_without_format_repairs": base, "required_remaining_tokens": required,
            "shortfall_tokens": max(0, required - remaining),
        "minimum_total_token_limit": runner.task.contract["token_limit"] - remaining + required,
        "capacity_status": "estimated_funded" if remaining >= required else "capacity_risk",
            "policy": "conditional-one-revision-with-fresh-context",
            "unknowns": ["future candidate size", "reviewer objections and responses",
                         "model overhead and reasoning", "actual usage", "wall time"]}


def _prior(session, campaign, role=None):
    result = []
    for identifier in campaign.body["rounds"]:
        review = session.get(ResearchObject, identifier)
        for comment in review.body["comments"]:
            if role and comment["specialist_role"] != role:
                continue
            response = next(
                (
                    r
                    for r in reversed(review.body["events"])
                    if r["kind"] == "response" and r["comment_id"] == comment["id"]
                ),
                None,
            )
            result.append({
                **comment, "round_id": identifier,
                "reviewed_candidate_sha256": review.body["candidate_hash"],
                "response": response,
            })
    return result


def _author_payload(runner, campaign, *, revision=False):
    prior = _prior(runner.session, campaign) if revision else []
    previous = campaign.body["drafts"][-1]["candidate"] if revision else None
    payload = {
        "contract": runner.task.contract,
        "sources": [
            {k: v for k, v in s.items() if k not in {"artifact", "extracted_artifact"}}
            for s in runner.task.sources
            if s.get("source_id")
        ],
        "verification_receipts": campaign.body["verification_receipts"],
        "search_receipts": campaign.body["search_receipts"],
        "prior_comments": prior,
        "editorial_findings": ((campaign.body.get("closure_reports") or [{}])[0]
            .get("report", {}).get("findings", [])) if revision else [],
        "expected_response_ids": sorted(c["id"] for c in prior),
        "previous_candidate": previous,
        "previous_candidate_sha256": stable_hash(previous) if previous else None,
    }
    if revision and getattr(runner, "author_checkpoint", None):
        from ..providers.research_codex_worker import author_evidence_hash

        payload["author_checkpoint"] = {
            "checkpoint_sha256": runner.author_checkpoint,
            "draft_sha256": stable_hash(previous),
            "evidence_sha256": author_evidence_hash(payload),
        }
        original = getattr(runner, "recoverable_author_return", None)
        if original:
            from ..research_contract import MAX_MANUSCRIPT_CLAIMS

            raw = original["result"]
            identifiers = sorted({claim["id"] for claim in raw["claims"]} | {
                identifier for section in raw["sections"] for identifier in section["claim_ids"]})
            if len(identifiers) > MAX_MANUSCRIPT_CLAIMS:
                raise StopResearch("failed_partial", "retained claim inventory exceeds recovery capacity")
            measured = quality.length_check(raw, runner.task.contract.get("manuscript_length"))
            payload.update(
                original_draft=raw, original_draft_sha256=original["result_sha256"],
                recovery_claim_ids=identifiers,
                draft_corrections=[
                    {"code": "claim_inventory", "required_claim_ids": identifiers,
                     "message": "Declare every required claim ID; add the missing source-grounded inventory "
                                "entries. Keep all section IDs and all required reviewer response IDs."},
                    {"code": "manuscript_length", **measured,
                     "message": "Extend the retained analysis with source-grounded substance to the "
                                "declared word range with a margin above its lower edge. "
                                "Check ALL final sections together; minimize repeated "
                                "length-tool calls because each resends context."},
                ],
                author_return_checkpoint={
                    "checkpoint_sha256": runner.author_checkpoint,
                    "draft_sha256": original["result_sha256"],
                    "evidence_sha256": author_evidence_hash(payload),
                },
                length_check_limit=1,
            )
            payload["draft_corrections"].extend(quality.manuscript_integrity.candidate_issues(raw))
            old_sections = {section["id"]: section for section in previous["sections"]}
            new_sections = {section["id"]: section for section in raw["sections"]}
            missing = set(old_sections) - set(new_sections)
            references = [s for s in new_sections.values() if s["heading"].strip().lower() == "references"]
            missing_references = [s for s in old_sections.values()
                                  if s["id"] in missing and s["heading"].strip().lower() == "references"]
            bounds = runner.task.contract.get("manuscript_length") or {}
            minimum = max(1000, bounds.get("min_words", 0) - measured["word_count"])
            maximum = min(1300, bounds.get("max_words", 0) - measured["word_count"])
            if (len(missing) == len(missing_references) == len(references) == 1
                    and references[0]["id"] in old_sections
                    and old_sections[references[0]["id"]]["heading"].strip().lower() != "references"
                    and set(identifiers) == {claim["id"] for claim in raw["claims"]}
                    and minimum <= maximum and len(new_sections) < 24):
                payload["section_recovery"] = {
                    "discussion_id": references[0]["id"], "reference_id": missing_references[0]["id"],
                    "discussion_heading": old_sections[references[0]["id"]]["heading"],
                    "base_sha256": original["result_sha256"], "min_words": minimum, "max_words": maximum,
                }
                parent = next(a for a in runner.agents if a.role == "parent")
                invalid = next((r for r in reversed(parent.provenance.get("invalid_returns", []))
                                if r.get("base_sha256") == original["result_sha256"]
                                and r.get("identity_verified")), None)
                if invalid:
                    payload["prior_section_return"] = invalid["result"]
    return payload


def _author(
    runner, parent, handle, manuscript, campaign, allowance, *, revision=False,
    protected_after_author=None,
):
    if allowance < 1000:
        raise StopResearch("limit_reached_partial", "final specialist review reservation preserved")
    operation = "revise" if revision else "draft"
    payload = _author_payload(runner, campaign, revision=revision)
    if protected_after_author is None:
        protected_after_author = runner.remaining_tokens() - allowance
    protected_after_author = max(0, protected_after_author)
    initial_allowance = allowance
    for attempt in range(1 if getattr(runner, "recoverable_author_return", None) else 0, 2):
        runner.check()
        available = runner.remaining_tokens() - protected_after_author
        allowance = min(initial_allowance, available)
        research_trace.record(
            runner,
            "author_budget_planned",
            agent=parent,
            operation=operation,
            attempt=attempt,
            remaining_tokens=runner.remaining_tokens(),
            protected_after_author=protected_after_author,
            allowance=allowance,
        )
        if allowance < 1000:
            raise StopResearch("limit_reached_partial", "draft correction exceeds author allowance")
        if revision or attempt:
            _admit_author_time(runner, campaign, revision=revision, correction=bool(attempt))
        parent.state = "running"
        runner.session.commit()
        allocation = runner.send(handle, parent, operation, allowance, payload)
        raw = runner.wait_parent(handle, parent, allocation, "draft")
        parent.report = {**parent.report, operation: raw}
        parent.provenance = {**parent.provenance, "draft_attempts": [
            *parent.provenance.get("draft_attempts", []), {
                "operation": operation, "attempt": attempt, "span_id": allocation["span_id"],
                "model_thread_id": parent.provenance.get("draft_model", {}).get("codex_thread_id"),
                "length_precheck": parent.provenance.get("draft_model", {}).get("length_precheck"),
                "draft_sha256": stable_hash(raw), "draft": raw,
            }]}
        try:
            if payload.get("recovery_claim_ids") and {
                claim.get("id") for claim in raw.get("claims", [])
            } != set(payload["recovery_claim_ids"]):
                raise quality.DraftValidationError([{
                    "code": "recovery_inventory", "path": "/claims",
                    "message": "The repaired inventory must declare every retained required claim ID.",
                }])
            draft, digest = quality.apply_draft(
                runner.session, runner.task, manuscript, campaign, raw, parent.id,
                expected_response_ids=payload["expected_response_ids"])
        except quality.DraftValidationError as exc:
            quality.update_campaign(campaign, rejected_drafts=[
                *campaign.body.get("rejected_drafts", []), {
                    "agent_id": parent.id, "operation": operation, "attempt": attempt,
                    "span_id": allocation["span_id"], "draft_sha256": stable_hash(raw),
                    "issues": exc.issues,
                }])
            research_trace.record(runner, "draft_rejected", agent=parent,
                                  span_id=allocation["span_id"], issues=exc.issues)
            runner.session.commit()
            if attempt:
                raise StopResearch("failed_partial",
                    "author draft still invalid after one bounded correction; evidence retained") from None
            payload = {**payload, "draft_corrections": exc.issues,
                       "original_draft": raw, "original_draft_sha256": stable_hash(raw)}
        else:
            break
    _restore_responses(runner, parent, campaign, draft, digest)
    runner.author_checkpoint = None
    runner.recoverable_author_return = None
    return digest


def _restore_responses(runner, parent, campaign, draft, digest):
    """Finish the accepted-draft checkpoint if a crash preceded its response events."""
    comments = {c["id"]: c for c in _prior(runner.session, campaign)}
    for response in draft["responses"]:
        comment = comments[response["comment_id"]]
        recorded = comment.get("response")
        if recorded and all(recorded.get(key) == value for key, value in {
            "author": parent.id, "response": response["response"],
            "changes": response["changes"], "candidate_hash": digest,
        }.items()):
            continue
        revision_review.respond(
            runner.session,
            comment["round_id"],
            comment_id=comment["id"],
            author=parent.id,
            response=response["response"],
            changes=response["changes"],
        )
    runner.session.commit()


def _report_correction_payload(child, packet, issues):
    original = child.provenance["report_attempts"][-1]
    return {"packet": packet, "report_corrections": issues,
            "original_report": original["report"],
            "original_report_sha256": original["report_sha256"]}


def _correction_grants(corrections, available, target):
    from ..providers.research_codex_worker import json_prompt, prompt_token_count

    minimums = []
    for child, _handle, packet, issues in corrections:
        payload = _report_correction_payload(child, packet, issues)
        input_tokens = prompt_token_count(json_prompt("audit", payload))
        output = prompt_token_count(json.dumps(payload["original_report"], ensure_ascii=False))
        # Repairs return the same report shape. Protect measured output plus a
        # 25% margin, rather than applying a large uniform floor to tiny reports.
        minimums.append(input_tokens + max(1000, (output * 5 + 3) // 4) + 400)
    required = sum(minimums)
    if required > available:
        raise StopResearch("limit_reached_partial",
                           f"report correction capacity requires {required} tokens; "
                           f"{available} available; retained reports were not re-dispatched")
    pool = max(required, min(target, available))
    extra, remainder = divmod(pool - required, len(minimums))
    return [minimum + extra + (index < remainder) for index, minimum in enumerate(minimums)]


def _closure_phase(runner, parent, manuscript, campaign, digest, phase):
    """One charged call per phase; invalid returns are retained and never retried."""
    if not closure.enabled(runner.task):
        return None
    previous = campaign.body.get("closure_calls", [])
    records = campaign.body.get("closure_reports", [])
    if phase == "confirmation" and len(records) == 2:
        state = quality.assessment(runner.session, manuscript.id)
        if state["closure"]["status"] in {"ready_for_human_review",
                                           "ready_for_human_review_with_advisories"}:
            return records[-1]
        raise StopResearch("failed_partial", "saved editorial confirmation is stale or invalid")
    if len(previous) >= (1 if phase == "preflight" else 2):
        raise StopResearch("limit_reached_partial", "editorial closure call limit reached")
    if phase == "preflight":
        scope = closure.scope_for(runner.task)
        quality.update_campaign(campaign, closure_scope=scope)
        plan = _revision_budget(runner, campaign)
        if runner.remaining_tokens() < plan["required_remaining_tokens"] + CLOSURE_CALL_RESERVE:
            raise StopResearch("limit_reached_partial", "full editorial and specialist path is unfunded")
    protected = FINAL_HANDOFF_RESERVE + (CLOSURE_CALL_RESERVE if phase == "preflight" else 0)
    if runner.remaining_tokens() < CLOSURE_CALL_RESERVE + protected:
        raise StopResearch("limit_reached_partial", "editorial closure grant and follow-through unavailable")
    remaining_time = runner.research_deadline - time.monotonic()
    if remaining_time < (180 if phase == "preflight" else 60):
        raise StopResearch("limit_reached_partial", "editorial closure time reserve unavailable")
    agent = runner.new_agent("child", {"role": "editorial_closure", "phase": phase,
                                       "candidate_sha256": digest}, parent)
    packet = closure.packet_for(runner.task, campaign, digest, agent.id, phase, session=runner.session,
        specialist_records=[{"agent_id": r["agent_id"], "role": r["role"],
                             "candidate_sha256": r["candidate_sha256"],
                             "report_sha256": r["report_sha256"], "blockers": r["blockers"]}
                            for r in campaign.body["reports"][-len(SPECIALIST_ROLES):]]
        if phase == "confirmation" else [])
    agent.assignment = {**agent.assignment, "packet_sha256": packet["packet_sha256"]}
    handle = runner.spawn(agent)
    quality.update_campaign(campaign, closure_calls=[*previous, {"phase": phase,
        "agent_id": agent.id, "candidate_sha256": digest, "packet_sha256": packet["packet_sha256"]}])
    runner.session.commit()
    try:
        allocation = runner.send(handle, agent, "closure", CLOSURE_CALL_RESERVE, {"packet": packet})
        raw = runner.wait_parent(handle, agent, allocation, "closure_report")
        identity = (agent.provenance.get("closure_report_model", {}).get("codex_thread_id")
                    if runner.task.contract["executor"] != "offline" else agent.id)
        authors = [runner.session.get(ResearchAgent, d["author_id"])
                   for d in campaign.body["drafts"]]
        forbidden = set().union(*(quality.author_model_threads(a) for a in authors if a))
        forbidden.update(a.provenance.get("specialist_report_model", {}).get("codex_thread_id")
                         for a in runner.agents if a.id != agent.id)
        state = quality.assessment(runner.session, manuscript.id) if phase == "confirmation" else {}
        artifacts_verified = all(row.get("status") == "available" for row in
            json.loads(packet["evidence_files"]["evidence/verification/index.json"]))
        decision = closure.evaluate(raw, packet, assigned_reviewer_id=agent.id,
            reviewer_thread_id=identity, writer_thread_ids=forbidden,
            specialists_current=state.get("specialist_checks_complete", False),
            artifacts_verified=artifacts_verified)
        record = {"phase": phase, "agent_id": agent.id, "candidate_sha256": digest,
                  "packet_sha256": packet["packet_sha256"], "scope_sha256": packet["scope_sha256"],
                  "evidence_manifest_sha256": packet["evidence_manifest_sha256"],
                  "report": raw, "report_sha256": stable_hash(raw),
                  "status": decision["status"], "reasons": decision["reasons"],
                  "allocation_span_id": allocation["span_id"], "reviewer_thread_id": identity}
        quality.update_campaign(campaign, closure_reports=[*campaign.body.get("closure_reports", []), record])
        agent.report, agent.state = raw, "completed"
        runner.session.commit()
        if decision["status"] in {"invalid_report", "stale_report"}:
            raise StopResearch("failed_partial", "editorial closure report was invalid; evidence retained")
        return record
    finally:
        handle.close()
        research_trace.record(runner, "worker_closed", agent=agent, pid=handle.pid)


def _audit_wave(runner, parent, manuscript, campaign, digest, iteration):
    pending, results = [], []
    # Accepted reports are committed individually, so interrupted waves can fill only missing roles.
    saved = [r for r in campaign.body["reports"]
             if r["candidate_sha256"] == digest and r["iteration"] == iteration]
    for record in saved:
        child = next(a for a in runner.agents if a.id == record["agent_id"])
        report, blockers, _flags = quality.validate_report(child.report, record["packet"])
        results.append((child, report, blockers))
    accepted_roles = {r["role"] for r in saved}
    pending.extend(retained_reviews(runner, campaign, digest, iteration, accepted_roles))
    remaining_roles = [role for role in SPECIALIST_ROLES if role not in accepted_roles]
    approved = getattr(runner.task, "ledger", {}).get("continuation", {}).get("normalization_approvals", {})
    available_sources = {stable_hash(handle.event["result"])
                         for _child, handle, _allocation, _packet in pending
                         if isinstance(handle, ReplayHandle)} | {
        row["normalization"]["source_report_sha256"] for row in saved if row.get("normalization")}
    if approved and (remaining_roles or set(approved) != available_sources):
        raise StopResearch("failed_partial",
                           "approved normalization returns missing; no fresh audit dispatched")
    role_count = max(1, len(remaining_roles))
    corrections, rejected, attempts = [], [], {}
    # Complete specialist review has priority over optional later revisions/synthesis.
    # The original sixth-of-task slice rejected an observed 19,555-token review
    # despite ample unallocated task capacity. All review grants share one ledger.
    tokens = min(runner.task.contract["token_limit"] // 4,
                 (runner.remaining_tokens() - _protected_reserve(runner)) // role_count)
    if remaining_roles and tokens < 1000:
        raise StopResearch("limit_reached_partial", "insufficient allowance for all specialist reviewers")
    budget = _revision_budget(runner, campaign)
    review_reserve = sum(budget["review_role_reserves"][role] for role in remaining_roles)
    # Initial reviews have priority; protect the available repair pool without
    # lowering forecasted review grants merely to fill an unfunded repair target.
    repair_reserve = min(budget["repair_reserve"], max(0,
        runner.remaining_tokens() - _protected_reserve(runner) - review_reserve))
    if (remaining_roles and not iteration and runner.remaining_tokens()
            >= _protected_reserve(runner) + 20000 * role_count + 1000):
        repair_reserve = max(1000, repair_reserve)
    tokens = min(runner.task.contract["token_limit"] // 4,
        (runner.remaining_tokens() - _protected_reserve(runner) - repair_reserve) // role_count)
    role_grants = {role: min(tokens, budget["review_role_reserves"][role]) for role in remaining_roles}
    repair_allocations = []
    if iteration and remaining_roles:
        repair_reserve = budget["repair_reserve"]
        spare = (runner.remaining_tokens() - _protected_reserve(runner)
                 - review_reserve - budget["repair_reserve"])
        if spare < 0:
            raise StopResearch("limit_reached_partial",
                               "observed specialist re-review reservation unavailable")
        # Keep the larger observed role's grant instead of averaging away its reservation.
        role_grants = {role: budget["review_role_reserves"][role]
                       for role in remaining_roles}
    plan = {"iteration": iteration, "remaining_tokens": runner.remaining_tokens(),
            "review_role_grants": role_grants, "repair_reserve": repair_reserve,
            "repair_forecast": budget["repair_reserve"], "handoff_reserve": _protected_reserve(runner)}
    quality.update_campaign(campaign, audit_budget_plans=[
        *campaign.body.get("audit_budget_plans", []), plan])
    research_trace.record(runner, "audit_budget_planned", **plan)
    runner.task.state, parent.state = "researching", "waiting_for_specialists"
    runner.session.commit()

    def dispatch(role, grant):
        packet = quality.packet_for(
            runner.task, campaign, digest, role, _prior(runner.session, campaign, role)
        )
        child = runner.new_agent(
            "child",
            {
                "specialist_role": role,
                "iteration": iteration,
                "candidate_sha256": digest,
                "packet_sha256": packet["packet_sha256"],
                "source_ids": [s["source_id"] for s in runner.task.sources if s.get("source_id")],
            },
            parent,
        )
        handle = runner.spawn(child)
        policy = packet.get("operator_model_policy")
        if policy and handle.requested_model_policy != {"role": role, **policy}:
            handle.close()
            raise StopResearch("failed_partial",
                "reviewer policy mismatch denied before model dispatch")
        quality.update_campaign(campaign, dispatches=[*campaign.body.get("dispatches", []),
            {"agent_id": child.id, "iteration": iteration, "packet": packet}])
        runner.session.commit()
        allocation = runner.send(handle, child, "audit", grant, {"packet": packet})
        pending.append((child, handle, allocation, packet))

    # Both waves use at most three workers. A completed/closed worker releases a
    # slot; waiting correction workers occupy slots until their repair finishes.
    # Deferred roles keep their token grants and can start before other roles finish.
    concurrent = 3
    deferred = list(remaining_roles[concurrent:])
    abort_deadline = None
    for role in remaining_roles[:concurrent]:
        dispatch(role, role_grants[role])
    while pending or corrections or deferred:
        runner.check()
        if rejected:
            corrections, deferred = [], []
            if abort_deadline is None:
                abort_deadline = min(runner.research_deadline, time.monotonic() + 10)
            if time.monotonic() >= abort_deadline:
                break
        if not pending and not corrections and not deferred:
            break
        if (deferred and not corrections and len(pending) < concurrent
                and not any(attempts.get(child.id, 0) for child, _, _, _ in pending)):
            if rejected:
                break
            role = deferred.pop(0)
            remaining_repair = max(0, repair_reserve - sum(
                allocation_charge(a) for a in repair_allocations))
            grant = (runner.remaining_tokens() - _protected_reserve(runner) - remaining_repair
                     - sum(role_grants[r] for r in deferred))
            if grant < role_grants[role]:
                raise StopResearch("limit_reached_partial", "deferred specialist reservation unavailable")
            grant = role_grants[role]
            dispatch(role, grant)
        if not pending:
            # Gather the whole wave's defects first. Each existing specialist may
            # correct its report once, using the original deadline and ledger.
            repair_reserve = min(budget["repair_reserve"], max(0,
                runner.remaining_tokens() - _protected_reserve(runner)
                - sum(role_grants[role] for role in deferred)))
            if campaign.body["drafts"][-1].get("local_revision") and corrections and (
                    len(corrections) + len(repair_allocations) > runner.task.ledger.get(
                        "continuation", {}).get("max_report_corrections", 1)):
                raise StopResearch("limit_reached_partial",
                    "local review permits only one shared format correction by default; "
                    "operator correction limit reached")
            grants = _correction_grants(corrections,
                max(0, runner.remaining_tokens() - _protected_reserve(runner)
                    - sum(role_grants[role] for role in deferred)),
                (max(0, runner.remaining_tokens() - _protected_reserve(runner)
                     - sum(role_grants[role] for role in deferred))
                 if campaign.body["drafts"][-1].get("local_revision") else
                 max(0, repair_reserve - sum(allocation_charge(a) for a in repair_allocations))))
            for (child, handle, packet, issues), tokens in zip(corrections, grants, strict=True):
                attempts[child.id] = 1
                child.state = "running"
                if isinstance(handle, ReplayHandle):
                    # Replay is read-only; a correction needs a new live worker,
                    # not a send to the exhausted in-memory saved-return handle.
                    handle.close()
                    handle = runner.spawn(child)
                allocation = runner.send(handle, child, "audit", tokens,
                                         _report_correction_payload(child, packet, issues))
                repair_allocations.append(allocation)
                pending.append((child, handle, allocation, packet))
            corrections = []
        for child, handle, allocation, packet in list(pending):
            try:
                raw = runner.event(handle, child, allocation, "specialist_report")
            except (ExecutorError, StopResearch) as exc:
                if isinstance(exc, StopResearch) and exc.scope != "call":
                    raise
                rejected.append(child.id)
                child.state = "failed"
                handle.close()
                pending.remove((child, handle, allocation, packet))
                research_trace.record(runner, "worker_closed", agent=child, pid=handle.pid)
                runner.session.commit()
                continue
            if raw is None:
                continue
            child.provenance = {**child.provenance, "original_return": raw,
                "report_attempts": [*child.provenance.get("report_attempts", []), {
                    "attempt": attempts.get(child.id, 0), "report": raw,
                    "span_id": allocation["span_id"],
                    "report_sha256": stable_hash(raw), "packet_sha256": packet["packet_sha256"],
                }]}
            runner.session.commit()
            normalized, normalization = normalize_review_report(raw, normalization_authority(runner.task))
            try:
                report, blockers, flags = quality.validate_report(normalized, packet)
            except quality.ReportValidationError as exc:
                child.state = "report_needs_correction"
                quality.update_campaign(campaign, rejected_reports=[
                    *campaign.body.get("rejected_reports", []), {
                        "agent_id": child.id, "iteration": iteration,
                        "span_id": allocation["span_id"],
                        "attempt": attempts.get(child.id, 0), "report_sha256": stable_hash(raw),
                        "packet_sha256": packet["packet_sha256"], "issues": exc.issues,
                    }])
                research_trace.record(runner, "report_rejected", agent=child,
                    span_id=allocation["span_id"], issues=exc.issues)
                pending.remove((child, handle, allocation, packet))
                if attempts.get(child.id, 0) == 0:
                    corrections.append((child, handle, packet, exc.issues))
                else:
                    rejected.append(child.id)
                    child.state = "failed"
                    handle.close()
                    research_trace.record(runner, "worker_closed", agent=child, pid=handle.pid)
                runner.session.commit()
                continue
            # Worker identities are obtained from the executor, never from reviewer prose.
            identity = child.provenance.get("specialist_report_model", {}).get("codex_thread_id")
            author_threads = set().union(*(quality.author_model_threads(a)
                                          for a in runner.agents if a.role == "parent"))
            other_threads = {
                a.provenance.get("specialist_report_model", {}).get("codex_thread_id")
                for a in runner.agents
                if a.role == "child" and a.id != child.id
            }
            if identity and (identity in author_threads or identity in other_threads):
                raise ValueError("specialist reused an author or reviewer thread")
            child.report, child.state = report, "completed"
            child.provenance = {**child.provenance, "report_hash": stable_hash(report)}
            if normalization:
                child.provenance = {**child.provenance, "review_normalization": normalization}
                research_trace.record(runner, "review_normalized", agent=child, **normalization)
            for resolution in report["resolutions"]:
                comment = next(c for c in packet["prior_comments"] if c["id"] == resolution["comment_id"])
                review = runner.session.get(ResearchObject, comment["round_id"])
                original = next(c for c in review.body["comments"] if c["id"] == comment["id"])
                revision_review.verify(
                    runner.session,
                    review.id,
                    verifier=child.id,
                    response_hash=stable_hash(comment["response"]),
                    expected_candidate_hash=digest,
                    expected_comment_hash=stable_hash(original),
                    **resolution,
                )
            record = {
                "validation_version": "manuscript-recovery-v2",
                "agent_id": child.id,
                "role": report["role"],
                "iteration": iteration,
                "candidate_sha256": digest,
                "packet": packet,
                "report_sha256": stable_hash(report),
                "blockers": blockers,
                **({"normalization": normalization} if normalization else {}),
                **flags,
            }
            quality.update_campaign(campaign, reports=[*campaign.body["reports"], record])
            runner.session.commit()
            results.append((child, report, blockers))
            handle.close()
            research_trace.record(runner, "worker_closed", agent=child, pid=handle.pid)
            pending.remove((child, handle, allocation, packet))
        time.sleep(0.02)
    if rejected:
        raise StopResearch("failed_partial",
            f"{len(rejected)} specialist report(s) still invalid after one bounded correction; "
            "evidence retained")
    current_records = [r for r in campaign.body["reports"]
                       if r["candidate_sha256"] == digest and r["iteration"] == iteration]
    manifests = [
        {
            "role": f"{rec['role']}-{iteration}",
            "packet_sha256": rec["packet"]["packet_sha256"],
            "evidence_artifacts": rec["packet"]["evidence_artifacts"],
        }
        for rec in current_records
    ]
    unique_manifests = {(m["role"], m["packet_sha256"]): m
                        for m in [*campaign.body["packets"], *manifests]}
    quality.update_campaign(campaign, packets=list(unique_manifests.values()))
    comments = []
    for child, report, blockers in results:
        issues = [
            (o["objection"], o["acceptance_criterion"])
            for o in report["objections"]
            if o["severity"] == "blocking"
        ]
        named = {text for text, _ in issues}
        issues += [
            (b, "Resolve the recorded evidence/coverage problem within its exact scope.")
            for b in blockers
            if b not in named
        ]
        for index, (objection, criterion) in enumerate(issues):
            comments.append(
                {
                    "id": f"{SPECIALIST_ROLES.index(report['role'])}-{iteration}-{index}",
                    "specialist_role": report["role"],
                    "agent_id": child.id,
                    "objection": objection,
                    "acceptance_criterion": criterion,
                }
            )
    if len(comments) > MAX_REVISION_COMMENTS:
        raise StopResearch("failed_partial",
            f"specialist wave produced {len(comments)} revision comments; "
            f"capacity is {MAX_REVISION_COMMENTS}; all reports retained")
    if comments:
        review = next((r for rid in campaign.body["rounds"]
                       if (r := runner.session.get(ResearchObject, rid)).body["candidate_hash"] == digest
                       and r.body["comments"] == comments), None)
        if review is None:
            review = revision_review.open_round(
                runner.session, manuscript.id, comments=comments, reviewer="specialist-controller")
            quality.update_campaign(campaign, rounds=[*campaign.body["rounds"], review.id])
    if not comments:
        from .manuscript_local_revision import verify_controller_completion
        verified = verify_controller_completion(runner.session, runner.task, campaign, digest)
        if verified:
            research_trace.record(runner, "controller_completion_verified",
                                  candidate_sha256=digest, comment_ids=verified)
    all_resolved = all(
        d in {"resolved", "justified_rejection"}
        for rid in campaign.body["rounds"]
        for d in revision_review.dispositions(
            runner.session, runner.session.get(ResearchObject, rid)
        ).values()
    )
    quality.update_campaign(
        campaign, status="agent_checks_complete" if not comments and all_resolved else "needs_revision"
    )
    runner.session.commit()
    return not comments and all_resolved


def _save_handoff(runner, manuscript, campaign):
    state = quality.assessment(runner.session, manuscript.id)
    draft = campaign.body["drafts"][-1]["candidate"] if campaign.body["drafts"] else None
    runner.task.synthesis = {
        **runner.task.synthesis,
        "summary": "Manuscript draft and specialist assessments retained for human review.",
        "report_ids": [r["agent_id"] for r in campaign.body["reports"]],
        "agreements": [],
        "conflicts": state["blockers"],
        "unresolved_questions": state["blockers"],
        "deliverables": {
            "paper": quality.draft_text(draft) if draft else "No complete draft returned.",
            "research_report": quality.report_text(state),
            "reviewer_report": quality.report_text(campaign.body["reports"]),
        },
        "integration": runner.task.synthesis.get("integration", "controller_preserved_reviewed_candidate"),
        "review_required": True,
        "quality": state,
        "manuscript_id": manuscript.id,
    }
    runner.session.commit()


def _integration_payload(task, campaign, agents):
    """Give the author the review decisions; original reports remain immutable evidence."""
    latest = campaign.body["reports"][-len(SPECIALIST_ROLES):]
    by_id = {a.id: a for a in agents}
    candidate = campaign.body["drafts"][-1]["candidate"]
    reports = {}
    for record in latest:
        agent = by_id[record["agent_id"]]
        report = agent.report
        reports[agent.id] = {
            "role": record["role"],
            "sha256": record["report_sha256"],
            "packet_sha256": record["packet"]["packet_sha256"],
            "summary": report["summary"],
            "contribution_comparison": report["contribution_comparison"],
            "claim_assessments": [
                {"claim_id": row["claim_id"], "status": row["status"]}
                for row in report["assessments"]
            ],
            "objections": report["objections"],
            "resolutions": report["resolutions"],
            "coverage_flags": report["coverage_flags"],
            "adversarial_checks": report.get("adversarial_checks", []),
            "blockers": record["blockers"],
            "review_flags": record["review_flags"],
        }
    return {
        "contract": {
            "question": task.contract["question"],
            "paper_type": task.contract["paper_type"],
            "success_criteria": task.contract["success_criteria"],
            "deliverables": ["research_report", "reviewer_report"],
        },
        "reports": reports,
        "reviewed_candidate": {
            "title": candidate["title"],
            "candidate_sha256": latest[0]["candidate_sha256"],
            "section_ids": [s["id"] for s in candidate["sections"]],
            "claim_ids": [c["id"] for c in candidate["claims"]],
            "limitations": candidate["limitations"],
        },
    }


def execute(runner):
    task, session = runner.task, runner.session
    continuation = task.ledger.get("continuation")
    if continuation:
        from .manuscript_continuation import checkpoint
        from .research_tasks import agents_for

        current = checkpoint(session, task, active=True)
        if current["saved_work_sha256"] != continuation["saved_work_sha256"]:
            raise ValueError("continuation evidence changed before execution")
        manuscript = session.get(ResearchObject, continuation["manuscript_id"])
        campaign = session.get(ResearchObject, continuation["campaign_id"])
        runner.agents = agents_for(session, task.id)
        runner.author_checkpoint = continuation["checkpoint_sha256"]
    else:
        manuscript, campaign = quality.create_campaign(session, task)
    research_trace.record(
        runner, "campaign_started", manuscript_id=manuscript.id, required_roles=list(SPECIALIST_ROLES)
    )
    parent = handle = None
    try:
        if continuation:
            parent = next(a for a in runner.agents if a.id == continuation["author_id"])
            if continuation["stage"] == "correct":
                from .manuscript_continuation import recoverable_return

                runner.recoverable_author_return = recoverable_return(parent, campaign, task)
                if (not runner.recoverable_author_return
                        or runner.recoverable_author_return["result_sha256"]
                        != continuation["recoverable_return_sha256"]):
                    raise ValueError("retained author return changed before recovery")
            draft = campaign.body["drafts"][-1]
            _restore_responses(runner, parent, campaign, draft["candidate"], draft["candidate_sha256"])
        else:
            manuscript_acquisition.collect(runner, manuscript, campaign)
            parent = runner.new_agent("parent", {"question": task.contract["question"], "role": "author"})
        local_review_only = bool(campaign.body["drafts"]
                                 and campaign.body["drafts"][-1].get("local_revision"))
        if local_review_only:
            policy = task.ledger.get("continuation", {}).get("specialist_policy", {})
            if policy:
                runner.executor.role_policy.update(policy)
                runner.executor.worker_config["WB_RESEARCH_CODEX_ROLE_POLICY"] = json.dumps(
                    runner.executor.role_policy)
                research_trace.record(runner, "operator_specialist_policy_bound", policy=policy)
        handle = None if local_review_only else runner.spawn(parent)
        # Future review cannot be borrowed by the author, even after unused allowances are released.
        initial_budget = _revision_budget(runner)
        reserve = (len(SPECIALIST_ROLES) * (
                       initial_budget["input_token_estimate"]
                       + initial_budget["review_output_headroom"]
                   )
                   + initial_budget["repair_reserve"] + _protected_reserve(runner))
        if closure.enabled(task):
            reserve += CLOSURE_CALL_RESERVE + 12000
        draft_allowance = min(task.contract["token_limit"] // 3, runner.remaining_tokens() - reserve)
        if continuation:
            digest = campaign.body["drafts"][-1]["candidate_sha256"]
            if continuation["stage"] == "correct":
                raw = runner.recoverable_author_return["result"]
                expected_ids = sorted(c["id"] for c in _prior(runner.session, campaign))
                try:
                    quality.validate_draft(task, campaign, raw, expected_response_ids=expected_ids)
                except quality.DraftValidationError:
                    pass
                else:
                    draft, digest = quality.apply_draft(session, task, manuscript, campaign, raw, parent.id,
                                                       expected_response_ids=expected_ids)
                    _restore_responses(runner, parent, campaign, draft, digest)
                    runner.recoverable_author_return = None
                    runner.author_checkpoint = None
            if continuation["stage"] == "correct" and runner.recoverable_author_return:
                budget = _revision_budget(runner, campaign)
                if budget["author_grant"] < budget["minimum_author_grant"]:
                    raise StopResearch("limit_reached_partial",
                                       "retained-return correction cycle is not funded")
                digest = _author(runner, parent, handle, manuscript, campaign, budget["author_grant"],
                    revision=True, protected_after_author=(
                        budget["review_reserve"] + budget["repair_reserve"] + budget["handoff_reserve"]))
        else:
            digest = _author(
                runner, parent, handle, manuscript, campaign, draft_allowance,
                protected_after_author=reserve,
            )
        if closure.enabled(task):
            records = campaign.body.get("closure_reports", [])
            preflight = records[0] if records else _closure_phase(
                runner, parent, manuscript, campaign, digest, "preflight")
            if records:
                reviewer = session.get(ResearchAgent, preflight["agent_id"])
                if (not reviewer or reviewer.deleted_at or reviewer.task_id != task.id
                        or reviewer.assignment.get("phase") != "preflight"
                        or stable_hash(reviewer.report) != preflight["report_sha256"]
                        or stable_hash(preflight["report"]) != preflight["report_sha256"]
                        or reviewer.assignment.get("packet_sha256") != preflight["packet_sha256"]):
                    raise StopResearch("failed_partial", "saved editorial preflight changed")
            if preflight["status"] not in {"preflight_complete", "needs_revision"}:
                raise StopResearch("failed_partial", "saved editorial preflight is invalid")
            if preflight["status"] == "needs_revision" and not campaign.body.get("closure_repair"):
                if local_review_only or task.contract["max_revision_cycles"] == 0:
                    raise StopResearch("limit_reached_partial",
                                       "editorial repair requires authorized revision")
                if runner.research_deadline - time.monotonic() < 300:
                    raise StopResearch("limit_reached_partial",
                                       "editorial repair and specialist time reserve unavailable")
                budget = _revision_budget(runner, campaign)
                if budget["capacity_status"] != "funded":
                    raise StopResearch(
                        "limit_reached_partial", "editorial repair and specialist wave are unfunded"
                    )
                before = digest
                digest = _author(runner, parent, handle, manuscript, campaign,
                                 budget["author_grant"], revision=True, protected_after_author=(
                                     budget["review_reserve"] + budget["repair_reserve"]
                                     + budget["handoff_reserve"]))
                quality.update_campaign(campaign, closure_repair={
                    "author_id": parent.id, "base_candidate_sha256": before,
                    "candidate_sha256": digest,
                    "finding_ids": [f["id"] for f in preflight["report"]["findings"]
                                    if f["category"] != "optional_improvement"
                                    and f["disposition"] in {"open", "deferred"}],
                })
                runner.session.commit()
        plan = _initial_capacity_plan(runner, campaign)
        quality.update_campaign(campaign, initial_capacity_plans=[
            *campaign.body.get("initial_capacity_plans", []), plan])
        research_trace.record(runner, "initial_capacity_planned", **plan)
        session.commit()
        completed = bool(continuation and continuation["stage"] == "integrate")
        previous_failure = None
        cycle_limit = (0 if continuation and continuation["stage"] == "correct"
                       else task.contract["max_revision_cycles"])
        for iteration in range(cycle_limit + 1):
            if completed:
                break
            if not (continuation and iteration == 0 and continuation["stage"] == "revise"):
                completed = _audit_wave(
                    runner, parent, manuscript, campaign, digest, len(campaign.body["drafts"]) - 1
                )
            _save_handoff(runner, manuscript, campaign)
            if completed:
                break
            candidate = campaign.body["drafts"][-1]["candidate"]
            failure = stable_hash(
                {
                    "candidate": {k: v for k, v in candidate.items() if k != "responses"},
                    "issues": sorted(
                        b for r in campaign.body["reports"][-len(SPECIALIST_ROLES) :] for b in r["blockers"]
                    ),
                }
            )
            if failure == previous_failure:
                break
            previous_failure = failure
            if iteration == cycle_limit:
                break
            # Original deadline and ledger apply to every revision; no fresh task grant.
            budget = _revision_budget(runner, campaign)
            quality.update_campaign(campaign, revision_budget_plans=[
                *campaign.body.get("revision_budget_plans", []), {"iteration": iteration, **budget}])
            research_trace.record(runner, "revision_budget_planned", **budget)
            session.commit()
            allowance = budget["author_grant"]
            if allowance < budget["minimum_author_grant"]:
                raise StopResearch("limit_reached_partial",
                    f"revision needs at least {budget['minimum_author_grant']} tokens after reserving "
                    f"{budget['review_reserve']} for specialist re-review and "
                    f"{budget['handoff_reserve']} for final handoff and "
                    f"{budget['repair_reserve']} for repair; {budget['remaining_tokens']} remain")
            digest = _author(
                runner, parent, handle, manuscript, campaign, allowance, revision=True,
                protected_after_author=(
                    budget["review_reserve"] + budget["handoff_reserve"]
                    + budget["repair_reserve"]
                ),
            )
            if closure.enabled(task) and campaign.body.get("closure_repair"):
                repair = campaign.body["closure_repair"]
                quality.update_campaign(campaign, closure_repair={**repair,
                    "candidate_sha256": digest,
                    "successor_candidate_sha256": [
                        *repair.get("successor_candidate_sha256", []), digest]})
                session.commit()
        _save_handoff(runner, manuscript, campaign)
        if completed and closure.enabled(task):
            confirmation = _closure_phase(runner, parent, manuscript, campaign, digest, "confirmation")
            if confirmation["status"] not in {"ready_for_human_review",
                                              "ready_for_human_review_with_advisories"}:
                completed = False
                quality.update_campaign(campaign, status="needs_revision")
                runner.session.commit()
                _save_handoff(runner, manuscript, campaign)
        # A final summary has a safety margin for best-effort usage telemetry.
        # The complete candidate/reports stay in the evidence graph, not repeated
        # in the parent's final message context.
        final_allowance = min(FINAL_HANDOFF_RESERVE, runner.remaining_tokens() - 1000)
        if completed and local_review_only:
            payload = _integration_payload(task, campaign, runner.agents)
            task.synthesis = {**task.synthesis,
                "integration": "controller_no_model_review_handoff",
                "controller_handoff_receipt": {"candidate_sha256": digest,
                    "report_hashes": {key: row["sha256"]
                                      for key, row in payload["reports"].items()},
                    "worker_calls": 0, "human_publication_approval": False}}
            task.ledger = {**task.ledger, "parent_integration_received": True,
                "child_handoff_received": True, "live_handoff_verified": True}
        elif completed and final_allowance >= 6000:
            payload = _integration_payload(task, campaign, runner.agents)
            reports = payload["reports"]
            allocation = runner.send(handle, parent, "integrate", final_allowance, payload)
            raw = runner.wait_parent(handle, parent, allocation, "synthesis")
            final = Synthesis.model_validate(raw).model_dump()
            if set(final["report_ids"]) != set(reports) or "paper" in final["deliverables"]:
                raise ValueError("handoff must cite all specialists and preserve reviewed prose")
            parent.report = {**parent.report, "synthesis": final}
            task.synthesis = {
                **task.synthesis,
                "parent_summary": final,
                "integration": "parent_agent_with_immutable_reviewed_candidate",
            }
            task.ledger = {
                **task.ledger,
                "parent_integration_received": True,
                "child_handoff_received": True,
                "live_handoff_verified": task.contract["executor"] != "offline",
            }
        parent.state = "completed"
        runner.reason = "Specialist campaign stopped; " + (
            "agent checks complete, human review remains required."
            if completed
            else "unresolved evidence or revision-limit blockers retained."
        )
        session.commit()
    finally:
        # Preserve every successful draft and original report on failure or cancellation.
        _save_handoff(runner, manuscript, campaign)
        research_trace.record(runner, "campaign_handoff", manuscript_id=manuscript.id)
