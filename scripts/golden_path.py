"""End-to-end golden path on the real CM corpus (live providers when configured).

Run: python -X utf8 scripts/golden_path.py
Journey: project → ingest → result card → grounded dialogue → literature search/import/
screen → contribution map → paper candidate → manuscript+sections+claims → audit →
skeptical review → export bundle. Uses a dedicated DB (data/golden.sqlite3).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, "src")
os.environ.setdefault("WB_DATABASE_URL", "sqlite:///data/golden.sqlite3")

from workbench import db  # noqa: E402
from workbench.ingest.files import ingest_file  # noqa: E402
from workbench.services import (  # noqa: E402
    audits, authoring, dialogue, export_service, literature, research,
)
from workbench.vocab import (  # noqa: E402
    ClaimSupport, Novelty, ObjectKind, ResultStrength, SourceAccess,
)


def main() -> None:
    Path("data/golden.sqlite3").unlink(missing_ok=True)
    db.create_all()
    session = db.session_factory()()

    ws = research.create_workspace(session, "Brian's Research")
    project = research.create_project(session, ws.id, "Correspondence Matrices")

    # P2: ingest real corpus files (copies; originals untouched)
    ingested = []
    for path, title in [
        (r"C:\Users\brian\Documents\Correspondence_Matrices\Readme.md", "CM repo README"),
        (r"C:\Users\brian\Downloads\CM-Benchmarks-and-Comparisons.pdf", "CM benchmark deck"),
    ]:
        if Path(path).is_file():
            ingested.append(ingest_file(session, project.id, path, title=title))
    print(f"[P2] ingested {len(ingested)} corpus files")

    result = research.create_object(
        session, project.id, kind=ObjectKind.RESULT,
        title="CM no-reinflate + persistent cache: 1.51x-1.89x end-to-end speedups",
        body={"scope": "reported benchmark regime (random expressions)"},
        strength=ResultStrength.EMPIRICALLY_ESTABLISHED,
    )
    thread = dialogue.create_thread(
        session, project.id, title="Publication readiness",
        goal="Decide whether the caching results warrant a paper.",
        pinned_object_ids=[result.id], pinned_source_ids=[s.id for s in ingested],
    )
    session.commit()
    _u, assistant = dialogue.post_user_turn(
        session, thread.id,
        "In two or three sentences: what is the single biggest gap before the persistent-cache "
        "results are publishable, and which comparison would you run next?",
    )
    session.commit()
    print(f"[P2] dialogue reply (model={assistant.provenance['model']}, "
          f"simulated={assistant.provenance['simulated']}):")
    print("     " + assistant.content.strip().replace("\n", "\n     ")[:600])

    # P3: literature
    _saved, works = literature.run_search(
        session, project.id, provider="openalex",
        query="binary decision diagram boolean function manipulation", count=5,
    )
    print(f"[P3] openalex search returned {len(works)} deduped works")
    src, created = literature.import_work(session, project.id, works[0])
    literature.set_screening(
        session, project.id, src.id, state="include", relationship="background",
        reason="canonical prior work for Boolean function representation",
    )
    contribution = literature.assess_contribution(
        session, project.id, title="CM as reusable Boolean IR",
        statement="CM offers a structure-preserving operator calculus usable as a compile-once IR",
        novelty=Novelty.APPARENTLY_NOVEL_LIMITED_SEARCH,
        coverage_note="OpenAlex keyword search 2026-07-20 (BDD lineage); no systematic sweep yet",
        closest_prior_source_ids=[src.id],
    )
    print(f"[P3] imported '{src.title[:50]}' (created={created}); "
          f"contribution novelty={contribution.body['novelty']}")

    # P4: candidate + manuscript
    excerpt = None
    if src.provider_metadata.get("scholarly", {}).get("abstract"):
        excerpt = research.capture_excerpt(
            session, src.id,
            text=src.provider_metadata["scholarly"]["abstract"][:500],
            locator="abstract",
        )
    claim_kwargs = {"research_object_ids": [result.id]}
    support = ClaimSupport.RESEARCH_RESULT
    if excerpt:
        claim_kwargs["excerpt_ids"] = [excerpt.id]
        support = ClaimSupport.BOTH
    claim = research.create_claim(
        session, project.id,
        text="Persistent structural-hash caching makes CM+bitset competitive for repeated evaluation",
        support=support, **claim_kwargs,
    )
    candidate = authoring.create_paper_candidate(
        session, project.id, title="CM as a Boolean IR: benchmark evidence",
        paper_type="computational",
        structure="algorithm_correctness_complexity_experiments",
        central_question="Is CM a useful structure-preserving Boolean IR?",
        thesis="With no-reinflate + persistent cache, yes for repeated evaluation",
        novelty_caveat="apparently novel under limited search only",
        missing_work=["CUDD comparison at larger n", "expert confirmation of novelty"],
    )
    ms = authoring.create_manuscript(
        session, project.id, title="Ultra-Fast Boolean Evaluation with Correspondence Matrices",
        from_candidate_id=candidate.id,
    )
    authoring.add_section(session, ms.id, heading="Introduction",
                          purpose="motivate CM as operator calculus")
    authoring.add_section(
        session, ms.id, heading="Results", purpose="report benchmark evidence",
        text="Caching compiled CM structure changes the performance story.",
        claim_ids=[claim.id],
    )
    session.commit()
    print(f"[P4] manuscript {ms.id} with 2 sections from candidate {candidate.id}")

    # P5: audits + skeptical review
    findings = audits.audit_manuscript(session, ms.id)
    print(f"[P5] audit findings: {len(findings)} "
          f"({sum(1 for f in findings if f['severity'] == 'error')} errors)")
    notes = audits.skeptical_review(session, ms.id)
    session.commit()
    print(f"[P5] skeptical review produced {len(notes)} objection notes (AI-suggested, open)")
    if notes:
        print("     e.g. " + notes[0].body["objection"][:200])

    # P6: export
    result_bundle = export_service.export_manuscript(session, ms.id)
    session.commit()
    print(f"[P6] exported to {result_bundle['out_dir']}")
    for fmt, path in result_bundle["files"].items():
        print(f"     {fmt}: {Path(path).name}")
    session.close()


if __name__ == "__main__":
    main()
