-- V207: 补建 tb_aux_balance_summary（PG 重建基线遗漏表，幂等）
--
-- 背景：该表为裸 SQL 表（无 ORM 映射），历史上由一次性 Alembic 迁移
--       ledger_aux_balance_summary_20260509.py 创建（dev-history 2296/2300 行），
--       不在 V 系列迁移清单里 → 清库重建（create_all + V 迁移重放）后缺失，
--       账套导入 pipeline「重建辅助汇总」阶段报 UndefinedTableError。
--
-- 🔴 列定义以 2026-10-27 清库前备份（gt_backup_pre_wipe.dump）中的原表 DDL 为准：
--   - dim_type / account_code / aux_code / record_count 均可空——真实账套存在
--     「有辅助类别无具体辅助项」的合法行（实测：职工福利事项 24 行、银行账户 4 行、
--     计提方式 2 行、减值方式 2 行 aux_code=NULL），NOT NULL 会让 rebuild 的
--     GROUP BY 插入报 NotNullViolationError。
--   - 金额列用裸 numeric（不设精度）避免超大金额溢出。
--   - 含 V064 方向字段 opening_direction / closing_direction 与 updated_at。
-- schema_drift_detector.KNOWN_ALLOWLIST 已将此表列为合法裸 SQL 表（无 ORM 映射是预期状态）。
CREATE TABLE IF NOT EXISTS tb_aux_balance_summary (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id        UUID NOT NULL,
    year              INTEGER NOT NULL,
    dim_type          VARCHAR(64),
    account_code      VARCHAR(64),
    account_name      VARCHAR(255),
    aux_code          VARCHAR(128),
    aux_name          VARCHAR(255),
    record_count      INTEGER DEFAULT 0,
    opening_balance   NUMERIC,
    debit_amount      NUMERIC,
    credit_amount     NUMERIC,
    closing_balance   NUMERIC,
    created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    opening_direction VARCHAR(10),
    closing_direction VARCHAR(10)
);
CREATE INDEX IF NOT EXISTS idx_tb_aux_summary_project_year
    ON tb_aux_balance_summary (project_id, year);
COMMENT ON TABLE tb_aux_balance_summary IS '辅助余额汇总（裸 SQL 表，无 ORM；导入后 rebuild_aux_balance_summary 重建）';
