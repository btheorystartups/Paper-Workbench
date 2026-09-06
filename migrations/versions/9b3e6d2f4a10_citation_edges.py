"""citation edges with provider provenance and controlled review state

Revision ID: 9b3e6d2f4a10
Revises: 7c2d8e4f1a23
Create Date: 2026-09-06

"""

import sqlalchemy as sa
from alembic import op

revision = "9b3e6d2f4a10"
down_revision = "7c2d8e4f1a23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "citation_edges",
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("citing_source_id", sa.String(length=32), nullable=True),
        sa.Column("cited_source_id", sa.String(length=32), nullable=True),
        sa.Column("citing_key", sa.String(length=700), nullable=False),
        sa.Column("cited_key", sa.String(length=700), nullable=False),
        sa.Column("citing_title", sa.String(length=600), nullable=False),
        sa.Column("cited_title", sa.String(length=600), nullable=False),
        sa.Column("resolution_state", sa.String(length=40), nullable=False),
        sa.Column("review_state", sa.String(length=40), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("observations", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["cited_source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["citing_source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "citing_key", "cited_key"),
    )
    with op.batch_alter_table("citation_edges", schema=None) as batch_op:
        batch_op.create_index(
            "ix_citation_project_resolution",
            ["project_id", "resolution_state"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_citation_edges_cited_source_id"),
            ["cited_source_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_citation_edges_citing_source_id"),
            ["citing_source_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_citation_edges_project_id"),
            ["project_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("citation_edges", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_citation_edges_project_id"))
        batch_op.drop_index(batch_op.f("ix_citation_edges_citing_source_id"))
        batch_op.drop_index(batch_op.f("ix_citation_edges_cited_source_id"))
        batch_op.drop_index("ix_citation_project_resolution")
    op.drop_table("citation_edges")
