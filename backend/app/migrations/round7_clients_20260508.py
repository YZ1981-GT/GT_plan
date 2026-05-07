"""Round 7: clients 主数据 + project_tags [R7-S3-06 Task 30]

Revision ID: round7_clients_20260508
Revises: round7_section_progress_gin
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'round7_clients_20260508'
down_revision = 'round7_section_progress_gin'
branch_labels = None
depends_on = None


def upgrade():
    # clients 主数据表
    op.create_table(
        'clients',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('normalized_name', sa.String(200), nullable=False),
        sa.Column('industry', sa.String(100), nullable=True),
        sa.Column('listed', sa.Boolean, server_default='false'),
        sa.Column('parent_id', UUID(as_uuid=True), sa.ForeignKey('clients.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_clients_normalized_name', 'clients', ['normalized_name'], unique=True)

    # Project.client_id FK（nullable，保留 client_name 冗余向后兼容）
    op.add_column('projects', sa.Column('client_id', UUID(as_uuid=True), sa.ForeignKey('clients.id'), nullable=True))

    # project_tags 关联表
    op.create_table(
        'project_tags',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tag', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_project_tags_project_tag', 'project_tags', ['project_id', 'tag'], unique=True)


def downgrade():
    op.drop_table('project_tags')
    op.drop_column('projects', 'client_id')
    op.drop_table('clients')
