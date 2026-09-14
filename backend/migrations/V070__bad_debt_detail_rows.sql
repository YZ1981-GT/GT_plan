-- V070: 坏账准备明细表嵌套子表 bad_debt_detail_rows
-- 关联 Spec: workpaper-bad-debt-nested-structure Task 1.1（基础设施：V070 迁移）
-- 致同 2025 修订版 D2-3（应收账款坏账准备明细表）两层嵌套结构：
--   Parent_Row（计提类别，provision_method 有值）→ Child_Row（明细行，parent_row_id 指向父行）
-- provision_method 用 VARCHAR(30) + 应用层枚举，不建 PG enum type（避免 ALTER TYPE 事务限制）
-- 所有 CREATE 使用 IF NOT EXISTS，保证幂等可重入

-- ============================================================================
-- 1. bad_debt_detail_rows: 父行/子行统一存储 + 13 金额列 + 乐观锁 version
--    TimestampMixin 铁律：DDL 必须显式写 created_at/updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
-- ============================================================================

CREATE TABLE IF NOT EXISTS bad_debt_detail_rows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wp_index_id UUID NOT NULL REFERENCES wp_index(id) ON DELETE CASCADE,
    parent_row_id UUID REFERENCES bad_debt_detail_rows(id) ON DELETE CASCADE,
    provision_method VARCHAR(30),  -- 仅父行有值: INDIVIDUAL/CREDIT_RISK_AGING/CREDIT_RISK_OTHER/OTHER
    sort_order INT NOT NULL DEFAULT 0,
    row_label VARCHAR(200) NOT NULL,
    -- 13 金额列 (B~N，排除 A 项目名)
    amount_b NUMERIC(18,2),  -- 期初未审数
    amount_c NUMERIC(18,2),  -- 期初账项调整
    amount_d NUMERIC(18,2),  -- 重分类调整(期初)
    amount_e NUMERIC(18,2),  -- 期初审定数
    amount_f NUMERIC(18,2),  -- 本期计提
    amount_g NUMERIC(18,2),  -- 其他增加
    amount_h NUMERIC(18,2),  -- 本期转回
    amount_i NUMERIC(18,2),  -- 核销
    amount_j NUMERIC(18,2),  -- 其他减少
    amount_k NUMERIC(18,2),  -- 期末未审数
    amount_l NUMERIC(18,2),  -- 期末账项调整
    amount_m NUMERIC(18,2),  -- 重分类调整(期末)
    amount_n NUMERIC(18,2),  -- 期末审定数
    version INT NOT NULL DEFAULT 1,  -- 乐观锁
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- 2. 索引：查询优化 + 同 sheet 下 provision_method 唯一（仅父行有值）
-- ============================================================================

-- 按底稿索引查全部行
CREATE INDEX IF NOT EXISTS ix_bad_debt_rows_wp_index
    ON bad_debt_detail_rows (wp_index_id);

-- 按父行查子行
CREATE INDEX IF NOT EXISTS ix_bad_debt_rows_parent
    ON bad_debt_detail_rows (parent_row_id);

-- 同一 wp_index 下 provision_method 唯一（仅父行有值，子行 provision_method 为 NULL 不受约束）
CREATE UNIQUE INDEX IF NOT EXISTS uq_bad_debt_provision_method
    ON bad_debt_detail_rows (wp_index_id, provision_method)
    WHERE provision_method IS NOT NULL;

COMMENT ON TABLE bad_debt_detail_rows IS '坏账准备明细表 D2-3 嵌套子表：父行(计提类别)/子行(明细)统一存储';
COMMENT ON COLUMN bad_debt_detail_rows.provision_method IS '计提方法枚举(仅父行)：INDIVIDUAL|CREDIT_RISK_AGING|CREDIT_RISK_OTHER|OTHER';
COMMENT ON COLUMN bad_debt_detail_rows.parent_row_id IS '父行 ID(子行指向父行，父行为 NULL)';
COMMENT ON COLUMN bad_debt_detail_rows.version IS '乐观锁版本号，并发更新冲突检测';
