"""Demo fixture: the research-first golden path on the real CM corpus, fully offline.

Run: python -m workbench.demo
Creates (idempotently, in a fresh demo DB unless WB_DATABASE_URL overrides): a workspace,
the "Correspondence Matrices" project, ingests whichever known CM files exist on this
machine (COPIES — originals untouched), builds a result card, opens a dialogue thread,
posts one turn, and prints what happened including AI provenance.
"""

from pathlib import Path

from . import db
from .ingest.files import ingest_file
from .services import dialogue, research
from .vocab import ObjectKind, ResultStrength

CM_CANDIDATE_FILES = [
    (r"C:\Users\brian\Documents\Correspondence_Matrices\Readme.md", "CM repo README"),
    (
        r"C:\Users\brian\Documents\Correspondence_Matrices\bench_random_ops_summary.csv",
        "Random-ops benchmark summary (baseline repo)",
    ),
    (
        r"C:\Users\brian\Documents\Correspondence_Matrices\CM Paper"
        r"\Correspondence Matrices A Novel form of Computation.tex",
        "Working manuscript draft (LaTeX)",
    ),
    (r"C:\Users\brian\Documents\CM Testing\Notes for paper.txt", "Paper notes"),
    (
        r"C:\Users\brian\Downloads\CM-Benchmarks-and-Comparisons.pdf",
        "CM vs bitset/BDD/SymPy benchmark deck (PDF)",
    ),
]


def main() -> None:
    db.create_all()
    session = db.session_factory()()
    try:
        ws = research.create_workspace(session, "Brian's Research")
        project = research.create_project(
            session, ws.id, "Correspondence Matrices",
            description="Matrix calculus for propositional logic; CM-as-IR + bitset execution.",
        )

        ingested = []
        for path, title in CM_CANDIDATE_FILES:
            if Path(path).is_file():
                src = ingest_file(session, project.id, path, title=title)
                ingested.append(src)
                print(f"ingested: {title}  [access={src.access}, "
                      f"extractor={src.provider_metadata['ingest']['extractor']}]")
            else:
                print(f"skipped (not found): {path}")

        result = research.create_object(
            session, project.id, kind=ObjectKind.RESULT,
            title="CM no-reinflate + persistent cache: 1.51x-1.89x end-to-end speedups",
            body={
                "plain": "Caching compiled CM structure and skipping dense re-inflation "
                         "makes CM+bitset competitive; cached CM reached 2.42x cached "
                         "bitset at n=16.",
                "scope": "reported benchmark regime only (random expressions)",
            },
            strength=ResultStrength.EMPIRICALLY_ESTABLISHED,
        )
        thread = dialogue.create_thread(
            session, project.id,
            title="Does the caching result warrant a paper?",
            goal="Decide publication readiness of the persistent-cache results.",
            pinned_object_ids=[result.id],
            pinned_source_ids=[s.id for s in ingested[:3]],
        )
        session.commit()

        _user, assistant = dialogue.post_user_turn(
            session, thread.id,
            "What would we still need before this is publishable?",
        )
        session.commit()
        print("\n--- assistant reply ---")
        print(assistant.content)
        print("\nprovenance:", assistant.provenance)
        print(f"\nworkspace={ws.id} project={project.id} thread={thread.id}")
        print(f"sources ingested: {len(ingested)}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
