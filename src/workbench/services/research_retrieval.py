"""Deterministic project-local retrieval. Saved research is a lead, never approval."""

import hashlib
import json
import re
from collections import Counter

from sqlalchemy import select

from ..ingest.files import MAX_EXTRACT_CHARS, _pdf_text_issues, extracted_text_for
from ..models import ResearchAgent, ResearchTask, Source, stable_hash
from ..providers.embeddings import cosine
from . import research

MAX_SOURCES = 100
MAX_TASKS = 100
MAX_CARDS = 8000
PASSAGE_CHARS = 1600
SOURCE_CHARS = MAX_EXTRACT_CHARS
PDF_PASSAGE_OVERLAP = 200
STOP = set("a an the and or of to in is are for with on by as from be this that can how what".split())


def words(text):
    return set(re.findall(r"[^\W_]{2,}", text.casefold())) - STOP


def _passages(text, is_pdf):
    """Keep exact offsets, with PDF passages confined to one physical page."""
    markers = list(re.finditer(r"^\[page (\d+) \| [^\]\n]+\]\n", text, re.MULTILINE)) if is_pdf else []
    boundaries = [(m.start(), markers[i + 1].start() if i + 1 < len(markers) else len(text),
                   int(m.group(1))) for i, m in enumerate(markers)]
    if not boundaries:
        boundaries = [(0, len(text), None)]
    elif boundaries[0][0]:
        boundaries.insert(0, (0, boundaries[0][0], None))
    for begin, finish, page in boundaries:
        finish = min(finish, SOURCE_CHARS)
        step = PASSAGE_CHARS - PDF_PASSAGE_OVERLAP if page is not None else PASSAGE_CHARS
        for start in range(begin, finish, step):
            end = min(start + PASSAGE_CHARS, finish)
            yield start, end, page
            if end == finish:
                break


