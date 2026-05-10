"""B' Day 7: one-shot UPDATE legacy active rows is_deleted=false.

背景（ADR-002 三阶段迁移策略）：
- Day 0 deploy B' 代码后，pipeline 新写入 is_deleted=false，查询走 get_active_filter
- Day 0 ~ Day 7 观察期：业务查询兜底分支仍用 is_deleted=false，**老 active 数据的
  物理行 is_deleted 仍为 true** —— 此时通过 get_active_filter 能命中 dataset_id
  active 的行，但 is_deleted=false 兜底会过滤掉老行
- Day 7（本迁移）：一次性 UPDATE 所有当前 active dataset 对应的 Tb* 行
  is_deleted=true → false，消除老数据与新数据的语义不一致
- Day 30：DROP INDEX `idx_tb_*_activate_staged`（55MB 回收）

设计要点：
- **分块 UPDATE + 小睡**：避免单次 UPDATE 200 万行锁表
  （批大小 100k / 每批后 pg_sleep(1) 让出 I/O）
- **仅 UPDATE active dataset 对应的 Tb* 行**：rolled_back / superseded 数据保留
  is_deleted=true（它们不可见）
- **幂等**：重跑只会 UPDATE 剩余的 is_deleted=true 行，不会误改已 UPDATE 的

性能预期（基于 YG2101 128MB/200 万行实测）：
- 老 activate 单次 UPDATE 200 万行 ≈ 127s（会锁表）
- 本迁移分块 100k × 20 次 + pg_sleep(1) × 20 ≈ 180-200s（不锁表）
- 是**一次性痛苦换永远不再痛**

Revision ID: view_refactor_cleanup_old_deleted_20260517
Revises: view_refactor_activate_index_20260510
"""
from alembic import op


revision = "view_refactor_cleanup_old_deleted_20260517"
down_revision = "view_refactor_activate_index_20260510"
branch_labels = None
depends_on = None


TABLES = ["tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger"]


def upgrade():
    """一次性 UPDATE 所有 active dataset 对应的 Tb* 行 is_deleted=true → false。

    SQLite / 非 PG 环境跳过（Day 7 迁移仅对 PG 生产库有意义）。
    """
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect != "postgresql":
        # 测试环境（SQLite）跳过
        return

    # 每张表分块 UPDATE，批大小 100k，每批后小睡 1s
    for tbl in TABLES:
        op.execute(f"""
            DO $$
            DECLARE
                batch_size INT := 100000;
                affected INT;
            BEGIN
                LOOP
                    UPDATE {tbl} SET is_deleted = false
                    WHERE ctid IN (
                        SELECT ctid FROM {tbl}
                        WHERE is_deleted = true
                          AND dataset_id IN (
                            SELECT id FROM ledger_datasets WHERE status = 'active'
                          )
                        LIMIT batch_size
                    );
                    GET DIAGNOSTICS affected = ROW_COUNT;
                    EXIT WHEN affected = 0;
                    PERFORM pg_sleep(1);
                END LOOP;
            END $$;
        """)


def downgrade():
    """不可降级：UPDATE 回 is_deleted=true 会让业务查询立即看不到数据。

    如需回滚 B' 架构，应走代码层 feature flag（ledger_import_view_refactor_enabled=false）
    降级单项目到老逻辑，而不是改数据。
    """
    pass
