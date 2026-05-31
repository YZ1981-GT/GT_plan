-- V034: 合并模块 schema 基线 + consol_lock 三列（consol-phase0-core-pipeline / Phase 0）
-- 注：原编号 V027，因与 work 分支底稿模块迁移（V027~V033）撞号，重编号为 V034（避开冲突）。
--
-- 设计要点（design.md §4.1 / 需求 4 / ADR-CONSOL-003）：
-- 1. 合并模块所有表此前从未进 D6 迁移（grep migrations/*.sql = 0 命中），
--    全靠 init_tables.py 的 create_all() 首次建表。create_all 只在表不存在时建表、
--    对已存在表永不 ALTER → 任何后加 ORM 字段在老库永不出现（C1 / B-lock / C3 根因）。
-- 2. 本迁移把合并核心表 ORM 现状固化为幂等 SQL（CREATE TABLE IF NOT EXISTS），并补 3 个新列：
--    - projects.consol_lock / consol_lock_by / consol_lock_at（合并锁定，F2/C3）
--    - consol_trial.consolidation_breakdown（B1 provenance 溯源）
-- 3. 双路径收敛：对已部署老库（create_all 已建表）仅补缺列（ADD COLUMN IF NOT EXISTS），
--    不重建已有表；对全新库 CREATE TYPE/TABLE IF NOT EXISTS 补建。两条路径都收敛到"列齐全"。
-- 4. 全部 CREATE TYPE / CREATE TABLE / ALTER 均幂等（IF NOT EXISTS 或 DO 块 pg_type 检查），
--    重复执行不抛 DuplicateType/DuplicateTable/DuplicateColumn，不中断 D6 管线
--    （需求 4.5 / 错误场景 E6 / 风险 R1）。
-- 5. 表内容 + enum 类型均由 ORM metadata（consolidation_models.py）精确反推，与 create_all 一致。
--
-- 执行顺序（对全新纯迁移库的正确性保障）：enum 类型 → CREATE TABLE → projects 补列
--   → consol_trial 补列 → GIN 索引。consol_trial ALTER 必须在 CREATE TABLE 之后。
--
-- 双路径幂等实测说明：本平台无法本地起 Docker/PG，V034 双路径（老库补列 + 新库补建）
-- 幂等实测待 start-dev.bat 由用户验证（任务 1.5）。

-- =========================================================================
-- 1) PG enum 类型（合并核心表依赖；CREATE TYPE 无 IF NOT EXISTS，用 DO 块 pg_type 检查幂等）
-- =========================================================================
DO $body$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'accountcategory') THEN
        CREATE TYPE accountcategory AS ENUM ('asset', 'liability', 'equity', 'revenue', 'expense');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'eliminationentrytype') THEN
        CREATE TYPE eliminationentrytype AS ENUM ('equity', 'internal_trade', 'internal_ar_ap', 'unrealized_profit', 'other');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reviewstatusenum') THEN
        CREATE TYPE reviewstatusenum AS ENUM ('draft', 'pending_review', 'approved', 'rejected');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'scopecompanytype') THEN
        CREATE TYPE scopecompanytype AS ENUM ('parent', 'subsidiary', 'associate', 'joint_venture');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'inclusionreason') THEN
        CREATE TYPE inclusionreason AS ENUM ('subsidiary', 'associate', 'joint_venture', 'special_purpose');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'scopechangetype') THEN
        CREATE TYPE scopechangetype AS ENUM ('none', 'new_inclusion', 'exclusion', 'method_change');
    END IF;
END
$body$;

-- =========================================================================
-- 2) 合并核心表基线固化（CREATE TABLE IF NOT EXISTS，与 ORM 精确一致）
--    对已 create_all 的老库 no-op；对全新库补建。
-- =========================================================================

-- 2.1 consol_scope（合并范围表）
CREATE TABLE IF NOT EXISTS consol_scope (
    id UUID NOT NULL,
    project_id UUID NOT NULL,
    year INTEGER NOT NULL,
    company_code VARCHAR NOT NULL,
    company_name VARCHAR,
    company_type scopecompanytype,
    ownership_ratio NUMERIC(5, 2),
    is_included BOOLEAN DEFAULT 'true' NOT NULL,
    inclusion_reason inclusionreason,
    exclusion_reason TEXT,
    scope_change_type scopechangetype DEFAULT 'none' NOT NULL,
    scope_change_description TEXT,
    is_deleted BOOLEAN NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(project_id) REFERENCES projects (id)
);

-- 2.2 consol_trial（合并试算表 — B1 核心表）
CREATE TABLE IF NOT EXISTS consol_trial (
    id UUID NOT NULL,
    project_id UUID NOT NULL,
    year INTEGER NOT NULL,
    standard_account_code VARCHAR NOT NULL,
    account_name VARCHAR,
    account_category accountcategory,
    individual_sum NUMERIC(20, 2) DEFAULT '0' NOT NULL,
    consol_adjustment NUMERIC(20, 2) DEFAULT '0' NOT NULL,
    consol_elimination NUMERIC(20, 2) DEFAULT '0' NOT NULL,
    consol_amount NUMERIC(20, 2) DEFAULT '0' NOT NULL,
    is_deleted BOOLEAN NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(project_id) REFERENCES projects (id)
);

-- 2.3 consol_worksheet（合并差额表 — 单一事实源主干，节点×科目×年度）
CREATE TABLE IF NOT EXISTS consol_worksheet (
    id UUID NOT NULL,
    project_id UUID NOT NULL,
    node_company_code VARCHAR(50) NOT NULL,
    account_code VARCHAR(50) NOT NULL,
    year INTEGER NOT NULL,
    adjustment_debit NUMERIC(20, 2) DEFAULT '0' NOT NULL,
    adjustment_credit NUMERIC(20, 2) DEFAULT '0' NOT NULL,
    elimination_debit NUMERIC(20, 2) DEFAULT '0' NOT NULL,
    elimination_credit NUMERIC(20, 2) DEFAULT '0' NOT NULL,
    net_difference NUMERIC(20, 2) DEFAULT '0' NOT NULL,
    children_amount_sum NUMERIC(20, 2) DEFAULT '0' NOT NULL,
    consolidated_amount NUMERIC(20, 2) DEFAULT '0' NOT NULL,
    is_deleted BOOLEAN NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(project_id) REFERENCES projects (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_consol_worksheet_node_account_year
    ON consol_worksheet (project_id, node_company_code, account_code, year)
    WHERE is_deleted = false;

-- 2.4 elimination_entries（抵消分录表）
CREATE TABLE IF NOT EXISTS elimination_entries (
    id UUID NOT NULL,
    project_id UUID NOT NULL,
    year INTEGER NOT NULL,
    entry_no VARCHAR NOT NULL,
    entry_type eliminationentrytype NOT NULL,
    description TEXT,
    account_code VARCHAR NOT NULL,
    account_name VARCHAR,
    debit_amount NUMERIC(20, 2) DEFAULT '0' NOT NULL,
    credit_amount NUMERIC(20, 2) DEFAULT '0' NOT NULL,
    lines JSONB,
    entry_group_id UUID NOT NULL,
    related_company_codes JSONB,
    is_continuous BOOLEAN DEFAULT 'false' NOT NULL,
    prior_year_entry_id UUID,
    review_status reviewstatusenum DEFAULT 'draft' NOT NULL,
    reviewer_id UUID,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    is_deleted BOOLEAN NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    created_by UUID,
    updated_by UUID,
    PRIMARY KEY (id),
    FOREIGN KEY(project_id) REFERENCES projects (id),
    FOREIGN KEY(reviewer_id) REFERENCES users (id),
    FOREIGN KEY(created_by) REFERENCES users (id),
    FOREIGN KEY(updated_by) REFERENCES users (id)
);

-- 注：其余合并表（companies / internal_trade / internal_ar_ap / goodwill_calc /
--     minority_interest / forex_translation / component_auditors /
--     component_instructions / component_results / consol_query_template）
--     当前仍由 create_all 维护，后续 Phase 迁移补全基线（本 Phase 0 仅固化 B1/B2 核心 4 表）。

-- =========================================================================
-- 3) projects 表加 consol_lock 三列（B-lock / C3 / F2 根因）
-- =========================================================================
ALTER TABLE projects ADD COLUMN IF NOT EXISTS consol_lock BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS consol_lock_by UUID;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS consol_lock_at TIMESTAMPTZ;

-- =========================================================================
-- 4) consol_trial 加 consolidation_breakdown provenance（B1 溯源；CREATE TABLE 之后）
-- =========================================================================
ALTER TABLE consol_trial ADD COLUMN IF NOT EXISTS consolidation_breakdown JSONB;

-- =========================================================================
-- 5) provenance 查询索引（GIN，软删除过滤）
-- =========================================================================
CREATE INDEX IF NOT EXISTS idx_consol_trial_breakdown
    ON consol_trial USING gin (consolidation_breakdown)
    WHERE is_deleted = false;
