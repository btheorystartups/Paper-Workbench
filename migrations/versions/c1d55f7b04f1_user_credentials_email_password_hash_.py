"""user credentials: email, password_hash, oidc

Revision ID: c1d55f7b04f1
Revises: 87d0b44a3f39
Create Date: 2026-07-20 20:02:12.739238

"""
from alembic import op
import sqlalchemy as sa


revision = 'c1d55f7b04f1'
down_revision = '87d0b44a3f39'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=320), nullable=True))
        batch_op.add_column(sa.Column('password_hash', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('oidc_subject', sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column('email_verified', sa.Boolean(), nullable=False,
                      server_default=sa.false())
        )
        batch_op.create_unique_constraint('uq_users_oidc_subject', ['oidc_subject'])
        batch_op.create_unique_constraint('uq_users_email', ['email'])


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_email', type_='unique')
        batch_op.drop_constraint('uq_users_oidc_subject', type_='unique')
        batch_op.drop_column('email_verified')
        batch_op.drop_column('oidc_subject')
        batch_op.drop_column('password_hash')
        batch_op.drop_column('email')
