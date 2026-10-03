"""Run the proposal workflow end-to-end using only disposable synthetic fixtures."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="wb-proposal-demo-") as directory:
        root = Path(directory)
        os.environ["WB_PROVIDER_MODE"] = "fake"
        os.environ["WB_LOAD_DOTENV"] = "false"
        os.environ["WB_DATABASE_URL"] = f"sqlite:///{root / 'proposal-demo.sqlite3'}"
        os.environ["WB_DATA_DIR"] = str(root / "artifacts")

        from workbench import config, db, storage
        from workbench.services import proposals, research
        from workbench.vocab import SourceAccess

        config.get_settings.cache_clear()
        db.reset_engine_for_tests()
        db.create_all()
        session = db.session_factory()()
        try:
            workspace = research.create_workspace(session, "Synthetic proposal workspace")
            project = research.create_project(session, workspace.id, "Synthetic pilot")

            def source(title: str, text: str):
                snapshot = storage.store_content(
                    text.encode("utf-8"),
                    filename="synthetic-extracted.txt",
                    namespace="demo/proposal",
                    content_type="text/plain; charset=utf-8",
                )
                return research.register_source(
                    session,
                    project.id,
                    title=title,
                    access=SourceAccess.FULL_TEXT_USER_SUPPLIED,
                    acquisition="synthetic offline demo fixture",
                    provider_metadata={
                        "ingest": {
                            "checksum_sha256": snapshot["sha256"],
                            "extracted_artifact": snapshot,
                            "extraction_confidence": "exact",
                        }
                    },
                )

            author = source(
                "Synthetic author method",
                ("background " * 2_000)
                + "Sparse solver latency improved for warm-cache batched matrix workloads.",
            )
            client = source(
                "Synthetic client aim",
                "Reduce sparse solver latency in a recurring batch-processing workflow.",
            )
            proposal = proposals.create_proposal(
                session,
                project.id,
                title="Synthetic sparse-solver feasibility proposal",
                kind="applied_client_pilot",
                brief={
                    "client_question": "Could the selected sparse solver help this workflow?",
                    "aims": "reduce sparse solver latency\ncreate horticulture imagery",
                    "success_criteria": "Compare latency against the current baseline.",
                    "unanswered_questions": "Budget and schedule are unspecified.",
                },
            )
            proposals.add_source(session, proposal.id, source_id=author.id, collection="author")
            proposals.add_source(session, proposal.id, source_id=client.id, collection="client")
            proposals.index_passages(session, proposal.id)
            retrieval = proposals.retrieve(session, proposal.id, "sparse solver latency")
            matrix = proposals.generate_fit_matrix(
                session,
                proposal.id,
                idempotency_key="demo-fit",
                needs=["reduce sparse solver latency", "create horticulture imagery"],
            )
            proposals.generate_outline(session, proposal.id, idempotency_key="demo-outline")
            proposals.generate_draft(session, proposal.id, idempotency_key="demo-draft")
            version = proposals.save_version(
                session,
                proposal.id,
                name="v1",
                review_note="Synthetic workflow review.",
                expected_draft_revision=proposal.draft_revision,
                approve_all=True,
            )
            export = proposals.export_version(session, version.id, formats=["md", "html", "docx"])
            session.commit()
            print("simulated:", matrix["generation"]["simulated"])
            print("retrieval locators:", [hit["locator"] for hit in retrieval["results"]])
            print("fit statuses:", [row["fit_status"] for row in matrix["rows"]])
            print("version:", version.name)
            print("exports:", sorted(export["artifact_refs"]))
        finally:
            session.close()
            db.reset_engine_for_tests()
            config.get_settings.cache_clear()


if __name__ == "__main__":
    main()
