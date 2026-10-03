"""Real local embeddings on a declared synthetic benchmark, with network calls blocked."""

import argparse
import json
import os
import socket
from pathlib import Path

CORPUS = [
    ("compactness", "Every open cover admits a finite subcover."),
    ("injection", "Distinct arguments always have distinct images."),
    ("surjection", "Each element of the codomain is the image of at least one input."),
    ("separation", "Any two distinct points have disjoint open neighbourhoods."),
    ("completeness", "A metric space is complete when every Cauchy sequence has a limit in that space."),
    ("ultrametric", "The distance from x to z never exceeds the larger of the distances "
     "from x to y and y to z."),
    ("bijection", "This mapping is both injective and surjective."),
    ("continuity", "The preimage of every open set is open."),
    ("scope-a", "Every compact subset of a metric space is closed."),
    ("scope-b", "Every closed subset of a metric space is compact."),
    ("negation", "Not every closed subset of a metric space is compact."),
]
QUERIES = [
    ("compactness", "Compactness of a topological space"),
    ("injection", "One-to-one function"),
    ("surjection", "Onto mapping"),
    ("separation", "Hausdorff separation"),
    ("completeness", "Cauchy sequence convergence"),
    ("ultrametric", "Strong triangle inequality"),
    ("bijection", "Bijective function"),
    ("continuity", "Continuous function"),
]
HOLDOUT_CORPUS = [
    ("convexity", "The entire line segment joining any two points of the set stays inside the set."),
    ("independence", "A linear combination of these vectors vanishes only when every coefficient is zero."),
    ("eigenvector", "Applying the matrix to this nonzero vector produces a scalar multiple "
     "of the same vector."),
    ("kernel", "These are precisely the inputs sent to the zero vector by the linear map."),
    ("connected", "Every pair of vertices can be joined by a path of edges."),
    ("bipartite", "The vertices split into two classes and each edge joins vertices in different classes."),
    ("monotone", "Increasing the argument never decreases the value of the function."),
    ("nullity", "The dimension of the domain equals the dimension of the kernel "
     "plus the dimension of the image."),
    *CORPUS[-3:],
]
HOLDOUT_QUERIES = [
    ("convexity", "Convex subsets"), ("independence", "Linear independence"),
    ("eigenvector", "Eigenvectors"), ("kernel", "Null space"),
    ("connected", "Connected graph"), ("bipartite", "Bipartite graph"),
    ("monotone", "Nondecreasing function"), ("nullity", "Rank nullity theorem"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recall", choices=["focused", "broad"], default="focused")
    parser.add_argument("--suite", choices=["development", "holdout"], default="development")
    args = parser.parse_args()
    corpus, queries = (HOLDOUT_CORPUS, HOLDOUT_QUERIES) if args.suite == "holdout" else (CORPUS, QUERIES)
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve()
    os.environ.update(WB_LOAD_DOTENV="false", WB_DATA_DIR=str(output / "data"),
                      WB_DATABASE_URL="sqlite:///" + (output / "synthetic.sqlite3").as_posix(),
                      WB_PROVIDER_MODE="fake", WB_LLM_PROVIDER="openai", WB_AUTH_REQUIRED="false")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from workbench import config
    from workbench.models import Base
    from workbench.providers.research_embeddings import get_local_provider
    from workbench.research_contract import TaskBrief
    from workbench.services import research, research_retrieval, research_semantic, research_tasks

    config.get_settings.cache_clear()
    engine = create_engine(os.environ["WB_DATABASE_URL"])
    Base.metadata.create_all(engine)
    attempts = []
    original_connect = socket.socket.connect

    def blocked(*args, **kwargs):
        attempts.append("blocked network attempt")
        raise AssertionError("Network disabled during local semantic acceptance")

    socket.socket.connect = blocked
    try:
        provider = get_local_provider()
        with Session(engine) as session:
            workspace = research.create_workspace(session, "Synthetic semantic benchmark")
            project = research.create_project(session, workspace.id, "Semantic coverage")
            task = research_tasks.create_task(session, project.id, TaskBrief(question="Benchmark fixture"))
            ids = {}
            for number, (label, text) in enumerate(corpus):
                sources = research_tasks.attach(session, task, f"fixture-{number:02}.txt", text.encode(),
                                                version="synthetic-v1")
                ids[label] = sources[-1]["source_id"]
            first = research_semantic.index_project(session, project.id)
            session.commit()
            warm = research_semantic.index_project(session, project.id)
            assert warm["embedded_now"] == 0
            results = []
            for expected, query in queries:
                row = {"expected": expected, "query": query}
                for mode in ("lexical", "hybrid"):
                    found = research_retrieval.retrieve(session, project.id, query, mode=mode,
                                                        recall=args.recall, limit=3)
                    row[mode] = {"hit_at_3": any(ids[expected] in [o.get("source_id") for o in c["origins"]]
                                                  for c in found["cards"]),
                                 "cards": found["cards"], "semantic": found["semantic"]}
                results.append(row)
            scope = research_retrieval.retrieve(session, project.id,
                "compact closed subsets metric spaces", mode="hybrid", limit=12)
            scope_ids = {o.get("source_id") for c in scope["cards"] for o in c["origins"]}
            assert {ids[k] for k in ("scope-a", "scope-b", "negation")} <= scope_ids
            absent = research_retrieval.retrieve(session, project.id,
                "tomato soup cooking recipe", mode="hybrid", recall=args.recall)
            negatives = [{"query": q, "candidate_count": len(research_retrieval.retrieve(
                session, project.id, q, mode="hybrid", recall=args.recall)["cards"])} for q in [
                "paleolithic anthropology", "stellar magnetic fields", "gene regulatory networks",
                "sonata form composition", "organic reaction mechanism", "agricultural irrigation",
                "medieval trade routes", "photosynthesis chloroplasts"]]
            summary = {"model": provider.model, "project_id": project.id, "synthetic": True,
                       "recall": args.recall,
                       "suite": args.suite,
                       "cases": len(results),
                       "lexical_hits_at_3": sum(r["lexical"]["hit_at_3"] for r in results),
                       "hybrid_hits_at_3": sum(r["hybrid"]["hit_at_3"] for r in results),
                       "unrelated_query_results": len(absent["cards"]),
                       "negative_queries": negatives,
                       "negative_queries_with_candidates": sum(n["candidate_count"] > 0 for n in negatives),
                       "scope_and_negation_records_preserved": True,
                       "network_attempts": len(attempts), "paid_api_calls": 0,
                       "first_index": first, "warm_index": warm,
                       "limits": "Small hand-authored demonstration, not an independent research benchmark. "
                       "The model is not a mathematical equivalence or entailment checker."}
            assert not attempts
            for name, value in [("verification.json", summary), ("query-results.json", results),
                                ("scope-contrasts.json", scope), ("corpus.json", corpus)]:
                (output / name).write_text(json.dumps(value, indent=2), encoding="utf-8")
            print(json.dumps({k: v for k, v in summary.items()
                              if k not in ("first_index", "warm_index")}, indent=2))
    finally:
        socket.socket.connect = original_connect
        engine.dispose()


if __name__ == "__main__":
    main()
