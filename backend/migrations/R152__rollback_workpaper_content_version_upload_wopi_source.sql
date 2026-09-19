-- ═══════════════════════════════════════════════════════════════════════════
-- R152：回滚 V152 —— 把 `ck_wpcv_source` 收回 V151 的 5 值词表
--
-- spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 19
--
-- ⚠️ 这是**收紧**方向：若已存在 `source IN ('upload','wopi')` 的 content version 行，
-- ADD CONSTRAINT 会失败。这是刻意的 —— 静默删掉那些行会丢掉真实的业务内容版本。
-- 回滚前必须先决定那些行怎么处理（重写 source 或先归档），不能由本脚本代替裁决。
-- ═══════════════════════════════════════════════════════════════════════════

DO $$
DECLARE
    stale_count BIGINT;
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'working_paper_content_version'
    ) THEN
        SELECT count(*) INTO stale_count
        FROM working_paper_content_version
        WHERE source IN ('upload', 'wopi');

        IF stale_count > 0 THEN
            RAISE EXCEPTION
                'R152 拒绝回滚：working_paper_content_version 仍有 % 行 source IN (upload, wopi)。'
                '先裁决这些业务内容版本的归属，再重跑本脚本。', stale_count;
        END IF;

        ALTER TABLE working_paper_content_version
            DROP CONSTRAINT IF EXISTS ck_wpcv_source;
        ALTER TABLE working_paper_content_version
            ADD CONSTRAINT ck_wpcv_source CHECK (
                source IN ('html', 'onlyoffice', 'conflict_resolution', 'rollback', 'custom')
            );
    END IF;
END $$;
