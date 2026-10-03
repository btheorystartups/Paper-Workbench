"""Authorized, temporary two-tenant Preview cookie-auth smoke; secrets stay in memory.

Run via vercel env run from a dotenv-free directory with the existing project linkage.
Only --execute creates fixtures; --cleanup-only repeats exact-run cleanup after interruption.
Neither mode changes registration, OIDC, provider configuration, or database schema.
"""

import argparse
import io
import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from email.parser import BytesParser
from http.cookies import SimpleCookie
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PROJECT = "prj_a4tgpf6rsmYp7H3JroXUH4x6ERk3"
DEPLOYMENT = "dpl_BoCfTGBdWq1DwxoHu8zBMbLZKGjB"
DATABASE_HOST = "ep-fragrant-violet-avjxe9qt-pooler.c-11.us-east-1.aws.neon.tech"
REVISION = "a91d4e7b620f"


class SmokeFailure(Exception):
    """Only constant check labels, never response bodies or exception details."""


def require(condition, label):
    if not condition:
        raise SmokeFailure(label)


def curl_config(method, body=None, cookies=None, headers=None):
    """curl config quoting, passed on stdin rather than argv or a credential file."""
    lines = [f"request = {json.dumps(method)}"]
    combined = dict(headers or {})
    if cookies:
        combined["Cookie"] = "; ".join(f"{key}={value}" for key, value in cookies.items())
    if body is not None:
        combined["Content-Type"] = "application/json"
        lines.append(f"data = {json.dumps(json.dumps(body))}")
    for key, value in combined.items():
        require(not any(char in key + value for char in "\r\n"), "header_control_character")
        lines.append(f"header = {json.dumps(f'{key}: {value}')}")
    return "\n".join(lines) + "\n"


def parse_response(raw):
    """Parse curl --include output, including informational/proxy header blocks."""
    stream = io.BytesIO(raw)
    while True:
        status_line = stream.readline().decode("ascii").strip()
        require(status_line.startswith("HTTP/"), "missing_http_status")
        status = int(status_line.split()[1])
        lines = []
        while (line := stream.readline()) not in {b"\r\n", b"\n", b""}:
            lines.append(line)
        headers = BytesParser().parsebytes(b"".join(lines))
        if status < 200 or "connection established" in status_line.lower():
            continue
        return status, headers, json.loads(stream.read())


class PreviewClient:
    def __init__(self, deployment=None):
        self.deployment = deployment or DEPLOYMENT
        command = shutil.which("vercel")
        self.node = shutil.which("node")
        require(command is not None and self.node is not None, "cli_unavailable")
        self.cli = Path(command).parent / "node_modules" / "vercel" / "dist" / "index.js"
        require(self.cli.is_file(), "cli_entrypoint_unavailable")
        self.cookies = {}

    def request(self, path, method="GET", body=None, headers=None):
        result = subprocess.run(
            [self.node, str(self.cli), "curl", path, "--deployment", self.deployment,
             "--", "--silent", "--show-error", "--max-time", "30", "--include", "--config", "-"],
            input=curl_config(method, body, self.cookies, headers).encode(),
            capture_output=True, timeout=60, check=False,
        )
        require(result.returncode == 0, "request_command_failed")
        status, response_headers, payload = parse_response(result.stdout)
        for value in response_headers.get_all("Set-Cookie", []):
            parsed = SimpleCookie()
            parsed.load(value)
            for key, morsel in parsed.items():
                if morsel["max-age"] == "0":
                    self.cookies.pop(key, None)
                else:
                    self.cookies[key] = morsel.value
        return status, response_headers, payload


def fixture_ids(run_id):
    return {
        kind: [uuid5(NAMESPACE_URL, f"wb-staging-auth:{run_id}:{kind}:{i}").hex for i in range(2)]
        for kind in ("users", "workspaces", "memberships")
    }


