-- V236: 报表最终值来源信封与运行记录（S5 / ADR-FPE-04、05、12、14）。
--
-- 每次 full / affected / stale 报表计算创建一条 report_generation_run；
-- financial_report.run_id 仅指向实际采用其计算结果的 run，provenance 保存双层最终值来源。
-- 存量行保持 NULL，由读取端标记 legacy；不做批量回填。

CREATE TABLE IF NOT EXISTS report_generation_run (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    trigger VARCHAR(40) NOT NULL,
    triggered_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    changed_rows INTEGER NOT NULL DEFAULT 0,
    recomputed_rows INTEGER NOT NULL DEFAULT 0,
    failed_rows INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT NULL,
    calc_version VARCHAR(100) NOT NULL,
    CONSTRAINT ck_report_generation_run_status
        CHECK (status IN ('running', 'succeeded', 'partial', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_report_generation_run_project_year_started
    ON report_generation_run (project_id, year, started_at DESC);

ALTER TABLE financial_report ADD COLUMN IF NOT EXISTS run_id UUID NULL;
ALTER TABLE financial_report ADD COLUMN IF NOT EXISTS provenance JSONB NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_financial_report_run'
    ) THEN
        ALTER TABLE financial_report
            ADD CONSTRAINT fk_financial_report_run
            FOREIGN KEY (run_id) REFERENCES report_generation_run(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_financial_report_project_year_run
    ON financial_report (project_id, year, run_id)
    WHERE run_id IS NOT NULL;
