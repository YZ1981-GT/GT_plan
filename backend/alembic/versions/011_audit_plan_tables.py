"""创建审计计划表

Revision ID: 011
Revises: 010
Create Date: 2024-06-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '011'
down_revision = '010a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audit_plans',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False, unique=True),
        sa.Column('plan_version', sa.Integer, default=1, nullable=False),
        sa.Column('audit_strategy', sa.Text, nullable=True),
        sa.Column('planned_start_date', sa.Date, nullable=True),
        sa.Column('planned_end_date', sa.Date, nullable=True),
        sa.Column('key_focus_areas', JSONB, nullable=True),
        sa.Column('team_assignment_summary', JSONB, nullable=True),
        sa.Column('materiality_reference', sa.Text, nullable=True),
        sa.Column('status', sa.Enum('draft', 'approved', 'revised', name='audit_plan_status'), default='draft', nullable=False),
        sa.Column('approved_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index('ix_audit_plans_project', 'audit_plans', ['project_id'])
    op.create_index('ix_audit_plans_status', 'audit_plans', ['status'])


def downgrade():
    op.drop_table('audit_plans')
