"""Initial license_api schema.

Revision ID: 20260409_0001
Revises:
Create Date: 2026-04-09 22:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "20260409_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "issued_license",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("license_id", sa.String(length=64), nullable=False),
        sa.Column("company_name", sa.String(length=120), nullable=False),
        sa.Column("instance_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("license_type", sa.String(length=20), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("max_users", sa.Integer(), nullable=True),
        sa.Column("max_admin_users", sa.Integer(), nullable=True),
        sa.Column("max_secretary_users", sa.Integer(), nullable=True),
        sa.Column("features_json", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_issued_license_company_name"), "issued_license", ["company_name"], unique=False)
    op.create_index(op.f("ix_issued_license_expires_at"), "issued_license", ["expires_at"], unique=False)
    op.create_index(op.f("ix_issued_license_instance_fingerprint"), "issued_license", ["instance_fingerprint"], unique=False)
    op.create_index(op.f("ix_issued_license_license_id"), "issued_license", ["license_id"], unique=True)
    op.create_index(op.f("ix_issued_license_license_type"), "issued_license", ["license_type"], unique=False)
    op.create_index(op.f("ix_issued_license_status"), "issued_license", ["status"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_issued_license_status"), table_name="issued_license")
    op.drop_index(op.f("ix_issued_license_license_type"), table_name="issued_license")
    op.drop_index(op.f("ix_issued_license_license_id"), table_name="issued_license")
    op.drop_index(op.f("ix_issued_license_instance_fingerprint"), table_name="issued_license")
    op.drop_index(op.f("ix_issued_license_expires_at"), table_name="issued_license")
    op.drop_index(op.f("ix_issued_license_company_name"), table_name="issued_license")
    op.drop_table("issued_license")