"""Permit unauthenticated login attempts in the audit log.

Revision ID: b6f3c91a2d08
Revises: e2c4b6d8a0f1
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'b6f3c91a2d08'
down_revision = 'e2c4b6d8a0f1'
branch_labels = None
depends_on = None

def upgrade():
    # An unknown user has no User.id, yet the attempt is security-relevant.
    # Keep the foreign key; SQL NULL is permitted for these events only.
    with op.batch_alter_table('audit_log') as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=True)

def downgrade():
    # Downgrade intentionally fails if anonymous events exist. Never delete
    # security audit records automatically to satisfy the old constraint.
    with op.batch_alter_table('audit_log') as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
