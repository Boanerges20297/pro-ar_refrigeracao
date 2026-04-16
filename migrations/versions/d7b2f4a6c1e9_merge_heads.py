"""merge alembic heads

Revision ID: d7b2f4a6c1e9
Revises: 7e1a4f0e2b3c, a1b2c3d4e5f6
Create Date: 2026-04-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7b2f4a6c1e9'
down_revision = ('7e1a4f0e2b3c', 'a1b2c3d4e5f6')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass