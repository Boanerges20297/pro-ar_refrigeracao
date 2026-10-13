from alembic import op
import sqlalchemy as sa

revision = 'b7c8d9e0f1a2'
down_revision = 'add_cnpj_feat'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('service_route',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('client.id'), nullable=False),
        sa.Column('technician_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('work_order_ids', sa.Text(), nullable=False),
        sa.Column('status', sa.String(30), nullable=False, server_default='In Progress'),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True))

def downgrade():
    op.drop_table('service_route')
