import os

import pytest

# Force offline fakes and an isolated DB per test session, before workbench imports settings.
os.environ["WB_PROVIDER_MODE"] = "fake"


@pytest.fixture()
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'test.sqlite3'}")
    from workbench import config, db

    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    db.create_all()
    factory = db.session_factory()
    s = factory()
    yield s
    s.close()
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()


@pytest.fixture()
def project(session):
    from workbench.services import research

    ws = research.create_workspace(session, "Test WS")
    proj = research.create_project(session, ws.id, "Test Project")
    session.commit()
    return proj
