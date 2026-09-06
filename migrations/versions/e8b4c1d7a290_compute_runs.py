"""review-gated reproducible compute runs

Revision ID: e8b4c1d7a290
Revises: d7f2a9c6e410
Create Date: 2026-09-06

"""

import sqlalchemy as sa
from alembic import op

revision = "e8b4c1d7a290"
down_revision = "d7f2a9c6e410"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compute_runs",
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("script_source_id", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("review_state", sa.String(length=20), nullable=False),
        sa.Column("network_policy", sa.String(length=50), nullable=False),
        sa.Column("plan_hash", sa.String(length=64), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("approval_note", sa.Text(), nullable=False),
        sa.Column("execution", sa.JSON(), nullable=False),
        sa.Column("outputs", sa.JSON(), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("promoted_object_ids", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["script_source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("compute_runs", schema=None) as batch_op:
        batch_op.create_index(
            "ix_compute_run_project_review",
            ["project_id", "review_state"],
            unique=False,
        )
        batch_op.create_index(
            "ix_compute_run_project_state",
            ["project_id", "state"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_compute_runs_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_compute_runs_script_source_id"),
            ["script_source_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("compute_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_compute_runs_script_source_id"))
        batch_op.drop_index(batch_op.f("ix_compute_runs_project_id"))
        batch_op.drop_index("ix_compute_run_project_state")
        batch_op.drop_index("ix_compute_run_project_review")
    op.drop_table("compute_runs")
