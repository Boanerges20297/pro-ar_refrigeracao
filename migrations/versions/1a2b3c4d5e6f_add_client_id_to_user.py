"""add client_id to user

Revision ID: 1a2b3c4d5e6f
Revises: cafd02fb47b0
Create Date: 2026-04-27 12:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1a2b3c4d5e6f'
down_revision = 'cafd02fb47b0'
branch_labels = None
depends_on = None


def upgrade():
    # Adiciona a coluna client_id à tabela user
    # Usamos batch_alter_table para compatibilidade total com SQLite e Postgres
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('client_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_user_client_id', 'client', ['client_id'], ['id'])


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('fk_user_client_id', type_='foreignkey')
        batch_op.drop_column('client_id')
