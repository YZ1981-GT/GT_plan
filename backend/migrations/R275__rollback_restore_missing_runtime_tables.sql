-- R275: 回滚 V275（补齐 6 张运行时表）
--
-- 回滚保护（与 display-settings 系列 R 脚本同纪律）：
-- DROP 前对任何非空数据行 RAISE EXCEPTION 并整单回滚。
-- 历史表（tb_aux_balance_summary / review_conversation_*）可能含真实业务数据，
-- 逐表独立保护块；幽灵表（linkage_audit_log / seed_load_history / wp_review_records）
-- 若有数据说明修复后已有真实写入，同样保护。

DO $$
BEGIN
    -- tb_aux_balance_summary
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='tb_aux_balance_summary') THEN
        IF EXISTS (SELECT 1 FROM tb_aux_balance_summary) THEN
            RAISE EXCEPTION 'R275 回滚保护：tb_aux_balance_summary 含 % 行数据，拒绝 DROP（先人工确认后清理）',
                (SELECT COUNT(*) FROM tb_aux_balance_summary);
        END IF;
        DROP TABLE tb_aux_balance_summary;
    END IF;

    -- review_conversation_exports
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='review_conversation_exports') THEN
        IF EXISTS (SELECT 1 FROM review_conversation_exports) THEN
            RAISE EXCEPTION 'R275 回滚保护：review_conversation_exports 含 % 行数据，拒绝 DROP',
                (SELECT COUNT(*) FROM review_conversation_exports);
        END IF;
        DROP TABLE review_conversation_exports;
    END IF;

    -- review_conversation_participants
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='review_conversation_participants') THEN
        IF EXISTS (SELECT 1 FROM review_conversation_participants) THEN
            RAISE EXCEPTION 'R275 回滚保护：review_conversation_participants 含 % 行数据，拒绝 DROP',
                (SELECT COUNT(*) FROM review_conversation_participants);
        END IF;
        DROP TABLE review_conversation_participants;
    END IF;

    -- linkage_audit_log
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='linkage_audit_log') THEN
        IF EXISTS (SELECT 1 FROM linkage_audit_log) THEN
            RAISE EXCEPTION 'R275 回滚保护：linkage_audit_log 含 % 行数据，拒绝 DROP',
                (SELECT COUNT(*) FROM linkage_audit_log);
        END IF;
        DROP TABLE linkage_audit_log;
    END IF;

    -- seed_load_history
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='seed_load_history') THEN
        IF EXISTS (SELECT 1 FROM seed_load_history) THEN
            RAISE EXCEPTION 'R275 回滚保护：seed_load_history 含 % 行数据，拒绝 DROP',
                (SELECT COUNT(*) FROM seed_load_history);
        END IF;
        DROP TABLE seed_load_history;
    END IF;

    -- wp_review_records
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='wp_review_records') THEN
        IF EXISTS (SELECT 1 FROM wp_review_records) THEN
            RAISE EXCEPTION 'R275 回滚保护：wp_review_records 含 % 行数据，拒绝 DROP',
                (SELECT COUNT(*) FROM wp_review_records);
        END IF;
        DROP TABLE wp_review_records;
    END IF;
END $$;
