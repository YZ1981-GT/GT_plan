-- ═══════════════════════════════════════════════════════════════════════════
-- V165：为 evidence scenario 增加 `authorization_reject` kind
--
-- 解除的欠账（原登记在 `evidence.py:SCHEMA_UNREPRESENTABLE_SCENARIOS`，owner 任务 9）：
--
--   AC 5.6 要求 quarantined incoming **永不**创建 application（application_ids 恒空），
--   而 V151 的 `ck_wpees_standard_requires_entities` 要求非 download_only/recovery_reject
--   的 `passed` 行必须 `operation_ids>=1 AND application_ids>=1`。两者不可同时满足 ⇒
--   `quarantined_rejects_application_and_engine` 的 `passed` 行在库层**物理写不进去**，
--   于是该场景恒 UNVERIFIABLE，其 entry 永不 verified。
--
-- 修法即该欠账注释自己规定的那条：「V151 需要一个 authorization_reject kind」。
--
-- 🔴 **不得**把新 kind 加进 `ck_wpees_download_only_zero_entities`：那条在三实体为零之外
--    还要求 `recovery_case_ids >= 1`（download-only 要终结一个 case），而 quarantined
--    场景 `expects_recovery_case=False`、生产上也不建 case（`CallbackDeliveryService`
--    的 quarantined 分支只建 rejected delivery + quarantined artifact，
--    `operation_id` 保持 NULL）。混进去会把「必须有 case」错加到它头上。
--
-- 因此新 kind 单独一条约束：三实体**恒零**。这比只豁免更严 —— 豁免若不配套零约束，
-- 「声明永不创建 application 的场景」就能带着伪造的 operation/application 记 passed。
--
-- 幂等性：两条被修改的约束用 DROP IF EXISTS + ADD（同名改定义，"缺失才加"无效）；
-- 新约束同样 DROP 后 ADD。健康库重跑为等价重建，不回填、不删表、不改业务数据。
-- ═══════════════════════════════════════════════════════════════════════════

-- 🔴 表名一律**不加 schema 限定**，与 V151 建表语句同风格 —— 让本迁移作用于
--    `search_path` 所指的 schema。写死 `public.` 会让它在 scratch schema 上静默 no-op
--    （本轮实测踩过：守卫测试里约束根本没落，且因 DO 块 RETURN 而毫无报错）。
DO $$
BEGIN
    IF to_regclass('working_paper_entry_evidence_scenario') IS NULL THEN
        RETURN;  -- V151 尚未建表（局部引导库）⇒ 本迁移无事可做
    END IF;

    -- ── 1. kind 取值域 +1：authorization_reject ──────────────────────────
    ALTER TABLE working_paper_entry_evidence_scenario
        DROP CONSTRAINT IF EXISTS ck_wpees_scenario_kind;
    ALTER TABLE working_paper_entry_evidence_scenario
        ADD CONSTRAINT ck_wpees_scenario_kind CHECK (scenario_kind IN (
            'standard', 'download_only', 'recovery_reject', 'recovery_claim',
            'close_capture', 'authorization_reject'));

    -- ── 2. standard entity 要求豁免新 kind（其余逐字同 V151）────────────
    ALTER TABLE working_paper_entry_evidence_scenario
        DROP CONSTRAINT IF EXISTS ck_wpees_standard_requires_entities;
    ALTER TABLE working_paper_entry_evidence_scenario
        ADD CONSTRAINT ck_wpees_standard_requires_entities CHECK (
            scenario_kind IN ('download_only', 'recovery_reject', 'authorization_reject')
            OR result <> 'passed'
            OR (jsonb_array_length(operation_ids) >= 1
                AND jsonb_array_length(application_ids) >= 1));

    -- ── 3. 新 kind 的三实体恒零（AC 5.6 的正面表达，不只是豁免）─────────
    ALTER TABLE working_paper_entry_evidence_scenario
        DROP CONSTRAINT IF EXISTS ck_wpees_authorization_reject_zero_entities;
    ALTER TABLE working_paper_entry_evidence_scenario
        ADD CONSTRAINT ck_wpees_authorization_reject_zero_entities CHECK (
            scenario_kind <> 'authorization_reject'
            OR (jsonb_array_length(operation_ids) = 0
                AND jsonb_array_length(application_ids) = 0
                AND jsonb_array_length(recovery_case_ids) = 0));
END $$;
