"""B' Step 1: add partial indexes on Tb* tables for fast activate UPDATE.

activate 阶段对 4 张 Tb* 表做 `UPDATE SET is_deleted=false WHERE project_id=X
AND year=Y AND dataset_id=Z` —— 没有匹配的索引时会全表扫描。
加 partial index `(dataset_id) WHERE is_deleted=true`，让 UPDATE 的 WHERE 只扫
staged 行（远少于全量），预期 127s → 40-60s。

Revision ID: view_refactor_activate_index_20260510
Revises: sprint8_import_job_version_20260510
"""
from alembic import op


revision = "view_refactor_activate_index_20260510"
down_revision = "sprint8_import_job_version_20260510"
branch_labels = None
depends_on = None


TABLES = ["tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger"]


def upgrade():
    for tbl in TABLES:
        # partial index: 只对 staged 行（is_deleted=true）建索引
        # 索引大小 = staged 行数，远小于全表；activate UPDATE 通过索引直接定位目标行
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{tbl}_activate_staged "
            f"ON {tbl} (dataset_id) WHERE is_deleted = true"
        )


def downgrade():
    for tbl in TABLES:
        op.execute(f"DROP INDEX IF EXISTS idx_{tbl}_activate_staged")
