"""merge proposal workflow and manuscript-chat heads

Revision ID: b3c4d5e6f708
Revises: a2b3c4d5e6f7, a91d4e7b620f
Create Date: 2026-09-14
"""

revision = "b3c4d5e6f708"
down_revision = ("a2b3c4d5e6f7", "a91d4e7b620f")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge-only revision: each parent owns its own schema changes."""


def downgrade() -> None:
    """Merge-only revision: Alembic restores both parent heads."""
