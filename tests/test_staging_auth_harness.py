"""Offline checks of the operator harness's credential transport and scoped cleanup."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def _harness():
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_staging_auth.py"
    spec = importlib.util.spec_from_file_location("staging_auth_harness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_credentials_use_stdin_and_logout_clears_cookie_jar(monkeypatch):
    module = _harness()
    client = object.__new__(module.PreviewClient)
    client.node = "node"
    client.cli = Path("cli.js")
    client.deployment = module.DEPLOYMENT
    client.cookies = {"wb_session": "synthetic-session", "wb_csrf": "synthetic-csrf"}

    def run(argv, **kwargs):
        assert "synthetic-session" not in " ".join(argv)
        assert "synthetic-password" not in " ".join(argv)
        stdin = kwargs["input"].decode()
        assert "synthetic-session" in stdin
        data_line = next(line for line in stdin.splitlines() if line.startswith("data = "))
        assert json.loads(json.loads(data_line.removeprefix("data = ")))["password"] == "synthetic-password"
        return SimpleNamespace(returncode=0, stdout=(
            b"HTTP/1.1 100 Continue\r\n\r\nHTTP/2 200\r\n"
            b'Set-Cookie: wb_session=""; Max-Age=0; Path=/\r\n'
            b'Set-Cookie: wb_csrf=""; Max-Age=0; Path=/\r\n\r\n{"authenticated": false}'
        ))

    monkeypatch.setattr(module.subprocess, "run", run)
    status, _, body = client.request("/auth/logout", "POST", {"password": "synthetic-password"})
    assert status == 200 and body == {"authenticated": False}
    assert client.cookies == {}


def test_cleanup_is_exact_run_scoped_and_repeatable():
    from sqlalchemy import create_engine, insert, select

    from workbench.models import Base, User, Workspace, WorkspaceMember

    module = _harness()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    target = module.fixture_ids("target-run")
    unrelated = module.fixture_ids("unrelated-run")
    with engine.begin() as connection:
        for ids in (target, unrelated):
            for i in range(2):
                connection.execute(insert(User).values(id=ids["users"][i], name="synthetic"))
                connection.execute(insert(Workspace).values(id=ids["workspaces"][i], name="synthetic"))
                connection.execute(insert(WorkspaceMember).values(
                    id=ids["memberships"][i], user_id=ids["users"][i],
                    workspace_id=ids["workspaces"][i], role="owner"))
    first = module.cleanup(engine, target)
    assert first["deleted"] == {"audit_events": 0, "workspace_members": 2, "workspaces": 2, "users": 2}
    assert all(value == 0 for value in module.cleanup(engine, target)["deleted"].values())
    with engine.connect() as connection:
        assert set(connection.scalars(select(User.id))) == set(unrelated["users"])
        assert set(connection.scalars(select(Workspace.id))) == set(unrelated["workspaces"])
    engine.dispose()


def test_replayed_session_is_an_explicit_unresolved_finding():
    module = _harness()
    report = {"status": "passed", "session_replay_after_logout": [{"user": 0, "status": 200}]}
    module.classify_report(report)
    assert report["status"] == "passed_with_findings"
    assert report["findings"][0]["state"] == "unresolved"
    report["status"] = "failed"
    module.classify_report(report)
    assert report["status"] == "failed"


def test_manuscript_cleanup_removes_only_its_fixture_graph_and_revocations(session):
    from sqlalchemy import select

    from workbench.models import Project, RevokedAccessToken, Turn, User, Workspace, WorkspaceMember, utcnow
    from workbench.services import authoring, dialogue, research

    module = _harness()
    target = module.fixture_ids("writing-target")
    other = module.fixture_ids("writing-other")
    kept_project = None
    for ids, token_hash in ((target, "a" * 64), (other, "b" * 64)):
        session.add_all([
            User(id=ids["users"][0], name="Synthetic"),
            Workspace(id=ids["workspaces"][0], name="Synthetic"),
        ])
        session.flush()
        session.add(WorkspaceMember(id=ids["memberships"][0], user_id=ids["users"][0],
                                    workspace_id=ids["workspaces"][0], role="owner"))
        project = research.create_project(session, ids["workspaces"][0], "Synthetic")
        manuscript = authoring.create_manuscript(session, project.id, title="Synthetic")
        section = authoring.add_section(session, manuscript.id, heading="Discussion", text="Synthetic")
        thread = dialogue.create_thread(session, project.id, title="Synthetic",
                                         manuscript_id=manuscript.id, section_id=section.id)
        dialogue.post_user_turn(session, thread.id, "revise: synthetic revision")
        session.add(RevokedAccessToken(token_hash=token_hash, expires_at=utcnow()))
        if ids is other:
            kept_project = project.id
    session.commit()
    result = module.cleanup(session.bind, target, ["a" * 64], manuscript=True)
    assert result["remaining"] == 0
    assert result["deleted"]["revoked_access_tokens"] == 1
    repeated = module.cleanup(session.bind, target, ["a" * 64], manuscript=True)
    assert all(n == 0 for n in repeated["deleted"].values())
    with session.bind.connect() as connection:
        assert set(connection.scalars(select(Project.id))) == {kept_project}
        assert len(connection.scalars(select(Turn.id)).all()) == 2
        assert set(connection.scalars(select(RevokedAccessToken.token_hash))) == {"b" * 64}
