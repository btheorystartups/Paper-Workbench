"""workspace tenant auth foundation

Revision ID: f3a1c7e9b420
Revises: e8b4c1d7a290
Create Date: 2026-09-08

"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "f3a1c7e9b420"
down_revision = "e8b4c1d7a290"
branch_labels = None
depends_on = None


def _id() -> str:
    return uuid.uuid4().hex


def upgrade() -> None:
    # Production credentials move to api_credentials. Keep legacy user keys readable
    # for local mode, but stop requiring new users to have one.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "api_key",
            existing_type=sa.String(length=64),
            nullable=True,
        )

    op.create_table(
        "workspace_members",
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id"),
    )
    op.create_index(
        op.f("ix_workspace_members_user_id"), "workspace_members", ["user_id"]
    )
    op.create_index(
        op.f("ix_workspace_members_workspace_id"),
        "workspace_members",
        ["workspace_id"],
    )

    op.create_table(
        "federated_identities",
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("issuer", sa.String(length=500), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("email_at_link", sa.String(length=320), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", "subject"),
    )
    op.create_index(
        op.f("ix_federated_identities_user_id"),
        "federated_identities",
        ["user_id"],
    )
    op.create_index(
        "ix_federated_identity_user_issuer",
        "federated_identities",
        ["user_id", "issuer"],
    )

    op.create_table(
        "oidc_workspace_bindings",
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("issuer", sa.String(length=500), nullable=False),
        sa.Column("tenant_key", sa.String(length=500), nullable=False),
        sa.Column("default_role", sa.String(length=20), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", "tenant_key"),
    )
    op.create_index(
        op.f("ix_oidc_workspace_bindings_workspace_id"),
        "oidc_workspace_bindings",
        ["workspace_id"],
    )

    op.create_table(
        "api_credentials",
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index(
        op.f("ix_api_credentials_key_prefix"),
        "api_credentials",
        ["key_prefix"],
    )
    op.create_index(
        op.f("ix_api_credentials_user_id"), "api_credentials", ["user_id"]
    )
    op.create_index(
        op.f("ix_api_credentials_workspace_id"),
        "api_credentials",
        ["workspace_id"],
    )

    # Existing databases were explicitly single-machine. Lift their current project
    # memberships to the workspace boundary; an unowned legacy workspace goes to the
    # oldest active user so migration never silently locks the local operator out.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT p.workspace_id, pm.user_id, pm.role
            FROM project_members AS pm
            JOIN projects AS p ON p.id = pm.project_id
            WHERE pm.deleted_at IS NULL AND p.deleted_at IS NULL
            ORDER BY p.workspace_id, pm.created_at, pm.id
            """
        )
    ).mappings()
    memberships: dict[tuple[str, str], str] = {}
    owner_candidates: dict[str, str] = {}
    for row in rows:
        key = (row["workspace_id"], row["user_id"])
        memberships[key] = "member"
        if row["role"] == "owner":
            owner_candidates.setdefault(row["workspace_id"], row["user_id"])

    for workspace_id, user_id in owner_candidates.items():
        memberships[(workspace_id, user_id)] = "owner"

    workspace_ids = [
        row[0]
        for row in bind.execute(
            sa.text("SELECT id FROM workspaces WHERE deleted_at IS NULL ORDER BY created_at, id")
        )
    ]
    first_user = bind.execute(
        sa.text(
            "SELECT id FROM users WHERE deleted_at IS NULL ORDER BY created_at, id LIMIT 1"
        )
    ).scalar_one_or_none()
    for workspace_id in workspace_ids:
        if any(
            key[0] == workspace_id and role == "owner"
            for key, role in memberships.items()
        ):
            continue
        existing_member = next(
            (key[1] for key in memberships if key[0] == workspace_id), None
        )
        owner_id = existing_member or first_user
        if owner_id:
            memberships[(workspace_id, owner_id)] = "owner"

    if memberships:
        now = datetime.now(UTC)
        table = sa.table(
            "workspace_members",
            sa.column("workspace_id", sa.String),
            sa.column("user_id", sa.String),
            sa.column("role", sa.String),
            sa.column("id", sa.String),
            sa.column("created_at", sa.DateTime),
            sa.column("deleted_at", sa.DateTime),
        )
        op.bulk_insert(
            table,
            [
                {
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                    "role": role,
                    "id": _id(),
                    "created_at": now,
                    "deleted_at": None,
                }
                for (workspace_id, user_id), role in memberships.items()
            ],
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_api_credentials_workspace_id"), table_name="api_credentials")
    op.drop_index(op.f("ix_api_credentials_user_id"), table_name="api_credentials")
    op.drop_index(op.f("ix_api_credentials_key_prefix"), table_name="api_credentials")
    op.drop_table("api_credentials")

    op.drop_index(
        op.f("ix_oidc_workspace_bindings_workspace_id"),
        table_name="oidc_workspace_bindings",
    )
    op.drop_table("oidc_workspace_bindings")

    op.drop_index(
        "ix_federated_identity_user_issuer", table_name="federated_identities"
    )
    op.drop_index(
        op.f("ix_federated_identities_user_id"), table_name="federated_identities"
    )
    op.drop_table("federated_identities")

    op.drop_index(
        op.f("ix_workspace_members_workspace_id"), table_name="workspace_members"
    )
    op.drop_index(op.f("ix_workspace_members_user_id"), table_name="workspace_members")
    op.drop_table("workspace_members")

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE users SET api_key = 'legacy-' || id WHERE api_key IS NULL"
        )
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "api_key",
            existing_type=sa.String(length=64),
            nullable=False,
        )
