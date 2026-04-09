"""Add license table

Revision ID: b1f0c7c9a5d2
Revises: c9f3a1b2d4e5
Create Date: 2026-04-08 15:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1f0c7c9a5d2'
down_revision = 'c9f3a1b2d4e5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'license',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('license_key', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('company_name', sa.String(length=100), nullable=True),
        sa.Column('instance_fingerprint', sa.String(length=64), nullable=True),
        sa.Column('issued_at', sa.DateTime(), nullable=True),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('last_validated_at', sa.DateTime(), nullable=True),
        sa.Column('last_validation_status', sa.String(length=20), nullable=True),
        sa.Column('last_validation_error', sa.Text(), nullable=True),
        sa.Column('max_users', sa.Integer(), nullable=True),
        sa.Column('max_admin_users', sa.Integer(), nullable=True),
        sa.Column('max_secretary_users', sa.Integer(), nullable=True),
        sa.Column('feature_flags', sa.Text(), nullable=True),
        sa.Column('warning_days', sa.Integer(), nullable=False, server_default='15'),
        sa.Column('grace_days', sa.Integer(), nullable=False, server_default='7'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_license_expires_at'), 'license', ['expires_at'], unique=False)
    op.create_index(op.f('ix_license_instance_fingerprint'), 'license', ['instance_fingerprint'], unique=False)
    op.create_index(op.f('ix_license_status'), 'license', ['status'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_license_status'), table_name='license')
    op.drop_index(op.f('ix_license_instance_fingerprint'), table_name='license')
    op.drop_index(op.f('ix_license_expires_at'), table_name='license')
    op.drop_table('license')