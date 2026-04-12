"""创建审计发现表

Revision ID: 013
Revises: 012
Create Date: 2024-06-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audit_findings',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('finding_code', sa.String(50), nullable=False),
        sa.Column('finding_description', sa.Text, nullable=True),
        sa.Column('severity', sa.Enum('high', 'medium', 'low', name='severity_level'), nullable=False),
        sa.Column('affected_account', sa.String(100), nullable=True),
        sa.Column('finding_amount', sa.Numeric(20, 2), nullable=True),
        sa.Column('management_response', sa.Text, nullable=True),
        sa.Column('final_treatment', sa.Enum(
            'adjusted', 'unadjusted', 'disclosed', 'no_action', name='final_treatment_enum'), nullable=True),
        sa.Column('related_adjustment_ids', sa.JSON, nullable=True),
        sa.Column('related_wp_code', sa.String(50), nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index('ix_audit_findings_project', 'audit_findings', ['project_id'])
    op.create_index('ix_audit_findings_severity', 'audit_findings', ['severity'])


def downgrade():
    op.drop_table('audit_findings')
