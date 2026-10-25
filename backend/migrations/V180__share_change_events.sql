-- V180：动态股比变动事件表
--
-- spec: consol-node-key-isolation-and-shared-context 任务 9.1
-- 设计: §十三（ADR-CNSC-009~010）
--
-- 每行代表一次股比变动事件；排序键 = (effective_date, sequence, id)。
-- G7 来源通过 (project_id, year, company_code, source_type, source_row_id)
-- 唯一约束实现幂等 upsert。
-- 所有 DDL 幂等；回滚见 R180。

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

-- 幂等 upsert 唯一约束（同一来源行只能产生一个事件）
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

-- 查询索引
CREATE INDEX IF NOT EXISTS ix_sce_project_year_company
    ON share_change_event (project_id, year, company_code);

-- 排序索引
CREATE INDEX IF NOT EXISTS ix_sce_sort
    ON share_change_event (project_id, year, company_code, effective_date, sequence, id);

COMMENT ON TABLE share_change_event IS
    '动态股比变动事件（1~N 次），按 (effective_date, sequence, id) 排序';
COMMENT ON COLUMN share_change_event.source_type IS
    '来源类型（如 g7-10-nci / g7-10-partialDisposal / manual）';
COMMENT ON COLUMN share_change_event.source_row_id IS
    '来源行唯一标识（G7 行 ID 或手动编号），用于幂等 upsert';
COMMENT ON COLUMN share_change_event.review_status IS
    'draft=草稿不入账 / approved=已确认可生成抵销 / revoked=已撤回';