def classify_report(report):
    """Keep successful cookie/logout checks distinct from a failed revocation probe."""
    report["findings"] = []
    if any(item["status"] == 200 for item in report["session_replay_after_logout"]):
        report["findings"].append({
            "code": "session_replay_after_logout",
            "state": "unresolved",
            "detail": "Logout clears cookies but does not revoke the copied server session token.",
        })
        if report["status"] == "passed":
            report["status"] = "passed_with_findings"
    return report


def cleanup(engine, ids, revocation_hashes=None, manuscript=False):
    from sqlalchemy import delete, func, or_, select

    from workbench.models import (
        AuditEvent,
        Claim,
        ClaimEvidence,
        Edge,
        Excerpt,
        Project,
        ProjectMember,
        ProposedAction,
        ResearchObject,
        RevokedAccessToken,
        Source,
        Thread,
        Turn,
        UsageEvent,
        User,
        Workspace,
        WorkspaceMember,
    )

    predicates = [
        (AuditEvent, AuditEvent.workspace_id.in_(ids["workspaces"])),
        (WorkspaceMember, or_(WorkspaceMember.workspace_id.in_(ids["workspaces"]),
                             WorkspaceMember.user_id.in_(ids["users"]))),
        (Workspace, Workspace.id.in_(ids["workspaces"])),
        (User, User.id.in_(ids["users"])),
    ]
    if revocation_hashes:
        predicates.insert(0, (RevokedAccessToken, RevokedAccessToken.token_hash.in_(revocation_hashes)))
    if manuscript:
        projects = select(Project.id).where(Project.workspace_id.in_(ids["workspaces"]))
        threads = select(Thread.id).where(Thread.project_id.in_(projects))
        sources = select(Source.id).where(Source.project_id.in_(projects))
        claims = select(Claim.id).where(Claim.project_id.in_(projects))
        predicates = [
            (ProposedAction, ProposedAction.thread_id.in_(threads)),
            (Turn, Turn.thread_id.in_(threads)),
            (Thread, Thread.project_id.in_(projects)),
            (ClaimEvidence, ClaimEvidence.claim_id.in_(claims)),
            (Excerpt, Excerpt.source_id.in_(sources)),
            (Claim, Claim.project_id.in_(projects)),
            (Edge, Edge.project_id.in_(projects)),
            (ResearchObject, ResearchObject.project_id.in_(projects)),
            (Source, Source.project_id.in_(projects)),
            (UsageEvent, UsageEvent.project_id.in_(projects)),
            (ProjectMember, ProjectMember.project_id.in_(projects)),
            (Project, Project.workspace_id.in_(ids["workspaces"])),
        ] + predicates
    counts = {}
    with engine.begin() as connection:
        for model, predicate in predicates:
            counts[model.__tablename__] = connection.execute(delete(model).where(predicate)).rowcount
        for model, predicate in predicates:
            require(connection.scalar(select(func.count()).select_from(model).where(predicate)) == 0,
                    "cleanup_not_empty")
    return {"deleted": counts, "remaining": 0}


