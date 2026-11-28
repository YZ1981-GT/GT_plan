-- V215: 客户科目表按 dataset 版本化，允许 active 与 staged/superseded 同时保留。
DROP INDEX IF EXISTS uq_account_chart_project_code_source;

CREATE UNIQUE INDEX IF NOT EXISTS uq_account_chart_project_dataset_code_source
    ON account_chart(project_id, dataset_id, account_code, source)
    WHERE is_deleted = false AND dataset_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_account_chart_project_code_source_legacy
    ON account_chart(project_id, account_code, source)
    WHERE is_deleted = false AND dataset_id IS NULL;
