"""创建管理建议书相关表

Revision ID: 014
Revises: 013
Create Date: 2024-06-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'management_letters',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('letter_code', sa.String(50), nullable=False),
        sa.Column('issue_number', sa.Integer, nullable=False),
        sa.Column('issue_type', sa.Enum(
            'control_deficiency', 'process_improvement', 'compliance', 'other', name='issue_type_enum'), nullable=False),
        sa.Column('issue_title', sa.String(200), nullable=False),
        sa.Column('issue_description', sa.Text, nullable=True),
        sa.Column('recommendation', sa.Text, nullable=True),
        sa.Column('management_response', sa.Text, nullable=True),
        sa.Column('response_by', sa.String(100), nullable=True),
        sa.Column('response_date', sa.Date, nullable=True),
        sa.Column('follow_up_status', sa.Enum(
            'open', 'in_progress', 'resolved', 'accepted_risk', name='follow_up_status_enum'), default='open', nullable=False),
        sa.Column('prior_year_item_id', UUID(as_uuid=True), nullable=True),
        sa.Column('is_prior_year_carryforward', sa.Boolean, default=False, nullable=False),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index('ix_management_letters_project', 'management_letters', ['project_id'])
    op.create_index('ix_management_letters_status', 'management_letters', ['follow_up_status'])
    op.create_index('ix_management_letters_prior', 'management_letters', ['prior_year_item_id'])


def downgrade():
    op.drop_table('management_letters')
