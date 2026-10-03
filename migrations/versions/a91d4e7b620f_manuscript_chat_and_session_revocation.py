"""Manuscript dialogue context and shared access-token revocation.

Revision ID: a91d4e7b620f
Revises: f3a1c7e9b420
"""

import sqlalchemy as sa
from alembic import op

revision = "a91d4e7b620f"
down_revision = "f3a1c7e9b420"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        # ADD nullable REFERENCES is supported natively. Rebuilding threads would fail
        # with foreign_keys=ON when existing turns/actions reference that table.
        op.execute("ALTER TABLE threads ADD COLUMN manuscript_id VARCHAR(32) REFERENCES research_objects(id)")
        op.execute("ALTER TABLE threads ADD COLUMN section_id VARCHAR(32) REFERENCES research_objects(id)")
    else:
        with op.batch_alter_table("threads") as batch:
            batch.add_column(sa.Column("manuscript_id", sa.String(32), nullable=True))
            batch.add_column(sa.Column("section_id", sa.String(32), nullable=True))
            batch.create_foreign_key("fk_thread_manuscript", "research_objects", ["manuscript_id"], ["id"])
            batch.create_foreign_key("fk_thread_section", "research_objects", ["section_id"], ["id"])
    op.create_table(
        "revoked_access_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_revoked_access_tokens_expires_at", "revoked_access_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_revoked_access_tokens_expires_at", table_name="revoked_access_tokens")
    op.drop_table("revoked_access_tokens")
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE threads DROP COLUMN section_id")
        op.execute("ALTER TABLE threads DROP COLUMN manuscript_id")
    else:
        with op.batch_alter_table("threads") as batch:
            batch.drop_constraint("fk_thread_section", type_="foreignkey")
            batch.drop_constraint("fk_thread_manuscript", type_="foreignkey")
            batch.drop_column("section_id")
            batch.drop_column("manuscript_id")
