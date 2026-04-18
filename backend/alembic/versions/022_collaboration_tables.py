"""创建剩余协作相关表（通知、函证、持续经营、审计档案归档）

Revision ID: 015
Revises: 014
Create Date: 2024-06-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '022'
down_revision = '021'
branch_labels = None
depends_on = None


def upgrade():
    # --- notifications ---
    op.create_table(
        'notifications',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('notification_type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('message', sa.Text, nullable=True),
        sa.Column('is_read', sa.Boolean, default=False, nullable=False),
        sa.Column('related_object_type', sa.String(50), nullable=True),
        sa.Column('related_object_id', UUID(as_uuid=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_notifications_user_unread', 'notifications', ['user_id', 'is_read'])

    # --- confirmation_lists ---
    op.create_table(
        'confirmation_lists',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('confirmation_type', sa.Enum(
            'bank', 'customer', 'vendor', 'lawyer', 'other', name='confirmation_type_enum'), nullable=False),
        sa.Column('confirmation_code', sa.String(50), nullable=False),
        sa.Column('counterparty_name', sa.String(200), nullable=False),
        sa.Column('counterparty_address', sa.Text, nullable=True),
        sa.Column('contact_person', sa.String(100), nullable=True),
        sa.Column('contact_email', sa.String(200), nullable=True),
        sa.Column('balance_or_amount', sa.Numeric(20, 2), nullable=True),
        sa.Column('as_of_date', sa.Date, nullable=True),
        sa.Column('list_status', sa.Enum(
            'draft', 'approved', 'sent', 'received', 'reconciled', name='confirmation_list_status'), default='draft', nullable=False),
        sa.Column('approved_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('due_date', sa.Date, nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index('ix_confirmation_lists_project_type', 'confirmation_lists', ['project_id', 'confirmation_type'])
    op.create_index('ix_confirmation_lists_project_status', 'confirmation_lists', ['project_id', 'list_status'])

    # --- confirmation_results ---
    op.create_table(
        'confirmation_results',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('confirmation_list_id', UUID(as_uuid=True), sa.ForeignKey('confirmation_lists.id'), nullable=False),
        sa.Column('result_status', sa.Enum(
            'confirmed', 'discrepancy', 'no_response', 'alternative_procedures', name='confirmation_result_status'), nullable=False),
        sa.Column('confirmed_amount', sa.Numeric(20, 2), nullable=True),
        sa.Column('discrepancy_amount', sa.Numeric(20, 2), nullable=True),
        sa.Column('discrepancy_reason', sa.Text, nullable=True),
        sa.Column('alternative_procedures_performed', sa.Text, nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('received_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_confirmation_results_list', 'confirmation_results', ['confirmation_list_id'])

    # --- confirmation_attachments ---
    op.create_table(
        'confirmation_attachments',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('confirmation_list_id', UUID(as_uuid=True), sa.ForeignKey('confirmation_lists.id'), nullable=False),
        sa.Column('file_name', sa.String(200), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_size', sa.Integer, nullable=True),
        sa.Column('uploaded_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_confirmation_attachments_list', 'confirmation_attachments', ['confirmation_list_id'])

    # --- going_concern_evaluations ---
    op.create_table(
        'going_concern_evaluations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('evaluation_date', sa.Date, nullable=False),
        sa.Column('conclusion', sa.Enum(
            'no_material_uncertainty', 'material_uncertainty_disclosed', 'qualified', 'adverse', name='going_concern_conclusion'), nullable=False),
        sa.Column('key_indicators', JSONB, nullable=True),
        sa.Column('management_plan', sa.Text, nullable=True),
        sa.Column('auditor_conclusion', sa.Text, nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index('ix_going_concern_project', 'going_concern_evaluations', ['project_id'])

    # --- going_concern_indicators ---
    op.create_table(
        'going_concern_indicators',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('evaluation_id', UUID(as_uuid=True), sa.ForeignKey('going_concern_evaluations.id'), nullable=False),
        sa.Column('indicator_type', sa.String(100), nullable=False),
        sa.Column('indicator_value', sa.String(200), nullable=True),
        sa.Column('threshold', sa.String(100), nullable=True),
        sa.Column('is_triggered', sa.Boolean, default=False, nullable=False),
        sa.Column('severity', sa.Enum('high', 'medium', 'low', name='severity_level'), nullable=False),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_going_concern_indicators_eval', 'going_concern_indicators', ['evaluation_id'])

    # --- archive_checklists ---
    op.create_table(
        'archive_checklists',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('item_code', sa.String(50), nullable=False),
        sa.Column('item_name', sa.String(200), nullable=False),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('check_status', sa.Enum(
            'pending', 'pass', 'fail', 'na', name='check_status_enum'), default='pending', nullable=False),
        sa.Column('checked_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_archive_checklists_project', 'archive_checklists', ['project_id'])

    # --- archive_modifications ---
    op.create_table(
        'archive_modifications',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('modification_type', sa.Enum(
            'addition', 'deletion', 'replacement', name='modification_type_enum'), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('request_reason', sa.Text, nullable=True),
        sa.Column('approval_status', sa.Enum('pending', 'approved', 'rejected', name='approval_status_enum'), default='pending', nullable=False),
        sa.Column('approved_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index('ix_archive_modifications_project', 'archive_modifications', ['project_id'])


def downgrade():
    op.drop_table('archive_modifications')
    op.drop_table('archive_checklists')
    op.drop_table('going_concern_indicators')
    op.drop_table('going_concern_evaluations')
    op.drop_table('confirmation_attachments')
    op.drop_table('confirmation_results')
    op.drop_table('confirmation_lists')
    op.drop_table('notifications')
