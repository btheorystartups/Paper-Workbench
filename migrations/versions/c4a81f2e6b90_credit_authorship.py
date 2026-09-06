"""review-gated CRediT contributions and authorship proposals

Revision ID: c4a81f2e6b90
Revises: 9b3e6d2f4a10
Create Date: 2026-09-06

"""

import sqlalchemy as sa
from alembic import op

revision = "c4a81f2e6b90"
down_revision = "9b3e6d2f4a10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contributors",
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=300), nullable=False),
        sa.Column("given_names", sa.String(length=200), nullable=False),
        sa.Column("family_name", sa.String(length=200), nullable=False),
        sa.Column("orcid", sa.String(length=19), nullable=True),
        sa.Column("affiliation", sa.Text(), nullable=False),
        sa.Column("corresponding", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("contributors", schema=None) as batch_op:
        batch_op.create_index(
            "ix_contributor_project_name", ["project_id", "display_name"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_contributors_project_id"), ["project_id"], unique=False
        )

    op.create_table(
        "credit_assignments",
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("manuscript_id", sa.String(length=32), nullable=False),
        sa.Column("contributor_id", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("degree", sa.String(length=20), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("origin", sa.String(length=20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["contributor_id"], ["contributors.id"]),
        sa.ForeignKeyConstraint(["manuscript_id"], ["research_objects.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("manuscript_id", "contributor_id", "role"),
    )
    with op.batch_alter_table("credit_assignments", schema=None) as batch_op:
        batch_op.create_index(
            "ix_credit_manuscript_state", ["manuscript_id", "state"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_credit_assignments_contributor_id"),
            ["contributor_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_assignments_manuscript_id"),
            ["manuscript_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_assignments_project_id"), ["project_id"], unique=False
        )

    op.create_table(
        "authorship_proposals",
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("manuscript_id", sa.String(length=32), nullable=False),
        sa.Column("ordered_contributor_ids", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("method", sa.String(length=50), nullable=False),
        sa.Column("basis_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["manuscript_id"], ["research_objects.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("authorship_proposals", schema=None) as batch_op:
        batch_op.create_index(
            "ix_authorship_manuscript_status", ["manuscript_id", "status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_authorship_proposals_manuscript_id"),
            ["manuscript_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_authorship_proposals_project_id"), ["project_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("authorship_proposals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_authorship_proposals_project_id"))
        batch_op.drop_index(batch_op.f("ix_authorship_proposals_manuscript_id"))
        batch_op.drop_index("ix_authorship_manuscript_status")
    op.drop_table("authorship_proposals")
    with op.batch_alter_table("credit_assignments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_credit_assignments_project_id"))
        batch_op.drop_index(batch_op.f("ix_credit_assignments_manuscript_id"))
        batch_op.drop_index(batch_op.f("ix_credit_assignments_contributor_id"))
        batch_op.drop_index("ix_credit_manuscript_state")
    op.drop_table("credit_assignments")
    with op.batch_alter_table("contributors", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_contributors_project_id"))
        batch_op.drop_index("ix_contributor_project_name")
    op.drop_table("contributors")
