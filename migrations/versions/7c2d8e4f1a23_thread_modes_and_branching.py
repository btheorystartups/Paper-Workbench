"""thread modes and branching

Revision ID: 7c2d8e4f1a23
Revises: 5a1c9b7e2f10
Create Date: 2026-07-23

"""
from alembic import op
import sqlalchemy as sa


revision = '7c2d8e4f1a23'
down_revision = '5a1c9b7e2f10'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('threads', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('mode', sa.String(length=20), nullable=False,
                      server_default='explore'))
        batch_op.add_column(
            sa.Column('parent_thread_id', sa.String(length=32), nullable=True))
        batch_op.add_column(
            sa.Column('branched_from_turn_id', sa.String(length=32), nullable=True))
        batch_op.create_foreign_key(
            'fk_threads_parent', 'threads', ['parent_thread_id'], ['id'])
        batch_op.create_foreign_key(
            'fk_threads_branch_turn', 'turns', ['branched_from_turn_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('threads', schema=None) as batch_op:
        batch_op.drop_constraint('fk_threads_branch_turn', type_='foreignkey')
        batch_op.drop_constraint('fk_threads_parent', type_='foreignkey')
        batch_op.drop_column('branched_from_turn_id')
        batch_op.drop_column('parent_thread_id')
        batch_op.drop_column('mode')
