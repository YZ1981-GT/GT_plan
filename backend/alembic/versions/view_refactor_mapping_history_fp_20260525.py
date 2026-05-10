"""F52 / Sprint 8.34: 扩展 import_column_mapping_history 支持文件指纹 + 历史链。

背景（requirements F52 / design D13.3）：
- ``file_fingerprint``：细粒度 SHA1（sheet_name + header[:20] + software_hint），
  同模板文件二次导入精确命中，节省 > 50% 列映射时间。
- ``override_parent_id``：用户在 detect 阶段拿到历史 mapping 自动应用 + 手动
  修改几列后再次保存时，新记录的 override_parent_id 指向被覆盖的上一代，
  形成可追溯的版本链。

新增字段：
- ``file_fingerprint VARCHAR(40) NULL``（SHA1 十六进制 40 字符）
- ``override_parent_id UUID NULL, FK → import_column_mapping_history(id)
  ON DELETE SET NULL``（父记录删除时整条链不级联删除）

新增索引：
- ``idx_icmh_project_file_fp (project_id, file_fingerprint, created_at)``：
  detect 阶段按 (project_id, file_fingerprint) 命中 + ``created_at > now - 30d``
  窗口过滤的专用复合索引。

Revision ID: view_refactor_mapping_history_fp_20260525
Revises: view_refactor_dataset_binding_20260519
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


revision = "view_refactor_mapping_history_fp_20260525"
down_revision = "view_refactor_dataset_binding_20260519"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "import_column_mapping_history",
        sa.Column("file_fingerprint", sa.String(40), nullable=True),
    )
    op.add_column(
        "import_column_mapping_history",
        sa.Column("override_parent_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_icmh_override_parent",
        "import_column_mapping_history",
        "import_column_mapping_history",
        ["override_parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_icmh_project_file_fp",
        "import_column_mapping_history",
        ["project_id", "file_fingerprint", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_icmh_project_file_fp",
        table_name="import_column_mapping_history",
    )
    op.drop_constraint(
        "fk_icmh_override_parent",
        "import_column_mapping_history",
        type_="foreignkey",
    )
    op.drop_column("import_column_mapping_history", "override_parent_id")
    op.drop_column("import_column_mapping_history", "file_fingerprint")
