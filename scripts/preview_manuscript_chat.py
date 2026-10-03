"""Run a loopback-only synthetic writing demo in a disposable database, always offline.

Run with the worktree's src on PYTHONPATH. No existing databases or dotenv files are read.
Stop with Ctrl+C to close the server and remove its temporary synthetic database.
"""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

from workbench import config, db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8879)
    args = parser.parse_args()
    config._load_dotenv = lambda: None
    with TemporaryDirectory(prefix="wb-synthetic-chat-") as temporary:
        database_url = f"sqlite:///{Path(temporary) / 'demo.sqlite3'}"
        settings = config.Settings(
            _env_ignore_empty=True,
            provider_mode="fake",
            database_url=database_url,
            data_dir=str(Path(temporary) / "artifacts"),
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
        from workbench.services import authoring, dialogue, research
        from workbench.vocab import SourceAccess

        with db.session_factory()() as session:
            workspace = research.create_workspace(session, "Synthetic writing demo")
            project = research.create_project(session, workspace.id, "Pilot experiment")
            source = research.register_source(
                session,
                project.id,
                title="Synthetic pilot observations",
                access=SourceAccess.FULL_TEXT_USER_SUPPLIED,
                acquisition="Invented exclusively for interface verification",
            )
            excerpt = research.capture_excerpt(
                session,
                source.id,
                text="The pilot measured a 12% improvement in ten runs.",
                locator="Synthetic report, page 3",
            )
            claim = research.create_claim(
                session,
                project.id,
                text="The pilot measured a 12% improvement.",
                support="external_source",
                excerpt_ids=[excerpt.id],
            )
            manuscript = authoring.create_manuscript(session, project.id, title="Interpreting a pilot result")
            section = authoring.add_section(
                session,
                manuscript.id,
                heading="Discussion",
                purpose="Interpret the pilot without generalizing beyond it.",
                text="The pilot measured a 12% improvement across ten runs. "
                "This small experiment does not establish general applicability.",
                claim_ids=[claim.id],
                word_budget=300,
            )
            thread = dialogue.create_thread(
                session,
                project.id,
                title="Discussion",
                mode="act",
                manuscript_id=manuscript.id,
                section_id=section.id,
            )
            session.commit()
            print(
                f"http://127.0.0.1:{args.port}/ui/#/project/{project.id}/manuscripts/{manuscript.id}/{thread.id}",
                flush=True,
            )
        from workbench.main import app

        try:
            uvicorn.run(app, host="127.0.0.1", port=args.port)
        finally:
            db.reset_engine_for_tests()


if __name__ == "__main__":
    main()