def run_checks(report, ids, emails, passwords, *, checkpoint=lambda: None, manuscript=False,
               require_revocation=False):
    clients = [PreviewClient(), PreviewClient()]

    def check(client, label, path, expected, method="GET", body=None, headers=None):
        status, response_headers, payload = client.request(path, method, body, headers)
        report["checks"].append({"check": label, "status": status, "passed": status == expected})
        print(json.dumps({"check": label, "status": status}), flush=True)
        require(status == expected, label)
        return response_headers, payload

    for i, client in enumerate(clients):
        body = {"email": emails[i], "password": passwords[i]}
        check(client, f"user_{i}_wrong_password", "/auth/login", 401, "POST",
              {**body, "password": "intentionally-wrong-synthetic-password"})
        headers, payload = check(client, f"user_{i}_login", "/auth/login", 200, "POST", body)
        require(payload.get("authenticated") is True and "access_token" not in payload,
                "login_token_body_exposure")
        cookies = SimpleCookie()
        for header in headers.get_all("Set-Cookie", []):
            cookies.load(header)
        require("wb_session" in cookies and "wb_csrf" in cookies, "login_cookies_missing")
        require(bool(cookies["wb_session"]["secure"]) and bool(cookies["wb_session"]["httponly"])
                and cookies["wb_session"]["samesite"].lower() == "lax", "session_cookie_flags")
        require(bool(cookies["wb_csrf"]["secure"]) and not cookies["wb_csrf"]["httponly"],
                "csrf_cookie_flags")
        if require_revocation:
            import jwt

            from workbench.auth import _session_hash

            claims = jwt.decode(client.cookies["wb_session"], options={"verify_signature": False})
            require(claims.get("sub") == ids["users"][i], "unexpected_session_subject")
            report.setdefault("revocation_hashes", []).append(_session_hash(claims))
            checkpoint()  # hashes only, before logout; allows exact cleanup after interruption
        _, me = check(client, f"user_{i}_identity", "/auth/me", 200)
        require(me.get("id") == ids["users"][i] and me.get("auth_method") == "password",
                "identity_mismatch")
        _, workspaces = check(client, f"user_{i}_workspace_list", "/workspaces", 200)
        require([row["id"] for row in workspaces] == [ids["workspaces"][i]], "tenant_list_leak")

    for i, client in enumerate(clients):
        own, other = ids["workspaces"][i], ids["workspaces"][1 - i]
        membership = {"user_id": ids["users"][i], "role": "owner"}
        own_path = f"/workspaces/{own}/members"
        csrf = client.cookies["wb_csrf"]
        check(client, f"user_{i}_csrf_missing", own_path, 403, "POST", membership)
        check(client, f"user_{i}_csrf_wrong", own_path, 403, "POST", membership,
              {"X-CSRF-Token": "incorrect-synthetic-csrf"})
        original_csrf = client.cookies["wb_csrf"]
        client.cookies["wb_csrf"] = clients[1 - i].cookies["wb_csrf"]
        try:
            check(client, f"user_{i}_csrf_other_session", own_path, 403, "POST", membership,
                  {"X-CSRF-Token": client.cookies["wb_csrf"]})
        finally:
            client.cookies["wb_csrf"] = original_csrf
        check(client, f"user_{i}_csrf_valid", own_path, 200, "POST", membership,
              {"X-CSRF-Token": csrf})
        check(client, f"user_{i}_own_tenant_read", own_path, 200)
        check(client, f"user_{i}_other_tenant_read", f"/workspaces/{other}/members", 404)
        check(client, f"user_{i}_other_tenant_projects", f"/workspaces/{other}/projects", 404)
        check(client, f"user_{i}_other_tenant_write", f"/workspaces/{other}/members", 404,
              "POST", membership, {"X-CSRF-Token": csrf})
        check(client, f"user_{i}_other_tenant_login", "/auth/login", 401, "POST",
              {"email": emails[i], "password": passwords[i], "workspace_id": other})

    if manuscript:
        run_manuscript_checks(clients, report, ids, check)

    # Logout's browser behavior and server token revocation are reported separately.
    saved_sessions = []
    for i, client in enumerate(clients):
        saved_sessions.append(dict(client.cookies))
        check(client, f"user_{i}_logout_csrf_missing", "/auth/logout", 403, "POST", {})
        check(client, f"user_{i}_still_authenticated", "/auth/me", 200)
        check(client, f"user_{i}_logout", "/auth/logout", 200, "POST", {},
              {"X-CSRF-Token": client.cookies["wb_csrf"]})
        require("wb_session" not in client.cookies and "wb_csrf" not in client.cookies,
                "logout_cookies_not_cleared")
        check(client, f"user_{i}_logged_out_denial", "/auth/me", 401)
        replay = PreviewClient()
        replay.cookies = dict(saved_sessions[i])
        status, _, _ = replay.request("/auth/me")
        report["session_replay_after_logout"].append({"user": i, "status": status})
        require(status == 401 if require_revocation else status in {200, 401},
                "unexpected_logout_replay_status")
        if require_revocation:
            token = saved_sessions[i]["wb_session"]
            check(PreviewClient(), f"user_{i}_bearer_replay_denied", "/auth/me", 401,
                  headers={"Authorization": f"Bearer {token}"})
            check(PreviewClient(), f"user_{i}_alternate_encoding_denied", "/auth/me", 401,
                  headers={"Authorization": f"Bearer {token}="})
    return saved_sessions


