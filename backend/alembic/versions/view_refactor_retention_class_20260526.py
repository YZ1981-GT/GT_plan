"""F53 / Sprint 8.38: ImportArtifact 新增 retention_class + retention_expires_at。

背景（requirements F53 / design D13.4）：
留档合规保留期差异化：
  - transient（默认）：90 天过期，purge 任务物理删
  - archived          ：10 年过期，元数据永久保留
  - legal_hold        ：法定保留，永不删除

新增字段：
- ``retention_class VARCHAR(20) NOT NULL DEFAULT 'transient'``
- ``retention_expires_at TIMESTAMP WITH TIME ZONE NULL``（legal_hold 时为 NULL）

新增索引：
- ``idx_import_artifacts_retention (retention_class, retention_expires_at)``：
  purge 任务按 "transient 且已过期" 扫描的专用复合索引。

Revision ID: view_refactor_retention_class_20260526
Revises: view_refactor_mapping_history_fp_20260525
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "view_refactor_retention_class_20260526"
down_revision = "view_refactor_mapping_history_fp_20260525"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "import_artifacts",
        sa.Column(
            "retention_class",
            sa.String(20),
            server_default=sa.text("'transient'"),
            nullable=False,
        ),
    )
    op.add_column(
        "import_artifacts",
        sa.Column(
            "retention_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_import_artifacts_retention",
        "import_artifacts",
        ["retention_class", "retention_expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_import_artifacts_retention",
        table_name="import_artifacts",
    )
    op.drop_column("import_artifacts", "retention_expires_at")
    op.drop_column("import_artifacts", "retention_class")
