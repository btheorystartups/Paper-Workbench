"""usage events + cost budgets

Revision ID: 5a1c9b7e2f10
Revises: 847bd078d7c4
Create Date: 2026-07-22

"""
from alembic import op
import sqlalchemy as sa


revision = '5a1c9b7e2f10'
down_revision = '847bd078d7c4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('usage_events',
    sa.Column('project_id', sa.String(length=32), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('model', sa.String(length=120), nullable=False),
    sa.Column('kind', sa.String(length=60), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('total_tokens', sa.Integer(), nullable=False),
    sa.Column('simulated', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('usage_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_usage_events_project_id'), ['project_id'], unique=False)

    op.create_table('cost_budgets',
    sa.Column('project_id', sa.String(length=32), nullable=False),
    sa.Column('monthly_token_ceiling', sa.Integer(), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id')
    )


def downgrade() -> None:
    op.drop_table('cost_budgets')
    with op.batch_alter_table('usage_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_usage_events_project_id'))
    op.drop_table('usage_events')
