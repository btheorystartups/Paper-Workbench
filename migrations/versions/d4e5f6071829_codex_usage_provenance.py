"""Record provider authentication and quota provenance separately from API usage."""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6071829"
down_revision = "b3c4d5e6f708"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usage_events", sa.Column("provenance", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("usage_events", "provenance")
