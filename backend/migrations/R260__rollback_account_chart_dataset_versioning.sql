-- R215: 仅在尚未产生跨 dataset 同码客户科目时可回退；若已有版本数据则唯一索引会 fail-closed。
DROP INDEX IF EXISTS uq_account_chart_project_dataset_code_source;
DROP INDEX IF EXISTS uq_account_chart_project_code_source_legacy;

CREATE UNIQUE INDEX IF NOT EXISTS uq_account_chart_project_code_source
    ON account_chart(project_id, account_code, source)
    WHERE is_deleted = false;