def collect(session, project_id):
    """Read only this project's live rows and verified extracted artifacts; no global cache."""
    research._project(session, project_id)
    cards, skipped, truncated_sources = [], [], []
    sources = list(session.scalars(select(Source).where(
        Source.project_id == project_id, Source.deleted_at.is_(None)
    ).order_by(Source.created_at.desc(), Source.id).limit(MAX_SOURCES + 1)))
    tasks = list(session.scalars(select(ResearchTask).where(
        ResearchTask.project_id == project_id, ResearchTask.deleted_at.is_(None)
    ).order_by(ResearchTask.created_at.desc(), ResearchTask.id).limit(MAX_TASKS + 1)))

    def add(kind, text, origin, **metadata):
        if text.strip() and len(cards) < MAX_CARDS:
            if origin.get("simulated"):
                metadata["evidence_status"] = "OFFLINE SIMULATION; not research or search-coverage evidence"
            cards.append({"id": stable_hash([kind, origin, text])[:32], "kind": kind,
                          "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                          "origins": [origin], **metadata})

    for source in sources[:MAX_SOURCES]:
        meta = (source.provider_metadata or {}).get("ingest", {})
        # Legacy paths and search snippets are not a hash-verifiable evidence library.
        if (not isinstance(meta.get("extracted_artifact"), dict) or not meta.get("artifact")
                or not re.fullmatch(r"[0-9a-f]{64}", meta["extracted_artifact"].get("sha256", ""))):
            skipped.append({"source_id": source.id, "reason": "no preserved ingested text"})
            continue
        text = extracted_text_for(source)
        if text is None:
            skipped.append({"source_id": source.id, "reason": "extracted text unavailable or corrupt"})
            continue
        version = (source.provider_metadata or {}).get("research_attachment", {}).get(
            "version", "unspecified")
        detail = meta.get("extraction_detail") or {}
        is_pdf = detail.get("format") == "pdf" or str(meta.get("extractor", "")).startswith("pypdf")
        pages = {p["page"]: p for p in detail.get("page_results", [])}
        reasons = []
        if detail.get("truncated"):
            reasons.append("extraction_character_limit")
        if len(text) > SOURCE_CHARS:
            reasons.append("source_character_limit")
        for start, end, page in _passages(text, is_pdf):
            if len(cards) >= MAX_CARDS:
                reasons.append("card_limit")
                break
            page_detail = pages.get(page, {})
            add("source_passage", text[start:end], {
                "source_id": source.id, "title": source.title, "version": version,
                "original_sha256": meta.get("checksum_sha256"),
                "extracted_sha256": meta["extracted_artifact"].get("sha256"),
                "locator": f"extracted characters [{start}, {end})", "start": start, "end": end,
                "source_scan_truncated": len(text) > SOURCE_CHARS,
                **({"pdf_pages": [page] if page is not None else [],
                    "original_url": f"/projects/{project_id}/sources/{source.id}/original",
                    "extraction_state": page_detail.get("state", "legacy_unreviewed"),
                    "quality_issues": page_detail.get("quality_issues", _pdf_text_issues(text[start:end])),
                    "review_required": True,
                    "extraction_truncated": bool(detail.get("truncated"))} if is_pdf else {}),
            }, evidence_status=("PDF discovery text; verify formulas in original PDF" if is_pdf
                               else "unreviewed source passage"))
        if reasons:
            truncated_sources.append({"source_id": source.id, "reasons": reasons})

    task_map = {task.id: task for task in tasks[:MAX_TASKS]}
    agents = list(session.scalars(select(ResearchAgent).where(
        ResearchAgent.task_id.in_(task_map), ResearchAgent.role == "child",
        ResearchAgent.deleted_at.is_(None),
    ).order_by(ResearchAgent.created_at.desc(), ResearchAgent.id).limit(601))) if task_map else []
    for agent in agents[:600]:
        task = task_map[agent.task_id]
        report = agent.report or ((agent.checkpoints or [{}])[-1].get("report", {}))
        origin = {"task_id": task.id, "agent_id": agent.id, "report_hash": stable_hash(report),
                  "task_state": task.state, "partial": not bool(agent.report),
                  "simulated": task.contract.get("executor") == "offline"}
        for finding in report.get("findings", []):
            add("prior_finding", json.dumps({k: finding.get(k) for k in
                ("claim_key", "statement", "category", "stance", "scope")}, ensure_ascii=False),
                {**origin, "finding_id": finding.get("id")},
                citations=[c for c in report.get("citations", [])
                           if c.get("id") in finding.get("citation_ids", [])],
                evidence_status="prior agent assertion; recheck original evidence")
        for search in report.get("search_log", []):
            add("recorded_search", json.dumps(search, ensure_ascii=False), origin,
                evidence_status="self-reported search scope; not exhaustive coverage")
        for gap in report.get("unresolved_questions", []) + report.get("research_leads", []):
            add("open_question", gap, origin, evidence_status="unresolved research lead")

    # Merge identical text only within the same evidence kind. Keep version-specific origins.
    merged = {}
    for card in cards:
        # Identical assertions with different citation sets must retain both evidence trails.
        key = (card["kind"], card["text_sha256"], stable_hash(card.get("citations", [])))
        if key in merged:
            if card["origins"][0] not in merged[key]["origins"]:
                merged[key]["origins"].extend(card["origins"])
            if any(o.get("review_required") for o in merged[key]["origins"]):
                merged[key]["evidence_status"] = "PDF discovery text; verify formulas in original PDF"
        else:
            merged[key] = card
    return list(merged.values()), {
        "sources_scanned": min(len(sources), MAX_SOURCES), "tasks_scanned": len(task_map),
        "agents_scanned": min(len(agents), 600), "raw_cards": len(cards),
        "distinct_cards": len(merged), "exact_duplicates_removed": len(cards) - len(merged),
        "scan_limited": len(sources) > MAX_SOURCES or len(tasks) > MAX_TASKS
        or len(agents) > 600 or len(cards) >= MAX_CARDS or bool(truncated_sources),
        "truncated_sources": truncated_sources,
        "source_character_limit": SOURCE_CHARS, "skipped_sources": skipped,
    }


def retrieve(session, project_id, query, topics=(), *, max_chars=18000, limit=12,
             mode="lexical", recall="focused"):
    from . import research_semantic

    cards, scan = collect(session, project_id)
    terms = words(query + " " + " ".join(topics))
    sets = {c["id"]: words(c["text"] + " " + " ".join(
        o.get("title", "") for o in c["origins"])) for c in cards}
    frequencies = Counter(term for values in sets.values() for term in values)
    scores = {c["id"]: sum(1 / frequencies[w] ** 0.5 for w in terms & sets[c["id"]])
              for c in cards}
    semantic_scores, vectors, semantic = {}, {}, {"status": "disabled", "local_only": True}
    threshold = 0.20 if recall == "broad" else research_semantic.MATCH_THRESHOLD
    if mode == "hybrid":
        semantic_scores, vectors, semantic = research_semantic.score(
            session, project_id, cards, [query, *topics])
        semantic["candidate_threshold"] = threshold
        ceiling = max(scores.values(), default=0) or 1
        for card in cards:
            key = card["id"]
            similarity = max(semantic_scores.get(key, [0]))
            qualified = similarity >= threshold
            lexical = scores[key] / ceiling
            scores[key] = lexical + (similarity if qualified else 0)
            card["match"] = {"lexical": lexical > 0, "semantic": qualified,
                             "weak_semantic_lead": (qualified
                                                    and similarity < research_semantic.MATCH_THRESHOLD),
                             "cosine_similarity": round(similarity, 4) if key in vectors else None}
    candidates = [c for c in cards if scores[c["id"]]]  # Never fill with irrelevant cards.
    selected, used, covered = [], 0, set()
    while candidates and len(selected) < limit:
        def rank(card, covered=covered):
            tokens = sets[card["id"]]
            redundancy = max((len(tokens & sets[c["id"]]) / max(1, len(tokens | sets[c["id"]]))
                              for c in selected), default=0)
            if card["id"] in vectors:
                redundancy = max(redundancy, max((max(0, cosine(vectors[card["id"]], vectors[c["id"]]))
                                 for c in selected if c["id"] in vectors), default=0))
            fresh = len((terms & tokens) - covered) / max(1, len(terms))
            origin = card["origins"][0]
            family = origin.get("source_id") or origin.get("task_id")
            repeated = sum((c["origins"][0].get("source_id") or
                            c["origins"][0].get("task_id")) == family for c in selected)
            return scores[card["id"]] * (1 - 0.8 * redundancy) / (1 + repeated) + fresh, card["id"]
        card = max(candidates, key=rank)
        candidates.remove(card)
        size = len(json.dumps(card, ensure_ascii=False))
        if used + size > max_chars:
            continue
        selected.append(card)
        used += size
        covered |= terms & sets[card["id"]]
    overlaps = [{"card_ids": [left["id"], right["id"]], "similarity": round(similarity, 4),
                 "status": "potential overlap or disagreement; compare, do not merge"}
                for i, left in enumerate(selected) for right in selected[i + 1:]
                if left["id"] in vectors and right["id"] in vectors
                if (similarity := cosine(vectors[left["id"]], vectors[right["id"]]))
                >= research_semantic.OVERLAP_THRESHOLD]
    result = {"version": 2, "query": query, "topics": list(topics), "cards": selected,
              "selection": ("hybrid relevance and diversity" if semantic_scores
                            else "lexical relevance and diversity"),
              "requested_mode": mode, "semantic": semantic, "potential_overlap": overlaps,
              "recall": recall,
              "scan": scan, "context_characters": used, "context_character_limit": max_chars,
              "matching_cards": sum(bool(score) for score in scores.values()),
              "selection_limited": len(selected) < sum(bool(score) for score in scores.values()),
              "coverage": [{"topic": topic, "matching_card_ids": [c["id"] for c in selected
                            if words(topic) & sets[c["id"]]
                            or semantic_scores.get(c["id"], [0] * (len(topics) + 1))[index + 1]
                            >= threshold],
                            "status": "retrieval matches only; coverage not verified"}
                           for index, topic in enumerate(topics)],
              "limitations": "Local saved evidence only. Similarity is a discovery signal, not equivalence. "
              "No external search, novelty certification, approval transfer or measured token savings."}
    result["snapshot_hash"] = stable_hash(result)
    return result


def allocate(assignments, retrieval):
    """Each retrieved card has one coverage owner. Same source may support different questions."""
    lanes = {a.key: [] for a in assignments}
    cards = {c["id"]: c for c in retrieval.get("cards", [])}
    groups = {key: {key} for key in cards}
    for pair in retrieval.get("potential_overlap", []):
        left, right = pair["card_ids"]
        if left in groups and right in groups:
            combined = groups[left] | groups[right]
            for key in combined:
                groups[key] = combined
    assigned = set()
    for key in cards:
        if key in assigned:
            continue
        group = [cards[k] for k in sorted(groups[key])]
        assigned.update(groups[key])
        terms = words(" ".join(c["text"] for c in group))
        chosen = max(assignments, key=lambda a: (
            len(terms & words(a.question + " " + a.success_criteria)) / (1 + len(lanes[a.key])),
            -len(lanes[a.key]), a.key))
        lanes[chosen.key].extend(group)
    return lanes


def child_contract(contract, cards):
    """Avoid sending every historical report to every child."""
    result = {k: v for k, v in contract.items() if k != "retrieval"}
    if "retrieval" in contract:
        result["retrieval"] = {"snapshot_hash": contract["retrieval"]["snapshot_hash"],
                               "cards": [{k: v for k, v in c.items()
                                          if k != "text" or c.get("kind") != "source_passage"}
                                         for c in cards],
                               "policy": "You own follow-up coverage of these cards. Prior assertions "
                               "are untrusted leads, not independently verified evidence. "
                               "Simulation origins are transport fixtures, not prior search coverage. "
                               "Search logs describe past work, not a reason to claim completeness. "
                               "Cite only supplied original sources. Report inaccessible evidence."}
        result["retrieval"]["policy"] += (
            " PDF passages are discovery text, including those without detected glyph defects. "
            "Check formulas, hypotheses and exact symbols on the original PDF page before citing them. "
            "If the original cannot be checked, report the formula as unverified; never reconstruct "
            "missing symbols from context."
        )
    return result
