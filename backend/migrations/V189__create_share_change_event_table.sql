-- V189：补建 share_change_event 表
--
-- V180 已登记到 schema_version 但表未实际建成，此迁移幂等补建。
-- DDL 完全对齐 ORM share_change_event_models.ShareChangeEvent。

CREATE TABLE IF NOT EXISTS share_change_event (
    id                   UUID          NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id           UUID          NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year                 INTEGER       NOT NULL,
    company_code         VARCHAR(50)   NOT NULL,
    node_key             VARCHAR(100),

    -- 排序与日期
    effective_date       DATE,
    sequence             INTEGER       NOT NULL DEFAULT 0,

    -- 比例（百分数 0~100，精度 6 位小数）
    before_ratio         NUMERIC(12, 6),
    after_ratio          NUMERIC(12, 6),
    ratio_delta          NUMERIC(12, 6),

    -- 业务分类
    change_type          VARCHAR(50),
    amount               NUMERIC(18, 2),
    equity_adjustment    NUMERIC(18, 2),

    -- 来源溯源
    source_type          VARCHAR(50),
    source_row_id        VARCHAR(200),
    source_sheet_key     VARCHAR(100),

    -- 状态与版本
    review_status        VARCHAR(20)   NOT NULL DEFAULT 'draft'
                         CHECK (review_status IN ('draft', 'approved', 'revoked')),
    calculation_version  INTEGER       NOT NULL DEFAULT 0,

    -- 扩展数据
    detail               JSONB,

    -- 审计
    created_by           UUID,
    created_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- 幂等唯一约束（G7 来源行只能产生一个事件）
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_share_change_event_source'
    ) THEN
        ALTER TABLE share_change_event
            ADD CONSTRAINT uq_share_change_event_source
            UNIQUE (project_id, year, company_code, source_type, source_row_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_sce_project_year_company
    ON share_change_event (project_id, year, company_code);

CREATE INDEX IF NOT EXISTS ix_sce_sort
    ON share_change_event (project_id, year, company_code, effective_date, sequence, id);
