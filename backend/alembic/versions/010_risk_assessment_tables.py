"""创建风险评估相关表

Revision ID: 010
Revises: 009
Create Date: 2024-06-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade():
    # --- risk_assessments ---
    op.create_table(
        'risk_assessments',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('assertion_level', sa.Enum(
            'existence', 'completeness', 'accuracy', 'cutoff',
            'classification', 'occurrence', 'rights_obligations', 'valuation',
            name='assertion_level'), nullable=False),
        sa.Column('account_or_cycle', sa.String(100), nullable=False),
        sa.Column('inherent_risk', sa.Enum('high', 'medium', 'low', name='risk_level'), nullable=False),
        sa.Column('control_risk', sa.Enum('high', 'medium', 'low', name='risk_level'), nullable=False),
        sa.Column('combined_risk', sa.Enum('high', 'medium', 'low', name='risk_level'), nullable=False),
        sa.Column('is_significant_risk', sa.Boolean, default=False, nullable=False),
        sa.Column('risk_description', sa.Text, nullable=True),
        sa.Column('response_strategy', sa.Text, nullable=True),
        sa.Column('related_audit_procedures', JSONB, nullable=True),
        sa.Column('review_status', sa.Enum('draft', 'pending_review', 'approved', 'rejected', name='review_status_enum'), default='draft', nullable=False),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index('ix_risk_assessments_project_account', 'risk_assessments', ['project_id', 'account_or_cycle'])
    op.create_index('ix_risk_assessments_project_cycle', 'risk_assessments', ['project_id', 'account_or_cycle'])
    op.create_index('ix_risk_assessments_significant', 'risk_assessments', ['project_id', 'is_significant_risk'])

    # --- risk_matrix_records ---
    op.create_table(
        'risk_matrix_records',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('inherent_risk', sa.Enum('high', 'medium', 'low', name='risk_level'), nullable=False),
        sa.Column('control_risk', sa.Enum('high', 'medium', 'low', name='risk_level'), nullable=False),
        sa.Column('combined_risk', sa.Enum('high', 'medium', 'low', name='risk_level'), nullable=False),
        sa.Column('inherent_risk_score', sa.Integer, nullable=False),
        sa.Column('control_risk_score', sa.Integer, nullable=False),
        sa.Column('combined_risk_score', sa.Integer, nullable=False),
        sa.Column('mitigation_notes', sa.Text, nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_risk_matrix_project', 'risk_matrix_records', ['project_id'])


def downgrade():
    op.drop_table('risk_matrix_records')
    op.drop_table('risk_assessments')