def run_manuscript_checks(clients, report, ids, check):
    """Exercise the deployed Function end to end with synthetic prose and evidence only."""
    def request(label, path, method="GET", body=None, expected=200, user=0):
        client = clients[user]
        headers = {"X-CSRF-Token": client.cookies["wb_csrf"]} if method != "GET" else None
        return check(client, label, path, expected, method, body, headers)[1]

    project = request("chat_project", "/projects", "POST",
                      {"workspace_id": ids["workspaces"][0], "name": "Synthetic chat verification"})
    pid = project["id"]
    manuscript = request("chat_manuscript", f"/projects/{pid}/manuscripts", "POST",
                         {"title": "Synthetic paper"})
    source = request("chat_source", f"/projects/{pid}/sources", "POST",
                     {"title": "Synthetic evidence", "access": "full_text_user_supplied",
                      "acquisition": "Invented solely for staging verification"})
    excerpt = request("chat_excerpt", f"/sources/{source['id']}/excerpts", "POST",
                      {"text": "Synthetic pilot improved by 12%.", "locator": "Synthetic page 3"})
    claim = request("chat_claim", f"/projects/{pid}/claims", "POST",
                    {"text": "Synthetic pilot improved by 12%.", "support": "external_source",
                     "excerpt_ids": [excerpt["id"]]})
    section = request("chat_section", f"/manuscripts/{manuscript['id']}/sections", "POST",
                      {"heading": "Discussion", "text": "Original synthetic draft.",
                       "purpose": "Preserve uncertainty", "claim_ids": [claim["id"]]})
    thread = request("chat_thread", f"/projects/{pid}/threads", "POST",
                     {"title": "Synthetic discussion", "manuscript_id": manuscript["id"],
                      "section_id": section["id"], "mode": "act"})
    tid = thread["id"]
    request("chat_brief", f"/threads/{tid}/brief", "PUT", {"summary": "Do not generalize the pilot."})
    context = request("chat_context", f"/threads/{tid}/context")
    require("Synthetic pilot improved by 12%." in context["system_prompt"], "excerpt_not_in_context")
    require("Do not generalize the pilot." in context["system_prompt"], "brief_not_in_context")
    request("chat_context_other_tenant", f"/threads/{tid}/context", expected=404, user=1)
    check(clients[0], "chat_missing_csrf", f"/threads/{tid}/turns", 403, "POST",
          {"content": "revise: blocked"})

    def propose(label, text):
        reply = request(label, f"/threads/{tid}/turns", "POST", {"content": "revise: " + text})
        require(reply["assistant"]["provenance"]["simulated"] is True, "unexpected_live_chat")
        actions = [a for a in reply["proposed_actions"] if a["kind"] == "revise_section"]
        require(bool(actions), "section_edit_not_proposed")
        # Older pending actions can be returned too; select this turn's exact proposed text.
        return next(a for a in actions if a["payload"].get("text") == text)

    def current_text(label):
        ctx = request(label, f"/threads/{tid}/context")
        return next(item["data"]["body"]["text"] for item in ctx["items"] if item["id"] == section["id"])

    action = propose("chat_proposal", "Synthetic proposed revision.")
    require(current_text("chat_unchanged_before_review") == "Original synthetic draft.", "premature_edit")
    request("chat_other_tenant_approval", f"/actions/{action['id']}/approve", "POST",
            {"plan_hash": action["plan_hash"]}, expected=404, user=1)
    revised = request("chat_human_revision", f"/actions/{action['id']}/revise", "POST",
                      {"plan_hash": action["plan_hash"], "text": "Human-adjusted synthetic prose."})
    request("chat_apply", f"/actions/{revised['id']}/approve", "POST", {"plan_hash": revised["plan_hash"]})
    require(current_text("chat_applied_text") == "Human-adjusted synthetic prose.", "edit_not_applied")
    request("chat_double_approval", f"/actions/{revised['id']}/approve", "POST",
            {"plan_hash": revised["plan_hash"]}, expected=409)
    undo = request("chat_undo_proposal", f"/actions/{revised['id']}/undo", "POST",
                   {"plan_hash": revised["plan_hash"]})
    require(current_text("chat_unchanged_before_undo") == "Human-adjusted synthetic prose.", "premature_undo")
    request("chat_apply_undo", f"/actions/{undo['id']}/approve", "POST", {"plan_hash": undo["plan_hash"]})
    require(current_text("chat_restored_text") == "Original synthetic draft.", "undo_not_applied")
    first = propose("chat_first_proposal", "First synthetic alternative.")
    stale = propose("chat_second_proposal", "Second synthetic alternative.")
    request("chat_apply_first", f"/actions/{first['id']}/approve", "POST", {"plan_hash": first["plan_hash"]})
    request("chat_stale_approval", f"/actions/{stale['id']}/approve", "POST",
            {"plan_hash": stale["plan_hash"]}, expected=409)
    rejected = propose("chat_rejected_proposal", "Rejected synthetic alternative.")
    request("chat_reject", f"/actions/{rejected['id']}/reject", "POST", {})
    require(current_text("chat_final_text") == "First synthetic alternative.",
            "rejected_or_stale_edit_applied")
    ledger = request("chat_claims_unchanged", f"/projects/{pid}/claims")
    require(len(ledger) == 1 and ledger[0]["support"] == "external_source", "claim_support_changed")
    report["manuscript_checks"] = "passed"


