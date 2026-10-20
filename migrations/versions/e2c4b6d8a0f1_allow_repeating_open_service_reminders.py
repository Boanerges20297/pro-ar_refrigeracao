"""allow repeated open service reminders

Revision ID: e2c4b6d8a0f1
Revises: f9a7c1d2e3b4
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'e2c4b6d8a0f1'
down_revision = 'f9a7c1d2e3b4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notification_job') as batch_op:
        batch_op.drop_constraint('uq_notification_workorder_reminder', type_='unique')
        batch_op.create_unique_constraint(
            'uq_notification_workorder_reminder',
            ['user_id', 'workorder_id', 'reminder_kind', 'scheduled_at', 'due_at'],
        )


def downgrade():
    with op.batch_alter_table('notification_job') as batch_op:
        batch_op.drop_constraint('uq_notification_workorder_reminder', type_='unique')
        batch_op.create_unique_constraint(
            'uq_notification_workorder_reminder',
            ['user_id', 'workorder_id', 'reminder_kind', 'scheduled_at'],
        )
