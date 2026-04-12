"""创建第四阶段AI相关表（12张AI赋能表）

Revision ID: 016
Revises: 015
Create Date: 2025-01-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade():
    # --- ai_model_config ---
    op.create_table(
        'ai_model_config',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('model_type', sa.Enum(
            'chat', 'embedding', 'ocr', name='ai_model_type_enum'), nullable=False),
        sa.Column('provider', sa.Enum(
            'ollama', 'openai_compatible', 'paddleocr', name='ai_provider_enum'), nullable=False),
        sa.Column('endpoint_url', sa.String(500), nullable=True),
        sa.Column('is_active', sa.Boolean, default=False, nullable=False),
        sa.Column('context_window', sa.Integer, nullable=True),
        sa.Column('performance_notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_ai_model_config_name_type', 'ai_model_config', ['model_name', 'model_type'], unique=True)

    # --- document_scan ---
    op.create_table(
        'document_scan',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('company_code', sa.String(50), nullable=True),
        sa.Column('year', sa.String(4), nullable=True),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_name', sa.String(200), nullable=False),
        sa.Column('file_size', sa.Integer, nullable=True),
        sa.Column('document_type', sa.Enum(
            'sales_invoice', 'purchase_invoice', 'bank_receipt', 'bank_statement',
            'outbound_order', 'inbound_order', 'logistics_order', 'voucher',
            'expense_report', 'toll_invoice', 'contract', 'customs_declaration', 'unknown',
            name='document_type_enum'), nullable=False),
        sa.Column('recognition_status', sa.Enum(
            'pending', 'processing', 'completed', 'failed', name='recognition_status_enum'),
            default='pending', nullable=False),
        sa.Column('uploaded_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_document_scan_project_type', 'document_scan', ['project_id', 'document_type'])
    op.create_index('ix_document_scan_status', 'document_scan', ['recognition_status'])

    # --- document_extracted ---
    op.create_table(
        'document_extracted',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('document_scan_id', UUID(as_uuid=True), sa.ForeignKey('document_scan.id'), nullable=False),
        sa.Column('field_name', sa.String(100), nullable=False),
        sa.Column('field_value', sa.Text, nullable=True),
        sa.Column('confidence_score', sa.Numeric(3, 2), nullable=True),
        sa.Column('human_confirmed', sa.Boolean, default=False, nullable=False),
        sa.Column('confirmed_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_document_extracted_scan', 'document_extracted', ['document_scan_id'])
    op.create_index('ix_document_extracted_confidence', 'document_extracted', ['confidence_score'])

    # --- document_match ---
    op.create_table(
        'document_match',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('document_scan_id', UUID(as_uuid=True), sa.ForeignKey('document_scan.id'), nullable=False),
        sa.Column('matched_voucher_no', sa.String(50), nullable=True),
        sa.Column('matched_account_code', sa.String(50), nullable=True),
        sa.Column('matched_amount', sa.Numeric(20, 2), nullable=True),
        sa.Column('match_result', sa.Enum(
            'matched', 'mismatched', 'unmatched', name='match_result_enum'), nullable=False),
        sa.Column('difference_amount', sa.Numeric(20, 2), nullable=True),
        sa.Column('difference_description', sa.Text, nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_document_match_scan', 'document_match', ['document_scan_id'])
    op.create_index('ix_document_match_result', 'document_match', ['match_result'])

    # --- ai_content ---
    op.create_table(
        'ai_content',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('workpaper_id', UUID(as_uuid=True), nullable=True),
        sa.Column('content_type', sa.Enum(
            'data_fill', 'analytical_review', 'risk_alert', 'test_summary', 'note_draft',
            name='ai_content_type_enum'), nullable=False),
        sa.Column('content_text', sa.Text, nullable=False),
        sa.Column('data_sources', JSONB, nullable=True),
        sa.Column('generation_model', sa.String(100), nullable=True),
        sa.Column('generation_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('confidence_level', sa.Enum(
            'high', 'medium', 'low', name='confidence_level_enum'), nullable=True),
        sa.Column('confirmation_status', sa.Enum(
            'pending', 'accepted', 'modified', 'rejected', 'regenerated',
            name='ai_confirmation_status_enum'), default='pending', nullable=False),
        sa.Column('confirmed_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('modification_note', sa.Text, nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_ai_content_project_workpaper_type', 'ai_content', ['project_id', 'workpaper_id', 'content_type'])
    op.create_index('ix_ai_content_confirmation', 'ai_content', ['confirmation_status'])

    # --- contracts ---
    op.create_table(
        'contracts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('company_code', sa.String(50), nullable=True),
        sa.Column('contract_no', sa.String(100), nullable=True),
        sa.Column('party_a', sa.String(200), nullable=True),
        sa.Column('party_b', sa.String(200), nullable=True),
        sa.Column('contract_amount', sa.Numeric(20, 2), nullable=True),
        sa.Column('contract_date', sa.Date, nullable=True),
        sa.Column('effective_date', sa.Date, nullable=True),
        sa.Column('expiry_date', sa.Date, nullable=True),
        sa.Column('contract_type', sa.Enum(
            'sales', 'purchase', 'service', 'lease', 'loan', 'guarantee', 'other',
            name='contract_type_enum'), nullable=True),
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('analysis_status', sa.Enum(
            'pending', 'analyzing', 'completed', 'failed', name='contract_analysis_status_enum'),
            default='pending', nullable=False),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_contracts_project_type', 'contracts', ['project_id', 'contract_type'])

    # --- contract_extracted ---
    op.create_table(
        'contract_extracted',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('contract_id', UUID(as_uuid=True), sa.ForeignKey('contracts.id'), nullable=False),
        sa.Column('clause_type', sa.Enum(
            'amount', 'payment_terms', 'delivery_terms', 'penalty', 'guarantee',
            'pledge', 'related_party', 'special_terms', 'pricing', 'duration',
            name='clause_type_enum'), nullable=False),
        sa.Column('clause_content', sa.Text, nullable=False),
        sa.Column('confidence_score', sa.Numeric(3, 2), nullable=True),
        sa.Column('human_confirmed', sa.Boolean, default=False, nullable=False),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_contract_extracted_contract_clause', 'contract_extracted', ['contract_id', 'clause_type'])

    # --- contract_wp_link ---
    op.create_table(
        'contract_wp_link',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('contract_id', UUID(as_uuid=True), sa.ForeignKey('contracts.id'), nullable=False),
        sa.Column('workpaper_id', UUID(as_uuid=True), nullable=False),
        sa.Column('link_type', sa.Enum(
            'revenue_recognition', 'cutoff_test', 'contingent_liability',
            'related_party', 'guarantee', name='contract_link_type_enum'), nullable=False),
        sa.Column('link_description', sa.Text, nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_contract_wp_link_contract_workpaper', 'contract_wp_link', ['contract_id', 'workpaper_id'])

    # --- evidence_chain ---
    op.create_table(
        'evidence_chain',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('chain_type', sa.Enum(
            'revenue', 'purchase', 'expense', name='evidence_chain_type_enum'), nullable=False),
        sa.Column('source_document_id', UUID(as_uuid=True), nullable=False),
        sa.Column('target_document_id', UUID(as_uuid=True), nullable=True),
        sa.Column('chain_step', sa.Integer, nullable=False),
        sa.Column('match_status', sa.Enum(
            'matched', 'mismatched', 'missing', name='chain_match_status_enum'), nullable=False),
        sa.Column('mismatch_description', sa.Text, nullable=True),
        sa.Column('risk_level', sa.Enum(
            'high', 'medium', 'low', name='risk_level_enum'), nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_evidence_chain_project_type', 'evidence_chain', ['project_id', 'chain_type'])
    op.create_index('ix_evidence_chain_risk', 'evidence_chain', ['risk_level'])

    # --- knowledge_index ---
    op.create_table(
        'knowledge_index',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('source_type', sa.Enum(
            'trial_balance', 'journal', 'auxiliary', 'contract', 'document_scan',
            'workpaper', 'adjustment', 'elimination', 'confirmation',
            'review_comment', 'prior_year_summary', name='knowledge_source_type_enum'), nullable=False),
        sa.Column('source_id', UUID(as_uuid=True), nullable=False),
        sa.Column('content_text', sa.Text, nullable=False),
        sa.Column('embedding_vector', sa.String(5000), nullable=True),
        sa.Column('chunk_index', sa.Integer, nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_knowledge_index_project_source', 'knowledge_index', ['project_id', 'source_type'])

    # --- ai_chat_history ---
    op.create_table(
        'ai_chat_history',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('conversation_id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('role', sa.Enum(
            'user', 'assistant', 'system', name='chat_role_enum'), nullable=False),
        sa.Column('message_text', sa.Text, nullable=False),
        sa.Column('referenced_sources', JSONB, nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('token_count', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_ai_chat_project_conv', 'ai_chat_history', ['project_id', 'conversation_id', 'created_at'])
    op.create_index('ix_ai_chat_user', 'ai_chat_history', ['user_id'])

    # --- confirmation_ai_check ---
    op.create_table(
        'confirmation_ai_check',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('confirmation_list_id', UUID(as_uuid=True), sa.ForeignKey('confirmation_lists.id'), nullable=False),
        sa.Column('check_type', sa.Enum(
            'address_verify', 'reply_ocr', 'amount_compare', 'seal_check',
            name='confirmation_check_type_enum'), nullable=False),
        sa.Column('check_result', JSONB, nullable=True),
        sa.Column('risk_level', sa.Enum(
            'high', 'medium', 'low', 'pass', name='confirmation_risk_level_enum'), nullable=True),
        sa.Column('human_confirmed', sa.Boolean, default=False, nullable=False),
        sa.Column('confirmed_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_confirmation_ai_check_list_type', 'confirmation_ai_check', ['confirmation_list_id', 'check_type'])


def downgrade():
    op.drop_table('confirmation_ai_check')
    op.drop_table('ai_chat_history')
    op.drop_table('knowledge_index')
    op.drop_table('evidence_chain')
    op.drop_table('contract_wp_link')
    op.drop_table('contract_extracted')
    op.drop_table('contracts')
    op.drop_table('ai_content')
    op.drop_table('document_match')
    op.drop_table('document_extracted')
    op.drop_table('document_scan')
    op.drop_table('ai_model_config')
