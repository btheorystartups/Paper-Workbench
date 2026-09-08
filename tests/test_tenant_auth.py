"""Adversarial coverage for workspace tenancy, OIDC boundaries, and API credentials."""

import json
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import select


@pytest.fixture()
def tenant_client(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'tenant.sqlite3'}")
    monkeypatch.setenv("WB_PROVIDER_MODE", "fake")
    monkeypatch.setenv("WB_AUTH_REQUIRED", "true")
    monkeypatch.setenv("WB_AUTH_ALLOW_REGISTRATION", "true")
    monkeypatch.setenv("WB_AUTH_SECRET", "tenant-test-secret-0123456789-abcdefghij")
    monkeypatch.setenv("WB_OIDC_MODE", "disabled")
    from fastapi.testclient import TestClient

    from workbench import config, db
    from workbench.main import app

    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    with TestClient(app) as client:
        yield client
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()


def _register_login(client, email: str) -> tuple[dict, str]:
    registered = client.post(
        "/auth/register",
        json={"name": email.split("@")[0], "email": email, "password": "password123"},
    )
    assert registered.status_code == 200, registered.text
    login = client.post(
        "/auth/login", json={"email": email, "password": "password123"}
    )
    assert login.status_code == 200, login.text
    return registered.json(), login.json()["access_token"]


def _workspace_project(client, token: str, suffix: str) -> tuple[dict, dict]:
    headers = {"Authorization": f"Bearer {token}"}
    workspace = client.post(
        "/workspaces", json={"name": f"Workspace {suffix}"}, headers=headers
    )
    assert workspace.status_code == 200, workspace.text
    project = client.post(
        "/projects",
        json={"workspace_id": workspace.json()["id"], "name": f"Project {suffix}"},
        headers=headers,
    )
    assert project.status_code == 200, project.text
    return workspace.json(), project.json()


def test_every_data_route_requires_auth_and_hides_cross_tenant_ids(tenant_client):
    client = tenant_client
    _user_a, token_a = _register_login(client, "a@example.com")
    _user_b, token_b = _register_login(client, "b@example.com")
    workspace_a, project_a = _workspace_project(client, token_a, "A")
    workspace_b, _project_b = _workspace_project(client, token_b, "B")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    created = client.post(
        f"/projects/{project_a['id']}/objects",
        json={"kind": "note", "title": "Tenant A only"},
        headers=headers_a,
    )
    assert created.status_code == 200, created.text
    object_id = created.json()["id"]

    assert client.get("/workspaces").status_code == 401
    assert client.get(f"/projects/{project_a['id']}/objects", headers=headers_b).status_code == 404
    assert client.post(f"/objects/{object_id}/accept", headers=headers_b).status_code == 404
    assert client.get(f"/objects/{object_id}/usage", headers=headers_b).status_code == 404
    assert client.get(
        f"/workspaces/{workspace_a['id']}/projects", headers=headers_b
    ).status_code == 404

    visible_a = client.get("/workspaces", headers=headers_a).json()
    visible_b = client.get("/workspaces", headers=headers_b).json()
    assert [row["id"] for row in visible_a] == [workspace_a["id"]]
    assert [row["id"] for row in visible_b] == [workspace_b["id"]]


def test_workspace_member_still_needs_project_membership(tenant_client):
    client = tenant_client
    user_a, token_a = _register_login(client, "tenant-owner@example.com")
    user_b, token_b = _register_login(client, "project-owner@example.com")
    workspace, project_a = _workspace_project(client, token_a, "Shared")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    added = client.post(
        f"/workspaces/{workspace['id']}/members",
        json={"user_id": user_b["id"], "role": "member"},
        headers=headers_a,
    )
    assert added.status_code == 200, added.text
    project_b = client.post(
        "/projects",
        json={"workspace_id": workspace["id"], "name": "Member project"},
        headers=headers_b,
    )
    assert project_b.status_code == 200, project_b.text

    assert client.get(
        f"/projects/{project_a['id']}/objects", headers=headers_b
    ).status_code == 404
    # The workspace owner is the tenant administrator and can recover/administer project B.
    assert client.get(
        f"/projects/{project_b.json()['id']}/objects", headers=headers_a
    ).status_code == 200
    assert user_a["id"] != user_b["id"]


