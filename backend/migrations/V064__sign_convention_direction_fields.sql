-- V064: 符号约定方向字段 — tb_balance / tb_aux_balance / tb_ledger / tb_aux_ledger + direction_override 覆盖表
-- Requirements: 2.1, 3.3, 5.3, 6.6
-- 所有 DDL 使用 IF NOT EXISTS，保证幂等可重入

-- ============================================================================
-- 1. tb_balance: 期初/期末方向、方向来源、符号版本、异常 JSONB
-- ============================================================================

ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS opening_direction VARCHAR(10);
ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS opening_direction_source VARCHAR(50);
ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS closing_direction VARCHAR(10);
ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS closing_direction_source VARCHAR(50);
ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS sign_convention_version VARCHAR(30);
ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS sign_anomaly_flags JSONB;

-- ============================================================================
-- 2. tb_aux_balance: 同上字段
-- ============================================================================

ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS opening_direction VARCHAR(10);
ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS opening_direction_source VARCHAR(50);
ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS closing_direction VARCHAR(10);
ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS closing_direction_source VARCHAR(50);
ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS sign_convention_version VARCHAR(30);
ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS sign_anomaly_flags JSONB;

-- ============================================================================
-- 3. tb_ledger: 发生方向和来源
-- ============================================================================

ALTER TABLE tb_ledger ADD COLUMN IF NOT EXISTS entry_direction VARCHAR(10);
ALTER TABLE tb_ledger ADD COLUMN IF NOT EXISTS entry_direction_source VARCHAR(50);

-- ============================================================================
-- 4. tb_aux_ledger: 发生方向和来源
-- ============================================================================

ALTER TABLE tb_aux_ledger ADD COLUMN IF NOT EXISTS entry_direction VARCHAR(10);
ALTER TABLE tb_aux_ledger ADD COLUMN IF NOT EXISTS entry_direction_source VARCHAR(50);

-- ============================================================================
-- 5. direction_override: 独立方向覆盖 overlay 表
-- ============================================================================

CREATE TABLE IF NOT EXISTS direction_override (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    dataset_id UUID NOT NULL,
    table_name VARCHAR(30) NOT NULL,
    record_id UUID NOT NULL,
    original_direction VARCHAR(10),
    override_direction VARCHAR(10) NOT NULL,
    override_reason TEXT NOT NULL,
    override_by UUID REFERENCES staff_members(id),
    override_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for querying overrides by project + table
CREATE INDEX IF NOT EXISTS idx_direction_override_project_table
    ON direction_override(project_id, table_name);

-- Index for querying overrides by record
CREATE INDEX IF NOT EXISTS idx_direction_override_record
    ON direction_override(record_id);
