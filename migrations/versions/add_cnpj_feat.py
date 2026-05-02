"""add cnpj to client

Revision ID: add_cnpj_feat
Revises: f6d8a4b2c0e1
Create Date: 2026-05-02 17:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_cnpj_feat'
down_revision = 'f6d8a4b2c0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('client', sa.Column('cnpj', sa.String(length=18), nullable=True))


def downgrade():
    op.drop_column('client', 'cnpj')
