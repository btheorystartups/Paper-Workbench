"""review-gated publication packages

Revision ID: d7f2a9c6e410
Revises: c4a81f2e6b90
Create Date: 2026-09-06

"""

import sqlalchemy as sa
from alembic import op

revision = "d7f2a9c6e410"
down_revision = "c4a81f2e6b90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "publication_packages",
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("submission_id", sa.String(length=32), nullable=False),
        sa.Column("manuscript_id", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("included_formats", sa.JSON(), nullable=False),
        sa.Column("cover_letter", sa.Text(), nullable=False),
        sa.Column("cover_letter_state", sa.String(length=20), nullable=False),
        sa.Column("cover_letter_review_note", sa.Text(), nullable=False),
        sa.Column("declarations", sa.JSON(), nullable=False),
        sa.Column("basis_hash", sa.String(length=64), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("builds", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["manuscript_id"], ["research_objects.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", "version"),
    )
    with op.batch_alter_table("publication_packages", schema=None) as batch_op:
        batch_op.create_index(
            "ix_publication_package_submission_state",
            ["submission_id", "state"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_publication_packages_manuscript_id"),
            ["manuscript_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_publication_packages_project_id"),
            ["project_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_publication_packages_submission_id"),
            ["submission_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("publication_packages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_publication_packages_submission_id"))
        batch_op.drop_index(batch_op.f("ix_publication_packages_project_id"))
        batch_op.drop_index(batch_op.f("ix_publication_packages_manuscript_id"))
        batch_op.drop_index("ix_publication_package_submission_state")
    op.drop_table("publication_packages")
