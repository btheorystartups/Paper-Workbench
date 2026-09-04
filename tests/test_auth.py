"""Hardened auth: password login, JWT, OIDC (fake), api-key, and role enforcement."""

import json

import pytest


@pytest.fixture()
def auth_env(monkeypatch):
    monkeypatch.setenv("WB_AUTH_SECRET", "test-secret-please-change-0123456789")
    from workbench import config

    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_password_hash_roundtrip(auth_env):
    from workbench import auth

    h = auth.hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert auth.verify_password("correct horse battery staple", h)
    assert not auth.verify_password("wrong", h)


def test_register_login_jwt(session, auth_env):
    from workbench import auth

    user = auth.register_local_user(
        session, name="Brian", email="b@example.com", password="hunter2hunter2"
    )
    assert user.password_hash and user.password_hash != "hunter2hunter2"
    _u, token = auth.login_password(session, email="b@example.com", password="hunter2hunter2")
    assert auth.decode_token(token) == user.id
    with pytest.raises(auth.AuthError):
        auth.login_password(session, email="b@example.com", password="nope")


def test_token_expiry(session, auth_env):
    from workbench import auth

    user = auth.register_local_user(
        session, name="X", email="x@example.com", password="password123"
    )
    expired = auth.issue_token(user.id, ttl_minutes=-1)
    with pytest.raises(auth.AuthError, match="invalid token"):
        auth.decode_token(expired)


def test_enforced_auth_requires_real_secret(monkeypatch):
    monkeypatch.setenv("WB_AUTH_REQUIRED", "true")
    monkeypatch.setenv("WB_AUTH_SECRET", "dev-insecure-secret")
    from workbench import auth, config

    config.get_settings.cache_clear()
    with pytest.raises(auth.AuthError, match="WB_AUTH_SECRET"):
        auth.issue_token("someone")
    config.get_settings.cache_clear()


def test_oidc_fake_flow_links_account(session, auth_env):
    from workbench import auth

    id_token = json.dumps(
        {"sub": "oidc|123", "email": "fed@example.com", "name": "Fed User",
         "email_verified": True}
    )
    user, token = auth.login_oidc(session, id_token)
    assert user.oidc_subject == "oidc|123"
    assert user.email_verified is True
    assert auth.decode_token(token) == user.id
    # second login with same subject reuses the account
    user2, _ = auth.login_oidc(session, id_token)
    assert user2.id == user.id


def test_principal_from_bearer_paths(session, auth_env):
    from workbench import auth
    from workbench.services import security

    # no token, auth not required â†’ default local user
    local = auth.principal_from_bearer(session, None)
    assert local.name == "local-user"
    # api-key path
    u = security.create_user(session, "Keyed")
    assert auth.principal_from_bearer(session, u.api_key).id == u.id
    # jwt path
    token = auth.issue_token(u.id)
    assert auth.principal_from_bearer(session, token).id == u.id
    # garbage
    with pytest.raises(auth.AuthError):
        auth.principal_from_bearer(session, "not-a-real-token")


def test_no_token_rejected_when_required(session, monkeypatch):
    monkeypatch.setenv("WB_AUTH_REQUIRED", "true")
    monkeypatch.setenv("WB_AUTH_SECRET", "real-secret-0123456789-abcdefghij")
    from workbench import auth, config

    config.get_settings.cache_clear()
    with pytest.raises(auth.AuthError, match="authentication required"):
        auth.principal_from_bearer(session, None)
    config.get_settings.cache_clear()


def test_role_enforcement_via_api(tmp_path, monkeypatch):
    """With auth on, a reviewer cannot create objects (needs coauthor); owner can."""
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'auth.sqlite3'}")
    monkeypatch.setenv("WB_PROVIDER_MODE", "fake")
    monkeypatch.setenv("WB_AUTH_REQUIRED", "true")
    monkeypatch.setenv("WB_AUTH_SECRET", "real-secret-0123456789-abcdefghij")
    from fastapi.testclient import TestClient

    from workbench import config, db

    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    from workbench.main import app

    with TestClient(app) as client:
        # bootstrap: register owner + reviewer, get tokens
        owner = client.post(
            "/auth/register",
            json={"name": "Owner", "email": "o@e.com", "password": "password123"},
        ).json()
        owner_tok = client.post(
            "/auth/login", json={"email": "o@e.com", "password": "password123"}
        ).json()["access_token"]
        rev = client.post(
            "/auth/register",
            json={"name": "Rev", "email": "r@e.com", "password": "password123"},
        ).json()
        rev_tok = client.post(
            "/auth/login", json={"email": "r@e.com", "password": "password123"}
        ).json()["access_token"]

        oh = {"Authorization": f"Bearer {owner_tok}"}
        rh = {"Authorization": f"Bearer {rev_tok}"}

        # unauthenticated request is rejected
        assert client.get("/auth/me").status_code == 401

        ws = client.post("/workspaces", json={"name": "W"}, headers=oh).json()
        project = client.post(
            "/projects", json={"workspace_id": ws["id"], "name": "P"}, headers=oh
        ).json()
        # grace mode ended once we add members; make owner the owner, reviewer a reviewer
        client.post(
            f"/projects/{project['id']}/members",
            json={"user_id": owner["id"], "role": "owner"}, headers=oh,
        )
        client.post(
            f"/projects/{project['id']}/members",
            json={"user_id": rev["id"], "role": "reviewer"}, headers=oh,
        )
        # reviewer cannot create an object
        forbidden = client.post(
            f"/projects/{project['id']}/objects",
            json={"kind": "note", "title": "sneaky"}, headers=rh,
        )
        assert forbidden.status_code == 403
        # owner can
        ok = client.post(
            f"/projects/{project['id']}/objects",
            json={"kind": "note", "title": "fine"}, headers=oh,
        )
        assert ok.status_code == 200

    db.reset_engine_for_tests()
    config.get_settings.cache_clear()
