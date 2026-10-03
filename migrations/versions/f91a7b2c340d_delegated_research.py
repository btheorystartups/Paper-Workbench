"""Checkpointed delegated research tasks and agent lineage.

Revision ID: f91a7b2c340d
Revises: d4e5f6071829
"""

import sqlalchemy as sa
from alembic import op

revision = "f91a7b2c340d"
down_revision = "d4e5f6071829"
branch_labels = None
depends_on = None


def stamps():
    return [
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade():
    op.create_table(
        "research_tasks",
        *stamps(),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("thread_id", sa.String(32), sa.ForeignKey("threads.id"), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        *[
            sa.Column(name, sa.JSON(), nullable=False)
            for name in ("contract", "sources", "ledger", "synthesis", "reviews")
        ],
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_index("ix_research_tasks_project_id", "research_tasks", ["project_id"])
    op.create_table(
        "research_agents",
        *stamps(),
        sa.Column("task_id", sa.String(32), sa.ForeignKey("research_tasks.id"), nullable=False),
        sa.Column("parent_id", sa.String(32), sa.ForeignKey("research_agents.id")),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        *[
            sa.Column(name, sa.JSON(), nullable=False)
            for name in ("assignment", "report", "checkpoints", "provenance")
        ],
    )
    op.create_index("ix_research_agents_task_id", "research_agents", ["task_id"])


def downgrade():
    op.drop_table("research_agents")
    op.drop_table("research_tasks")
