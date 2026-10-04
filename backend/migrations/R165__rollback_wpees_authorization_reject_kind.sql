-- ═══════════════════════════════════════════════════════════════════════════
-- R165：回滚 V165（撤销 `authorization_reject` kind）
--
-- 🔴 回滚前必须先清掉该 kind 的行，否则恢复 V151 的 `ck_wpees_scenario_kind` 会因存量
--    数据违约而失败。这里**不**静默删业务行：若存在该 kind 的 evidence 行就抛错，由人
--    决定是删还是改 —— evidence 是审计轨迹，静默删除比回滚失败危险得多。
-- ═══════════════════════════════════════════════════════════════════════════

-- 🔴 表名不加 schema 限定，跟随 `search_path`（同 V165 的理由）。
DO $$
DECLARE
    offending bigint;
BEGIN
    IF to_regclass('working_paper_entry_evidence_scenario') IS NULL THEN
        RETURN;
    END IF;

    SELECT count(*) INTO offending
    FROM working_paper_entry_evidence_scenario
    WHERE scenario_kind = 'authorization_reject';

    IF offending > 0 THEN
        RAISE EXCEPTION
            'R165 拒绝回滚：仍有 % 行 scenario_kind=authorization_reject。'
            'evidence 是审计轨迹，本回滚不静默删除；请先人工裁决这些行的去向。',
            offending;
    END IF;

    ALTER TABLE working_paper_entry_evidence_scenario
        DROP CONSTRAINT IF EXISTS ck_wpees_authorization_reject_zero_entities;

    -- 恢复 V151 原文
    ALTER TABLE working_paper_entry_evidence_scenario
        DROP CONSTRAINT IF EXISTS ck_wpees_standard_requires_entities;
    ALTER TABLE working_paper_entry_evidence_scenario
        ADD CONSTRAINT ck_wpees_standard_requires_entities CHECK (
            scenario_kind IN ('download_only', 'recovery_reject')
            OR result <> 'passed'
            OR (jsonb_array_length(operation_ids) >= 1
                AND jsonb_array_length(application_ids) >= 1));

    ALTER TABLE working_paper_entry_evidence_scenario
        DROP CONSTRAINT IF EXISTS ck_wpees_scenario_kind;
    ALTER TABLE working_paper_entry_evidence_scenario
        ADD CONSTRAINT ck_wpees_scenario_kind CHECK (scenario_kind IN (
            'standard', 'download_only', 'recovery_reject', 'recovery_claim',
            'close_capture'));
END $$;
