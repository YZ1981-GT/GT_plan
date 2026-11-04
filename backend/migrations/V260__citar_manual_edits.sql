-- V260: CITAR 表格人工修改（spec citar-table-manual-edit）
--
-- 编号说明：本分支最高 V230，其他分支已用到 V251，取 V260 避免合并时撞号（MigrationRunner 按数字去重）。
--
-- 1. financial_report.manual_amounts：审定报表手工值（R6）。
--    {"current": {"value": "…", "auto": "…"}, "prior": {…}, "by": 用户 id, "at": 时间}；
--    current_period_amount / prior_period_amount 始终是生效值（手工优先），重新生成只刷新 auto。
-- 2. ledger_manual_edits：科目余额表 / 序时账人工修改日志（R3~R5）。
--    修改直接写当前数据集的行；本表记每次修改前后的值，恢复取该行第一次修改的 before。
--    action：edit 人工修改 / restore 恢复导入原值 / cascade 末级修改带动上级同步。
-- 三层一致：ORM backend/app/models/report_models.py FinancialReport.manual_amounts、
-- backend/app/models/ledger_edit_models.py LedgerManualEdit；service report_manual_service / ledger_edit_service。
ALTER TABLE financial_report
    ADD COLUMN IF NOT EXISTS manual_amounts JSONB;
COMMENT ON COLUMN financial_report.manual_amounts IS '审定报表手工值 {current|prior: {value, auto}, by, at}；金额列为生效值';

CREATE TABLE IF NOT EXISTS ledger_manual_edits (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    dataset_id UUID,
    table_name VARCHAR(20) NOT NULL,
    row_id UUID NOT NULL,
    action VARCHAR(10) NOT NULL,
    before JSONB NOT NULL DEFAULT '{}'::jsonb,
    after JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason TEXT,
    edited_by UUID REFERENCES users(id) ON DELETE SET NULL,
    edited_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ledger_manual_edits_project_year_table
    ON ledger_manual_edits (project_id, year, table_name);
CREATE INDEX IF NOT EXISTS idx_ledger_manual_edits_row
    ON ledger_manual_edits (row_id);
COMMENT ON TABLE ledger_manual_edits IS '科目余额表 / 序时账人工修改日志（before / after 为修改的字段）';
