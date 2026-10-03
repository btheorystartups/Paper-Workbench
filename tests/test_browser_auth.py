"""Offline browser-session, CSRF, and OIDC Authorization Code + PKCE tests."""

import base64
import hashlib
import json
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient


def _reset():
    from workbench import auth, config, db

    config.get_settings.cache_clear()
    auth._live_oidc_verifier.cache_clear()
    db.reset_engine_for_tests()


def _cookie_auth_env(monkeypatch, tmp_path):
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'browser-auth.sqlite3'}")
    monkeypatch.setenv("WB_PROVIDER_MODE", "fake")
    monkeypatch.setenv("WB_AUTH_REQUIRED", "true")
    monkeypatch.setenv("WB_AUTH_SECRET", "browser-test-secret-0123456789-abcdefgh")
    monkeypatch.setenv("WB_AUTH_ALLOW_REGISTRATION", "true")
    monkeypatch.setenv("WB_AUTH_COOKIE_SESSIONS_ENABLED", "true")
    monkeypatch.setenv("WB_AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("WB_OIDC_MODE", "disabled")


def _browser_oidc_env(monkeypatch, tmp_path):
    _cookie_auth_env(monkeypatch, tmp_path)
    monkeypatch.setenv("WB_OIDC_MODE", "live")
    monkeypatch.setenv("WB_OIDC_ISSUER", "https://identity.example/")
    monkeypatch.setenv("WB_OIDC_AUDIENCE", "paper-workbench-client")
    monkeypatch.setenv("WB_OIDC_JWKS_URL", "https://identity.example/.well-known/jwks.json")
    monkeypatch.setenv("WB_OIDC_BROWSER_ENABLED", "true")
    monkeypatch.setenv("WB_OIDC_CLIENT_ID", "paper-workbench-client")
    monkeypatch.setenv("WB_OIDC_AUTHORIZATION_URL", "https://identity.example/authorize")
    monkeypatch.setenv("WB_OIDC_TOKEN_URL", "https://identity.example/oauth/token")
    monkeypatch.setenv(
        "WB_OIDC_REDIRECT_URI", "https://paper-workbench.example/auth/oidc/callback"
    )
    monkeypatch.setenv("WB_OIDC_ALLOW_JIT_PROVISIONING", "true")


def test_password_cookie_session_requires_csrf(tmp_path, monkeypatch):
    _cookie_auth_env(monkeypatch, tmp_path)
    _reset()
    from workbench.main import app

    with TestClient(app) as client:
        created = client.post(
            "/auth/register",
            json={"name": "Browser User", "email": "browser@example.com", "password": "password123"},
        )
        assert created.status_code == 200
        login = client.post(
            "/auth/login",
            json={"email": "browser@example.com", "password": "password123"},
        )
        assert login.status_code == 200
        assert login.json()["token_type"] == "cookie"
        assert "access_token" not in login.json()
        assert client.get("/auth/me").status_code == 200

        blocked = client.post("/workspaces", json={"name": "No CSRF"})
        assert blocked.status_code == 403
        csrf = client.cookies.get("wb_csrf")
        copied_token = client.cookies.get("wb_session")
        allowed = client.post(
            "/workspaces",
            json={"name": "With CSRF"},
            headers={"X-CSRF-Token": csrf},
        )
        assert allowed.status_code == 200

        logout = client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
        assert logout.status_code == 200
        assert client.get("/auth/me").status_code == 401
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {copied_token}"}).status_code == 401
    _reset()


def test_oidc_pkce_flow_and_callback_are_state_and_nonce_bound(tmp_path, monkeypatch):
    _browser_oidc_env(monkeypatch, tmp_path)
    _reset()
    from workbench import auth
    from workbench.main import app

    with TestClient(app) as client:
        start = client.get("/auth/oidc/start", follow_redirects=False)
        assert start.status_code == 302
        query = parse_qs(urlparse(start.headers["location"]).query)
        assert query["code_challenge_method"] == ["S256"]
        flow_cookie = client.cookies.get("wb_oidc_flow")
        flow = auth.decode_oidc_browser_flow(flow_cookie, query["state"][0])
        expected_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(flow.code_verifier.encode()).digest()
        ).rstrip(b"=").decode()
        assert query["code_challenge"] == [expected_challenge]
        with pytest.raises(auth.AuthError, match="state mismatch"):
            auth.decode_oidc_browser_flow(flow_cookie, "wrong-state")

        id_token = json.dumps(
            {
                "iss": "https://identity.example/",
                "sub": "browser-user-1",
                "email": "oidc@example.com",
                "email_verified": True,
                "name": "OIDC User",
                "nonce": flow.nonce,
            }
        )
        monkeypatch.setattr(auth, "exchange_oidc_authorization_code", lambda *_: id_token)
        monkeypatch.setattr(
            auth,
            "get_oidc_verifier",
            lambda: auth.FakeOidcVerifier(issuer="https://identity.example/"),
        )
        callback = client.get(
            "/auth/oidc/callback",
            params={"code": "one-time-code", "state": flow.state},
            follow_redirects=False,
        )
        assert callback.status_code == 303
        assert callback.headers["location"] == "/ui/"
        assert client.get("/auth/me").json()["auth_method"] == "oidc"
        copied_token = client.cookies.get("wb_session")
        logout = client.post("/auth/logout", headers={"X-CSRF-Token": client.cookies.get("wb_csrf")})
        assert logout.status_code == 200
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {copied_token}"}).status_code == 401
    _reset()