def test_scoped_api_key_is_hashed_bound_and_revocable(tenant_client):
    client = tenant_client
    _user, token = _register_login(client, "key-owner@example.com")
    workspace, project = _workspace_project(client, token, "Keys")
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        f"/workspaces/{workspace['id']}/api-keys",
        json={"name": "read automation", "scopes": ["read"]},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    raw_key = body["api_key"]
    assert raw_key.startswith("wbk_")
    assert raw_key not in json.dumps(
        client.get(f"/workspaces/{workspace['id']}/api-keys", headers=headers).json()
    )

    from workbench import db
    from workbench.models import ApiCredential, AuditEvent

    with db.session_factory()() as session:
        stored = session.scalar(select(ApiCredential).where(ApiCredential.id == body["id"]))
        assert stored is not None
        assert stored.key_hash != raw_key
        assert len(stored.key_hash) == 64
        assert stored.workspace_id == workspace["id"]
        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.object_type == "api_credential",
                AuditEvent.object_id == stored.id,
                AuditEvent.action == "create_api_credential",
            )
        )
        assert audit is not None
        assert raw_key not in json.dumps(audit.detail)

    key_headers = {"Authorization": f"Bearer {raw_key}"}
    assert client.get(
        f"/projects/{project['id']}/objects", headers=key_headers
    ).status_code == 200
    other_workspace, other_project = _workspace_project(client, token, "Other tenant")
    key_workspaces = client.get("/workspaces", headers=key_headers).json()
    assert [row["id"] for row in key_workspaces] == [workspace["id"]]
    assert other_workspace["id"] != workspace["id"]
    assert client.get(
        f"/projects/{other_project['id']}/objects", headers=key_headers
    ).status_code == 404
    denied = client.post(
        f"/projects/{project['id']}/objects",
        json={"kind": "note", "title": "No write scope"},
        headers=key_headers,
    )
    assert denied.status_code == 403

    revoked = client.post(f"/api-keys/{body['id']}/revoke", headers=headers)
    assert revoked.status_code == 200
    assert client.get(
        f"/projects/{project['id']}/objects", headers=key_headers
    ).status_code == 401


def test_registration_is_fail_closed_when_not_explicitly_enabled(
    tenant_client, monkeypatch
):
    from workbench import config

    monkeypatch.setenv("WB_AUTH_ALLOW_REGISTRATION", "false")
    config.get_settings.cache_clear()
    response = tenant_client.post(
        "/auth/register",
        json={"name": "Closed", "email": "closed@example.com", "password": "password123"},
    )
    assert response.status_code == 403


def test_first_user_bootstrap_requires_env_token_and_is_one_time(
    tenant_client, monkeypatch
):
    from workbench import config

    bootstrap = "first-user-bootstrap-token-0123456789"
    monkeypatch.setenv("WB_AUTH_ALLOW_REGISTRATION", "false")
    monkeypatch.setenv("WB_AUTH_BOOTSTRAP_TOKEN", bootstrap)
    config.get_settings.cache_clear()
    body = {
        "name": "Initial owner",
        "email": "initial@example.com",
        "password": "password123",
    }
    first = tenant_client.post(
        "/auth/register", json=body, headers={"X-Workbench-Bootstrap": bootstrap}
    )
    assert first.status_code == 200
    second = tenant_client.post(
        "/auth/register",
        json={**body, "email": "second@example.com"},
        headers={"X-Workbench-Bootstrap": bootstrap},
    )
    assert second.status_code == 403


def test_fake_oidc_is_refused_at_enforced_auth_boundary(session, monkeypatch):
    monkeypatch.setenv("WB_AUTH_REQUIRED", "true")
    monkeypatch.setenv("WB_AUTH_SECRET", "oidc-test-secret-0123456789-abcdefghij")
    monkeypatch.setenv("WB_OIDC_MODE", "fake")
    from workbench import auth, config

    config.get_settings.cache_clear()
    with pytest.raises(auth.AuthError, match="fake OIDC is refused"):
        auth.login_oidc(session, json.dumps({"sub": "attacker"}))
    config.get_settings.cache_clear()


def test_unverified_oidc_email_cannot_link_existing_account(session, monkeypatch):
    monkeypatch.setenv("WB_OIDC_MODE", "fake")
    monkeypatch.setenv("WB_OIDC_ALLOW_EMAIL_LINKING", "true")
    monkeypatch.setenv("WB_OIDC_ALLOW_JIT_PROVISIONING", "true")
    from workbench import auth, config

    config.get_settings.cache_clear()
    auth.register_local_user(
        session, name="Existing", email="same@example.com", password="password123"
    )
    token = json.dumps(
        {"sub": "foreign-sub", "email": "same@example.com", "email_verified": False}
    )
    with pytest.raises(auth.AuthError, match="pre-link required"):
        auth.login_oidc(session, token)
    config.get_settings.cache_clear()


