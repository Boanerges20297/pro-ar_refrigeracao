"""Link maintenance schedules to work orders

Revision ID: 7e1a4f0e2b3c
Revises: b1f0c7c9a5d2
Create Date: 2026-04-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7e1a4f0e2b3c'
down_revision = 'b1f0c7c9a5d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('maintenance_schedule', schema=None) as batch_op:
        batch_op.add_column(sa.Column('workorder_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_maintenance_schedule_workorder_id',
            'work_order',
            ['workorder_id'],
            ['id'],
        )
        batch_op.create_unique_constraint('uq_maintenance_schedule_workorder_id', ['workorder_id'])


def downgrade():
    with op.batch_alter_table('maintenance_schedule', schema=None) as batch_op:
        batch_op.drop_constraint('uq_maintenance_schedule_workorder_id', type_='unique')
        batch_op.drop_constraint('fk_maintenance_schedule_workorder_id', type_='foreignkey')
        batch_op.drop_column('workorder_id')