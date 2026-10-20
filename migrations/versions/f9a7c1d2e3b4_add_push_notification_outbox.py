"""add push subscriptions and scheduled notification outbox

Revision ID: f9a7c1d2e3b4
Revises: b7c8d9e0f1a2
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'f9a7c1d2e3b4'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'push_subscription',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('subscription_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'), sa.UniqueConstraint('endpoint'),
    )
    op.create_index('ix_push_subscription_user_id', 'push_subscription', ['user_id'])
    op.create_table(
        'notification_job',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('workorder_id', sa.Integer(), nullable=False),
        sa.Column('reminder_kind', sa.String(length=20), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(), nullable=False),
        sa.Column('due_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.String(length=500), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workorder_id'], ['work_order.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'workorder_id', 'reminder_kind', 'scheduled_at', name='uq_notification_workorder_reminder'),
    )
    for column in ('user_id', 'workorder_id', 'due_at', 'status'):
        op.create_index(f'ix_notification_job_{column}', 'notification_job', [column])


def downgrade():
    op.drop_table('notification_job')
    op.drop_table('push_subscription')
