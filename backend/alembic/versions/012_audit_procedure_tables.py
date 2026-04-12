"""创建审计程序表

Revision ID: 012
Revises: 011
Create Date: 2024-06-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audit_procedures',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('procedure_code', sa.String(50), nullable=False),
        sa.Column('procedure_name', sa.String(200), nullable=False),
        sa.Column('procedure_type', sa.Enum(
            'risk_assessment', 'control_test', 'substantive', name='procedure_type_enum'), nullable=False),
        sa.Column('audit_cycle', sa.String(100), nullable=True),
        sa.Column('account_code', sa.String(50), nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('execution_status', sa.Enum(
            'not_started', 'in_progress', 'completed', 'not_applicable', name='execution_status_enum'), default='not_started', nullable=False),
        sa.Column('executed_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('executed_at', sa.Date, nullable=True),
        sa.Column('conclusion', sa.Text, nullable=True),
        sa.Column('related_wp_code', sa.String(50), nullable=True),
        sa.Column('related_risk_id', UUID(as_uuid=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_audit_procedures_project_type', 'audit_procedures', ['project_id', 'procedure_type'])
    op.create_index('ix_audit_procedures_project_cycle', 'audit_procedures', ['project_id', 'audit_cycle'])
    op.create_index('ix_audit_procedures_project_status', 'audit_procedures', ['project_id', 'execution_status'])


def downgrade():
    op.drop_table('audit_procedures')