def test_logout_revocation_survives_new_worker_and_preserves_other_sessions(tmp_path, monkeypatch):
    _cookie_auth_env(monkeypatch, tmp_path)
    _reset()
    from sqlalchemy import select

    from workbench import auth, db
    from workbench.main import app
    from workbench.models import RevokedAccessToken

    with TestClient(app) as client:
        client.post("/auth/register", json={"name": "Session test", "email": "sessions@example.com",
                                            "password": "password123"})
        credentials = {"email": "sessions@example.com", "password": "password123"}
        client.post("/auth/login", json=credentials)
        first = client.cookies.get("wb_session")
        alternate_encoding = first + "="
        assert auth.decode_access_token(alternate_encoding)["jti"] == auth.decode_access_token(first)["jti"]
        csrf = client.cookies.get("wb_csrf")
        assert client.post("/auth/logout").status_code == 403
        assert client.get("/auth/me").status_code == 200
        client.post("/auth/login", json=credentials)
        second = client.cookies.get("wb_session")
        assert first != second
        # Explicit bearer logout revokes exactly the selected token, not all user sessions.
        assert client.post("/auth/logout", headers={"Authorization": f"Bearer {first}"}).status_code == 200
        with db.session_factory()() as session:
            auth.revoke_access_token(session, first)  # idempotent duplicate service request
            session.commit()
            entries = session.scalars(select(RevokedAccessToken)).all()
            assert len(entries) == 1
            assert entries[0].token_hash == auth._session_hash(auth.decode_access_token(first))
        db.reset_engine_for_tests()  # no worker memory should be needed for revocation
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {first}"}).status_code == 401
        replay = client.get("/auth/me", headers={"Authorization": f"Bearer {alternate_encoding}"})
        assert replay.status_code == 401
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {second}"}).status_code == 200
        client.cookies.set("wb_session", first)
        client.cookies.set("wb_csrf", csrf)
        assert client.get("/auth/me").status_code == 401
        assert client.post("/workspaces", json={"name": "Blocked replay"},
                           headers={"X-CSRF-Token": csrf}).status_code == 401
    _reset()


def test_browser_oidc_configuration_is_fail_closed(tmp_path, monkeypatch):
    _browser_oidc_env(monkeypatch, tmp_path)
    monkeypatch.setenv("WB_OIDC_MODE", "disabled")
    _reset()
    from workbench import auth

    with pytest.raises(auth.AuthError, match="requires WB_OIDC_MODE=live"):
        auth.validate_auth_configuration()
    _reset()