def test_oidc_subject_is_qualified_by_issuer(session, monkeypatch):
    from workbench import auth, config
    from workbench.models import FederatedIdentity

    monkeypatch.setenv("WB_OIDC_MODE", "fake")
    monkeypatch.setenv("WB_OIDC_ALLOW_JIT_PROVISIONING", "true")
    monkeypatch.setenv("WB_AUTH_SECRET", "oidc-test-secret-0123456789-abcdefghij")
    monkeypatch.setenv("WB_OIDC_ISSUER", "https://issuer-a.example")
    config.get_settings.cache_clear()
    user_a, _ = auth.login_oidc(session, json.dumps({"sub": "shared-sub"}))

    monkeypatch.setenv("WB_OIDC_ISSUER", "https://issuer-b.example")
    config.get_settings.cache_clear()
    user_b, _ = auth.login_oidc(session, json.dumps({"sub": "shared-sub"}))

    identities = list(session.scalars(select(FederatedIdentity)))
    assert user_a.id != user_b.id
    assert {(row.issuer, row.subject) for row in identities} == {
        ("https://issuer-a.example", "shared-sub"),
        ("https://issuer-b.example", "shared-sub"),
    }
    config.get_settings.cache_clear()


def test_oidc_tenant_claim_maps_to_workspace_membership(session, monkeypatch):
    monkeypatch.setenv("WB_OIDC_MODE", "fake")
    monkeypatch.setenv("WB_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("WB_OIDC_TENANT_CLAIM", "org_id")
    monkeypatch.setenv("WB_OIDC_ALLOW_JIT_PROVISIONING", "true")
    monkeypatch.setenv("WB_OIDC_ALLOW_JIT_MEMBERSHIP", "true")
    monkeypatch.setenv("WB_AUTH_SECRET", "oidc-test-secret-0123456789-abcdefghij")
    from workbench import auth, config
    from workbench.models import OidcWorkspaceBinding, WorkspaceMember
    from workbench.services import research

    config.get_settings.cache_clear()
    workspace = research.create_workspace(session, "Bound tenant")
    session.add(
        OidcWorkspaceBinding(
            workspace_id=workspace.id,
            issuer="https://issuer.example",
            tenant_key="org-42",
            default_role="member",
        )
    )
    session.flush()

    user, token = auth.login_oidc(
        session,
        json.dumps({"sub": "subject-42", "org_id": "org-42"}),
    )
    claims = auth.decode_access_token(token)
    membership = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    assert claims["wid"] == workspace.id
    assert membership is not None and membership.role == "member"
    config.get_settings.cache_clear()


def test_live_oidc_configuration_rejects_insecure_urls_and_symmetric_algorithms(
    monkeypatch,
):
    monkeypatch.setenv("WB_OIDC_MODE", "live")
    monkeypatch.setenv("WB_OIDC_ISSUER", "http://issuer.example")
    monkeypatch.setenv("WB_OIDC_AUDIENCE", "paper-workbench")
    monkeypatch.setenv("WB_OIDC_JWKS_URL", "https://issuer.example/jwks")
    from workbench import auth, config

    config.get_settings.cache_clear()
    with pytest.raises(auth.AuthError, match="absolute HTTPS"):
        auth.get_oidc_verifier()

    monkeypatch.setenv("WB_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("WB_OIDC_ALLOWED_ALGORITHMS", "HS256")
    config.get_settings.cache_clear()
    with pytest.raises(auth.AuthError, match="asymmetric"):
        auth.get_oidc_verifier()
    config.get_settings.cache_clear()


def test_live_oidc_verifier_checks_signature_issuer_audience_and_claim_types():
    import jwt
    rsa = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")

    from workbench import auth

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class StaticJwkClient:
        def get_signing_key_from_jwt(self, _token):
            return SimpleNamespace(key=private_key.public_key())

    verifier = auth.OidcVerifier(
        issuer="https://issuer.example",
        audience="paper-workbench",
        jwks_url="https://issuer.example/jwks",
        algorithms=("RS256",),
        tenant_claim="org_id",
        jwk_client=StaticJwkClient(),
    )
    now = int(time.time())
    payload = {
        "iss": "https://issuer.example",
        "sub": "subject-1",
        "aud": "paper-workbench",
        "iat": now,
        "exp": now + 300,
        "email": "USER@EXAMPLE.COM",
        "email_verified": "false",
        "org_id": 42,
    }
    token = jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "test"})
    claims = verifier.verify(token)
    assert claims.email == "user@example.com"
    assert claims.email_verified is False
    assert claims.tenant_key == "42"

    payload["aud"] = "wrong-audience"
    wrong_audience = jwt.encode(
        payload, private_key, algorithm="RS256", headers={"kid": "test"}
    )
    with pytest.raises(auth.AuthError, match="OIDC verification failed"):
        verifier.verify(wrong_audience)
