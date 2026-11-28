-- V275: 补齐 6 张「历史 create_all 建、迁移从未覆盖」的运行时表
--
-- 背景（2026-11-24 平台技术债清偿，探针证据 tmp_platform_debt_fix/probes/）：
-- 平台有两类表从未被任何 V*.sql CREATE 过：
--   A. 早期经 Base.metadata.create_all 建到共享库的历史基线表（后来 ORM 改名/删模型，
--      但裸 SQL 仍在用）—— 空库引导（init_tables.py create_all + 全量迁移）后缺失；
--   B. 生产代码裸 SQL 引用、但「ORM 无模型 + 迁移无 CREATE + 共享库也没有」的幽灵表
--      —— 写入/查询路径被 try/except 吞掉，功能静默失效。
--
-- 本迁移把 A/B 两类共 6 张表补齐为迁移持有（幂等 IF NOT EXISTS；共享库已存在的表
-- 结构逐列对齐现网 schema，不改任何现有列）：
--   1. tb_aux_balance_summary        —— A 类（smart_import_engine 写 / ledger_penetration 读）
--   2. review_conversation_exports   —— A 类（rc_enhanced_service）
--   3. review_conversation_participants —— A 类（rc_enhanced_service）
--   4. linkage_audit_log             —— B 类（stale_propagation_engine 写 / linkage_bus 读）
--   5. seed_load_history             —— B 类（template_library_mgmt 3 处）
--   6. wp_review_records             —— B 类（quality_rating_service._review_depth_score）
--
-- 列形状来源：
--   1~3 = 共享库现网 information_schema 逐列 dump（2026-11-24）；
--   4~6 = 生产 SQL 的 INSERT/SELECT 列清单反推。
-- work_hours_legacy（V117 已废弃、无生产引用）不重建，留在 drift detector 白名单。
--
-- 幂等性：全部 CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS；
-- 对已存在的表不做任何 ALTER（现网列已在，历史数据不动）。

-- ============================================================
-- 1. tb_aux_balance_summary（辅助余额汇总表，dim_type 口径 = V083 统一后）
-- ============================================================
CREATE TABLE IF NOT EXISTS tb_aux_balance_summary (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL,
    year            INTEGER NOT NULL,
    account_code    VARCHAR,
    account_name    VARCHAR,
    dim_type        VARCHAR,
    aux_code        VARCHAR,
    aux_name        VARCHAR,
    opening_balance NUMERIC,
    closing_balance NUMERIC,
    debit_amount    NUMERIC,
    credit_amount   NUMERIC,
    record_count    INTEGER,
    is_deleted      BOOLEAN DEFAULT false,
    created_at      TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tb_aux_bal_summary_proj_year
    ON tb_aux_balance_summary (project_id, year);
CREATE INDEX IF NOT EXISTS idx_tb_aux_bal_summary_dim
    ON tb_aux_balance_summary (project_id, year, dim_type);

-- ============================================================
-- 2. review_conversation_exports（复核会话导出证据）
-- ============================================================
CREATE TABLE IF NOT EXISTS review_conversation_exports (
    id                    UUID PRIMARY KEY,
    export_id             VARCHAR NOT NULL,
    conversation_id       UUID NOT NULL,
    project_id            UUID NOT NULL,
    requested_by          UUID NOT NULL,
    export_scope          VARCHAR NOT NULL DEFAULT 'full_timeline',
    purpose               TEXT NOT NULL,
    receiver              VARCHAR NOT NULL,
    mask_policy           VARCHAR NOT NULL DEFAULT 'none',
    include_hash_manifest BOOLEAN NOT NULL DEFAULT false,
    file_hash             VARCHAR,
    trace_id              VARCHAR NOT NULL,
    status                VARCHAR NOT NULL DEFAULT 'ready',
    created_at            TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT review_conversation_exports_export_id_key UNIQUE (export_id)
);
CREATE INDEX IF NOT EXISTS idx_rc_exports_conv
    ON review_conversation_exports (conversation_id);
CREATE INDEX IF NOT EXISTS idx_rc_exports_project
    ON review_conversation_exports (project_id, created_at DESC);

-- ============================================================
-- 3. review_conversation_participants（复核会话参与者）
-- ============================================================
CREATE TABLE IF NOT EXISTS review_conversation_participants (
    id               UUID PRIMARY KEY,
    conversation_id  UUID NOT NULL,
    user_id          UUID NOT NULL,
    participant_role VARCHAR NOT NULL DEFAULT 'viewer',
    is_required_ack  BOOLEAN NOT NULL DEFAULT false,
    joined_at        TIMESTAMP NOT NULL DEFAULT now(),
    left_at          TIMESTAMP,
    is_deleted       BOOLEAN NOT NULL DEFAULT false,
    created_at       TIMESTAMP NOT NULL DEFAULT now(),
    updated_at       TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rc_participants_conv
    ON review_conversation_participants (conversation_id, is_deleted);
CREATE INDEX IF NOT EXISTS idx_rc_participants_user
    ON review_conversation_participants (user_id, is_deleted);

-- ============================================================
-- 4. linkage_audit_log（联动传播审计日志；stale_propagation_engine 写）
--    真库现网无此表 —— 幽灵表，列形状按生产 INSERT/SELECT 反推。
-- ============================================================
CREATE TABLE IF NOT EXISTS linkage_audit_log (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_uri     VARCHAR NOT NULL,
    affected_count INTEGER NOT NULL DEFAULT 0,
    duration_ms    INTEGER NOT NULL DEFAULT 0,
    project_id     UUID,
    created_at     TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_linkage_audit_project
    ON linkage_audit_log (project_id, created_at DESC);

-- ============================================================
-- 5. seed_load_history（模板库种子加载审计轨迹；template_library_mgmt 写/读）
--    真库现网无此表 —— 幽灵表，列形状按生产 INSERT/SELECT 反推。
-- ============================================================
CREATE TABLE IF NOT EXISTS seed_load_history (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seed_name    VARCHAR NOT NULL,
    loaded_at    TIMESTAMP NOT NULL DEFAULT now(),
    loaded_by    UUID,
    record_count INTEGER NOT NULL DEFAULT 0,
    inserted     INTEGER NOT NULL DEFAULT 0,
    updated      INTEGER NOT NULL DEFAULT 0,
    errors       INTEGER NOT NULL DEFAULT 0,
    status       VARCHAR NOT NULL DEFAULT 'ok'
);
CREATE INDEX IF NOT EXISTS idx_seed_load_history_name
    ON seed_load_history (seed_name, loaded_at DESC);

-- ============================================================
-- 6. wp_review_records（底稿复核记录；quality_rating_service._review_depth_score 读）
--    真库现网无此表 —— 幽灵表，列形状按生产 SELECT 反推：
--    review_status（'rejected' 值参与聚合）、project_id。
-- ============================================================
CREATE TABLE IF NOT EXISTS wp_review_records (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id    UUID NOT NULL,
    wp_id         UUID,
    reviewer_id   UUID,
    review_status VARCHAR NOT NULL DEFAULT 'pending',
    review_comment TEXT,
    created_at    TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_wp_review_records_project
    ON wp_review_records (project_id);
