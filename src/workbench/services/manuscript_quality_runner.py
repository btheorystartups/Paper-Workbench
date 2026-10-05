"""Bounded specialist manuscript production using the existing Runner and review ledger."""

import json
import time
from types import SimpleNamespace

from ..models import ResearchObject, stable_hash
from ..research_contract import MANUSCRIPT_HANDOFF_TOKEN_RESERVE, SPECIALIST_ROLES, Synthesis
from . import manuscript_acquisition, research_trace, revision_review
from . import manuscript_quality as quality
from .research_runner import StopResearch, allocation_charge

FINAL_HANDOFF_RESERVE = MANUSCRIPT_HANDOFF_TOKEN_RESERVE


def _cycle_timing(runner):
    calls = research_trace.summary(getattr(runner.task, "ledger", {}).get("call_trace", []))["calls"]
    kinds = {a.get("span_id"): a.get("operation_kind") for a in runner.allocations}
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
    events = getattr(runner.task, "ledger", {}).get("call_trace", [])
    starts = {e["span_id"]: e["elapsed_seconds"] for e in events if e["event"] == "spawn_started"}
    spawns = [max(0, e["elapsed_seconds"] - starts[e["span_id"]]) for e in events
              if e["event"] == "spawn_finished" and e["span_id"] in starts]
    startup = max(5.0, 4 * max(spawns, default=0) * 1.25)
    author_repair = max([author, *author_repairs]) if author is not None else None
    report_repair = (
        max(report_repairs, default=max(durations.values(), default=0)) if review is not None else None
    )
    required = (1.25 * (cycle + author_repair + report_repair) + startup) if cycle is not None else None
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
    if campaign and campaign.body.get("drafts"):
        digest = campaign.body["drafts"][-1]["candidate_sha256"]
        prompts, repair_prompts = [], []
        for role in SPECIALIST_ROLES:
            packet = quality.packet_for(
                runner.task, campaign, digest, role, _prior(runner.session, campaign, role))
            prompts.append(json_prompt("audit", {"packet": packet}))
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
        author_input_tokens = prompt_token_count(json_prompt(
            "revise", _author_payload(runner, campaign, revision=True)))
    floor = max(20000, input_tokens + 6000)
    repair_reserve = max(20000, repair_input_tokens + 6000)
    review_usage = dict.fromkeys(SPECIALIST_ROLES, floor)
    observed_reviews = {}
    author_usage = 0
    seen_audits = set()
    roles = {a.id: a.assignment.get("specialist_role") for a in runner.agents}
    for allocation in runner.allocations:
        if not allocation.get("final_actual"):
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
            repair_reserve = max(repair_reserve, (observed * 5 + 3) // 4)
            continue
        if allocation["phase"] == "audit" and roles.get(allocation["agent_id"]) in review_usage:
            role = roles[allocation["agent_id"]]
            observed_reviews[role] = max(observed_reviews.get(role, 0), (observed * 5 + 3) // 4)
        elif allocation["phase"] in {"draft", "revise"}:
            author_usage = max(author_usage, (observed * 5 + 3) // 4)
    review_usage.update({role: max(input_tokens + 6000, amount)
                         for role, amount in observed_reviews.items()})
    review_reserve = sum(review_usage.values())
    remaining = runner.remaining_tokens()
    minimum_author = max(12000, author_usage, author_input_tokens + 6000)
    required = review_reserve + FINAL_HANDOFF_RESERVE + repair_reserve + minimum_author
    author_grant = max(0, min(limit // 4,
        remaining - review_reserve - FINAL_HANDOFF_RESERVE - repair_reserve))
    return {
        "candidate_sha256": campaign.body["drafts"][-1]["candidate_sha256"]
                            if campaign and campaign.body.get("drafts") else None,
        "token_limit": limit,
        "time_limit_seconds": runner.task.contract.get("time_limit_seconds"),
        "remaining_tokens": remaining,
        "review_role_reserves": review_usage,
        "review_reserve": review_reserve,
        "handoff_reserve": FINAL_HANDOFF_RESERVE,
        "repair_reserve": repair_reserve,
        "input_token_estimate": input_tokens,
        "repair_input_token_estimate": repair_input_tokens,
        "author_input_token_estimate": author_input_tokens,
        "minimum_author_grant": minimum_author,
        "author_grant": author_grant,
        "required_remaining_tokens": required,
        "shortfall_tokens": max(0, required - remaining),
        "author_slice_shortfall_tokens": max(0, minimum_author - limit // 4),
        "minimum_total_token_limit": max(limit - remaining + required, 4 * minimum_author),
        "capacity_status": "funded" if author_grant >= minimum_author else (
            "insufficient_tokens" if remaining < required else "author_slice_below_minimum"),
        "timing": _cycle_timing(runner),
        "policy": "fresh-operation-usage-with-25-percent-margin",
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
    base = current["review_reserve"] + FINAL_HANDOFF_RESERVE
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
            "minimum_total_token_limit": max(runner.task.contract["token_limit"] - remaining + required,
                                             4 * future["minimum_author_grant"] if revisions else 0),
            "capacity_status": "estimated_funded" if remaining >= required and (
                not revisions or future["author_slice_shortfall_tokens"] == 0) else "capacity_risk",
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
    return {
        "contract": runner.task.contract,
        "sources": [
            {k: v for k, v in s.items() if k not in {"artifact", "extracted_artifact"}}
            for s in runner.task.sources
            if s.get("source_id")
        ],
        "verification_receipts": campaign.body["verification_receipts"],
        "search_receipts": campaign.body["search_receipts"],
        "prior_comments": prior,
        "expected_response_ids": sorted(c["id"] for c in prior),
        "previous_candidate": previous,
        "previous_candidate_sha256": stable_hash(previous) if previous else None,
    }


def _author(runner, parent, handle, manuscript, campaign, allowance, *, revision=False):
    if allowance < 1000:
        raise StopResearch("limit_reached_partial", "final specialist review reservation preserved")
    operation = "revise" if revision else "draft"
    payload = _author_payload(runner, campaign, revision=revision)
    prior = payload["prior_comments"]
    reserved_after_author = runner.remaining_tokens() - allowance
    for attempt in range(2):
        runner.check()
        allowance = runner.remaining_tokens() - reserved_after_author
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
    responses = {r["comment_id"]: r for r in draft["responses"]}
    for comment in prior:
        response = responses[comment["id"]]
        revision_review.respond(
            runner.session,
            comment["round_id"],
            comment_id=comment["id"],
            author=parent.id,
            response=response["response"],
            changes=response["changes"],
        )
    runner.session.commit()
    return digest


def _audit_wave(runner, parent, manuscript, campaign, digest, iteration):
    pending, results = [], []
    corrections, rejected, attempts = [], [], {}
    # Complete specialist review has priority over optional later revisions/synthesis.
    # The original sixth-of-task slice rejected an observed 19,555-token review
    # despite ample unallocated task capacity. All review grants share one ledger.
    tokens = min(runner.task.contract["token_limit"] // 4,
                 (runner.remaining_tokens() - FINAL_HANDOFF_RESERVE) // len(SPECIALIST_ROLES))
    if tokens < 1000:
        raise StopResearch("limit_reached_partial", "insufficient allowance for all specialist reviewers")
    budget = _revision_budget(runner, campaign)
    # Initial reviews have priority; protect the available repair pool without
    # lowering forecasted review grants merely to fill an unfunded repair target.
    repair_reserve = min(budget["repair_reserve"], max(0,
        runner.remaining_tokens() - FINAL_HANDOFF_RESERVE - budget["review_reserve"]))
    tokens = min(runner.task.contract["token_limit"] // 4,
        (runner.remaining_tokens() - FINAL_HANDOFF_RESERVE - repair_reserve) // len(SPECIALIST_ROLES))
    role_grants = dict.fromkeys(SPECIALIST_ROLES, tokens)
    repair_allocations = []
    if iteration:
        repair_reserve = budget["repair_reserve"]
        spare = (runner.remaining_tokens() - FINAL_HANDOFF_RESERVE
                 - budget["review_reserve"] - budget["repair_reserve"])
        if spare < 0:
            raise StopResearch("limit_reached_partial",
                               "observed specialist re-review reservation unavailable")
        # Keep the larger observed role's grant instead of averaging away its reservation.
        role_grants = {role: amount + spare // len(SPECIALIST_ROLES)
                       for role, amount in budget["review_role_reserves"].items()}
    plan = {"iteration": iteration, "remaining_tokens": runner.remaining_tokens(),
            "review_role_grants": role_grants, "repair_reserve": repair_reserve,
            "repair_forecast": budget["repair_reserve"], "handoff_reserve": FINAL_HANDOFF_RESERVE}
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
        quality.update_campaign(campaign, dispatches=[*campaign.body.get("dispatches", []),
            {"agent_id": child.id, "iteration": iteration, "packet": packet}])
        runner.session.commit()
        allocation = runner.send(handle, child, "audit", grant, {"packet": packet})
        pending.append((child, handle, allocation, packet))

    # Both waves use at most three workers. A completed/closed worker releases a
    # slot; waiting correction workers occupy slots until their repair finishes.
    # Deferred roles keep their token grants and can start before other roles finish.
    concurrent = 3
    deferred = list(SPECIALIST_ROLES[concurrent:])
    for role in SPECIALIST_ROLES[:concurrent]:
        dispatch(role, role_grants[role])
    while pending or corrections or deferred:
        runner.check()
        if (deferred and not corrections and len(pending) < concurrent
                and not any(attempts.get(child.id, 0) for child, _, _, _ in pending)):
            if rejected:
                break
            role = deferred.pop(0)
            remaining_repair = max(0, repair_reserve - sum(
                allocation_charge(a) for a in repair_allocations))
            grant = (runner.remaining_tokens() - FINAL_HANDOFF_RESERVE - remaining_repair
                     - sum(role_grants[r] for r in deferred))
            if grant < role_grants[role]:
                raise StopResearch("limit_reached_partial", "deferred specialist reservation unavailable")
            if not iteration:
                grant = role_grants[role]
            dispatch(role, grant)
        if not pending:
            # Gather the whole wave's defects first. Each existing specialist may
            # correct its report once, using the original deadline and ledger.
            tokens = min(runner.task.contract["token_limit"] // 3,
                         (runner.remaining_tokens() - FINAL_HANDOFF_RESERVE
                          - sum(role_grants[role] for role in deferred)) // len(corrections))
            if tokens < 1000:
                raise StopResearch("limit_reached_partial", "report corrections exceed remaining allowance")
            for child, handle, packet, issues in corrections:
                attempts[child.id] = 1
                child.state = "running"
                allocation = runner.send(handle, child, "audit", tokens, {
                    "packet": packet, "report_corrections": issues,
                    "original_report": child.provenance["report_attempts"][-1]["report"],
                    "original_report_sha256": child.provenance["report_attempts"][-1]["report_sha256"],
                })
                repair_allocations.append(allocation)
                pending.append((child, handle, allocation, packet))
            corrections = []
        for child, handle, allocation, packet in list(pending):
            raw = runner.event(handle, child, allocation, "specialist_report")
            if raw is None:
                continue
            child.provenance = {**child.provenance, "original_return": raw,
                "report_attempts": [*child.provenance.get("report_attempts", []), {
                    "attempt": attempts.get(child.id, 0), "report": raw,
                    "span_id": allocation["span_id"],
                    "report_sha256": stable_hash(raw), "packet_sha256": packet["packet_sha256"],
                }]}
            runner.session.commit()
            try:
                report, blockers, flags = quality.validate_report(raw, packet)
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
            author_threads = quality.author_model_threads(parent)
            other_threads = {
                a.provenance.get("specialist_report_model", {}).get("codex_thread_id")
                for a in runner.agents
                if a.role == "child" and a.id != child.id
            }
            if identity and (identity in author_threads or identity in other_threads):
                raise ValueError("specialist reused an author or reviewer thread")
            child.report, child.state = report, "completed"
            child.provenance = {**child.provenance, "report_hash": stable_hash(report)}
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
                "agent_id": child.id,
                "role": report["role"],
                "iteration": iteration,
                "candidate_sha256": digest,
                "packet": packet,
                "report_sha256": stable_hash(report),
                "blockers": blockers,
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
    manifests = [
        {
            "role": f"{r[1]['role']}-{iteration}",
            "packet_sha256": rec["packet"]["packet_sha256"],
            "evidence_artifacts": rec["packet"]["evidence_artifacts"],
        }
        for r, rec in zip(results, campaign.body["reports"][-len(SPECIALIST_ROLES):], strict=True)
    ]
    quality.update_campaign(campaign, packets=[*campaign.body["packets"], *manifests])
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
    if len(comments) > 60:
        raise ValueError("too many specialist objections; return a partial handoff")
    if comments:
        review = revision_review.open_round(
            runner.session, manuscript.id, comments=comments, reviewer="specialist-controller"
        )
        quality.update_campaign(campaign, rounds=[*campaign.body["rounds"], review.id])
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
    manuscript, campaign = quality.create_campaign(session, task)
    research_trace.record(
        runner, "campaign_started", manuscript_id=manuscript.id, required_roles=list(SPECIALIST_ROLES)
    )
    parent = handle = None
    try:
        manuscript_acquisition.collect(runner, manuscript, campaign)
        parent = runner.new_agent("parent", {"question": task.contract["question"], "role": "author"})
        handle = runner.spawn(parent)
        # Future review cannot be borrowed by the author, even after unused allowances are released.
        initial_budget = _revision_budget(runner)
        reserve = (len(SPECIALIST_ROLES) * (initial_budget["input_token_estimate"] + 6000)
                   + initial_budget["repair_reserve"] + FINAL_HANDOFF_RESERVE)
        draft_allowance = min(task.contract["token_limit"] // 3, runner.remaining_tokens() - reserve)
        digest = _author(runner, parent, handle, manuscript, campaign, draft_allowance)
        plan = _initial_capacity_plan(runner, campaign)
        quality.update_campaign(campaign, initial_capacity_plans=[
            *campaign.body.get("initial_capacity_plans", []), plan])
        research_trace.record(runner, "initial_capacity_planned", **plan)
        session.commit()
        completed = False
        previous_failure = None
        for iteration in range(task.contract["max_revision_cycles"] + 1):
            completed = _audit_wave(runner, parent, manuscript, campaign, digest, iteration)
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
            if iteration == task.contract["max_revision_cycles"]:
                break
            # Original deadline and ledger apply to every revision; no fresh task grant.
            budget = _revision_budget(runner, campaign)
            quality.update_campaign(campaign, revision_budget_plans=[
                *campaign.body.get("revision_budget_plans", []), {"iteration": iteration, **budget}])
            research_trace.record(runner, "revision_budget_planned", **budget)
            session.commit()
            allowance = budget["author_grant"]
            if allowance < budget["minimum_author_grant"]:
                if budget["capacity_status"] == "author_slice_below_minimum":
                    raise StopResearch("limit_reached_partial",
                        f"revision author slice cap {task.contract['token_limit'] // 4} below "
                        f"required {budget['minimum_author_grant']}; review and handoff reserves preserved")
                raise StopResearch("limit_reached_partial",
                    f"revision needs at least {budget['minimum_author_grant']} tokens after reserving "
                    f"{budget['review_reserve']} for specialist re-review and "
                    f"{budget['handoff_reserve']} for final handoff and "
                    f"{budget['repair_reserve']} for repair; {budget['remaining_tokens']} remain")
            digest = _author(runner, parent, handle, manuscript, campaign, allowance, revision=True)
        _save_handoff(runner, manuscript, campaign)
        # A final summary has a safety margin for best-effort usage telemetry.
        # The complete candidate/reports stay in the evidence graph, not repeated
        # in the parent's final message context.
        final_allowance = runner.remaining_tokens() - 1000
        if completed and final_allowance >= 6000:
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
