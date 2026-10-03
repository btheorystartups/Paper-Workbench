"""Run a loopback-only, fake-provider proposal demo in a disposable database.

No dotenv file, user database, client source, or live model is read. Stop with Ctrl+C
to close the server and discard the synthetic data.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from workbench import config, db, storage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8878)
    args = parser.parse_args()
    config._load_dotenv = lambda: None
    with TemporaryDirectory(prefix="wb-synthetic-proposal-") as temporary:
        root = Path(temporary)
        database_url = f"sqlite:///{root / 'proposal-demo.sqlite3'}"
        settings = config.Settings(
            _env_ignore_empty=True,
            provider_mode="fake",
            database_url=database_url,
            data_dir=str(root / "artifacts"),
            deployment_mode="local",
            auth_required=False,
            oidc_mode="disabled",
            oidc_browser_enabled=False,
            run_migrations_on_startup=False,
            artifact_storage_backend="local",
        )
        config.get_settings = lambda: settings
        db.get_settings = lambda: settings
        db.runtime_database_url = lambda: database_url
        db.migration_database_url = lambda: database_url
        db.reset_engine_for_tests()
        db.create_all()
        from workbench.services import proposals, research
        from workbench.vocab import SourceAccess

        with db.session_factory()() as session:
            workspace = research.create_workspace(session, "Synthetic proposal workspace")
            project = research.create_project(session, workspace.id, "Synthetic sparse-solver pilot")

            def source(title: str, text: str):
                snapshot = storage.store_content(
                    text.encode("utf-8"),
                    filename="synthetic-extracted.txt",
                    namespace="preview/proposal",
                    content_type="text/plain; charset=utf-8",
                )
                return research.register_source(
                    session,
                    project.id,
                    title=title,
                    access=SourceAccess.FULL_TEXT_USER_SUPPLIED,
                    acquisition="invented exclusively for interface verification",
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
            proposals.generate_fit_matrix(
                session,
                proposal.id,
                idempotency_key="preview-fit",
                needs=["reduce sparse solver latency", "create horticulture imagery"],
            )
            proposals.generate_outline(session, proposal.id, idempotency_key="preview-outline")
            proposals.generate_draft(session, proposal.id, idempotency_key="preview-draft")
            session.commit()
            print(
                f"http://127.0.0.1:{args.port}/ui/#/project/{project.id}/proposals/{proposal.id}",
                flush=True,
            )
        from workbench.main import app

        try:
            uvicorn.run(app, host="127.0.0.1", port=args.port)
        finally:
            db.reset_engine_for_tests()


if __name__ == "__main__":
    main()
