"""add must_change_password to user

Revision ID: a1b2c3d4e5f6
Revises: f28f3b783c81
Create Date: 2026-04-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f28f3b783c81'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'user',
        sa.Column('must_change_password', sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    if is_sqlite:
        op.execute(sa.text('PRAGMA foreign_keys=OFF'))

    try:
        with op.batch_alter_table('user', schema=None) as batch_op:
            batch_op.drop_column('must_change_password')
    finally:
        if is_sqlite:
            op.execute(sa.text('PRAGMA foreign_keys=ON'))