def main():
    global DEPLOYMENT, REVISION
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cleanup-only", action="store_true")
    parser.add_argument("--run-id", default=uuid4().hex)
    parser.add_argument("--confirm-project", required=True)
    parser.add_argument("--expected-database-host", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--deployment", default=DEPLOYMENT)
    parser.add_argument("--expected-revision", default=REVISION)
    parser.add_argument("--require-revocation", action="store_true")
    parser.add_argument("--check-manuscript", action="store_true")
    args = parser.parse_args()
    DEPLOYMENT, REVISION = args.deployment, args.expected_revision
    logging.disable(logging.CRITICAL)
    run_id = UUID(args.run_id).hex
    ids = fixture_ids(run_id)
    report = {"run_id": run_id, "deployment_id": DEPLOYMENT, "project_id": PROJECT,
              "started_at": datetime.now(UTC).isoformat(), "fixture_ids": ids, "checks": [],
              "session_replay_after_logout": [], "status": "started"}
    engine = None
    cleanup_required = False
    sessions = []
    phase = "preflight"
    try:
        from sqlalchemy import create_engine, func, insert, select, text
        from sqlalchemy.engine import make_url
        from sqlalchemy.pool import NullPool

        from workbench import config
        from workbench.auth import hash_password
        from workbench.db import normalize_database_url
        from workbench.models import User, Workspace, WorkspaceMember

        config._load_dotenv = lambda: None
        require(args.confirm_project == PROJECT and args.expected_database_host == DATABASE_HOST,
                "target_confirmation_mismatch")
        require(not (args.execute and args.cleanup_only), "conflicting_modes")
        link = json.loads((Path.cwd() / ".vercel" / "project.json").read_text())
        require(link.get("projectId") == PROJECT, "project_link_mismatch")
        require(not any(Path.cwd().glob(".env*")), "operator_directory_contains_dotenv")
        raw_url = os.environ.get("WB_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
        url = make_url(normalize_database_url(raw_url))
        require(url.host == DATABASE_HOST and url.drivername == "postgresql+psycopg",
                "database_target_mismatch")
        client = PreviewClient()
        status, _, health = client.request("/health")
        require(status == 200 and health.get("provider_mode") == "fake"
                and health.get("auth_required") is True and health.get("oidc_mode") == "disabled"
                and health.get("deployment_mode") == "vercel", "unsafe_deployed_health")
        status, _, auth_config = client.request("/auth/config")
        require(status == 200 and auth_config.get("registration_enabled") is False
                and auth_config.get("password_login_enabled") is True
                and auth_config.get("cookie_sessions_enabled") is True, "unsafe_deployed_auth")
        # Neon pooled endpoints may reject PostgreSQL startup "options" parameters.
        engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 30})
        with engine.connect() as connection:
            require(list(connection.scalars(text("SELECT version_num FROM alembic_version"))) == [REVISION],
                    "migration_revision_mismatch")
        report["alembic_revision"] = REVISION
        if args.cleanup_only:
            if args.report.is_file():
                previous = json.loads(args.report.read_text(encoding="utf-8"))
                require(previous.get("run_id") == run_id, "cleanup_report_run_mismatch")
                report["revocation_hashes"] = previous.get("revocation_hashes", [])
            cleanup_required = True
        elif args.execute:
            phase = "seed"
            passwords = [secrets.token_urlsafe(32) for _ in range(2)]
            emails = [f"wb-auth-{run_id}-{i}@example.invalid" for i in range(2)]
            print(json.dumps({"run_id": run_id, "phase": "creating_temporary_fixtures", "ids": ids}),
                  flush=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            cleanup_required = True
            with engine.begin() as connection:
                for i in range(2):
                    connection.execute(insert(User).values(
                        id=ids["users"][i], name=f"Synthetic auth {run_id} {i}", email=emails[i],
                        password_hash=hash_password(passwords[i]), api_key=None))
                    connection.execute(insert(Workspace).values(
                        id=ids["workspaces"][i], name=f"Synthetic auth {run_id} {i}"))
                    connection.execute(insert(WorkspaceMember).values(
                        id=ids["memberships"][i], workspace_id=ids["workspaces"][i],
                        user_id=ids["users"][i], role="owner"))
            phase = "http_checks"
            sessions = run_checks(
                report, ids, emails, passwords, manuscript=args.check_manuscript,
                require_revocation=args.require_revocation,
                checkpoint=lambda: args.report.write_text(
                    json.dumps(report, indent=2) + "\n", encoding="utf-8"
                ),
            )
            with engine.connect() as connection:
                count = connection.scalar(select(func.count()).select_from(WorkspaceMember).where(
                    WorkspaceMember.workspace_id.in_(ids["workspaces"])))
                require(count == 2, "unauthorized_membership_persisted")
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", failed_phase=phase, error_type=type(exc).__name__)
        original = getattr(exc, "orig", None)
        if original is not None:
            report["database_sqlstate"] = getattr(original, "sqlstate", None)
        if isinstance(exc, SmokeFailure):
            report["failed_check"] = str(exc)
    finally:
        if cleanup_required and engine is not None:
            try:
                report["cleanup"] = cleanup(engine, ids, report.get("revocation_hashes"),
                                             manuscript=args.check_manuscript)
            except Exception as exc:
                report.update(status="failed", cleanup_error_type=type(exc).__name__)
        if engine is not None:
            engine.dispose()
    if report.get("cleanup", {}).get("remaining") == 0 and sessions:
        try:
            for i, cookies in enumerate(sessions):
                client = PreviewClient()
                client.cookies = cookies
                status, _, _ = client.request("/auth/me")
                report["checks"].append({"check": f"deleted_user_{i}_session_denied",
                                         "status": status, "passed": status == 401})
                require(status == 401, "deleted_user_session_accepted")
        except Exception as exc:
            report.update(status="failed", post_cleanup_error_type=type(exc).__name__)
    report["finished_at"] = datetime.now(UTC).isoformat()
    classify_report(report)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["status"] in {"passed", "passed_with_findings"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
