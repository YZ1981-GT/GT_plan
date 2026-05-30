-- V030: workpaper_sheet_classification 新增 functional_type 列
-- 底稿第三维度：功能行为类型（sampling/cutoff/aging/monthly_analysis/contract_ledger/reconciliation/...）

ALTER TABLE workpaper_sheet_classification
    ADD COLUMN IF NOT EXISTS functional_type VARCHAR(50);

-- 索引加速按 functional_type 查询
CREATE INDEX IF NOT EXISTS idx_wpsc_functional_type
    ON workpaper_sheet_classification (functional_type)
    WHERE functional_type IS NOT NULL;
