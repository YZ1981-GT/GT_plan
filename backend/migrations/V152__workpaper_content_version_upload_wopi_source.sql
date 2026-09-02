-- ═══════════════════════════════════════════════════════════════════════════
-- V152：`working_paper_content_version.source` 补上 `upload` 与 `wopi`
--
-- spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 19
-- Requirements: 2.2（HTML save、**导入上传**、**WOPI**、OnlyOffice、冲突裁决与 rollback
--               统一经 ContentMutationService 提交）、2.3（content version 记录 `source`）
--
-- V151 把 `ck_wpcv_source` 的封闭词表定为 5 个值
-- （html / onlyoffice / conflict_resolution / rollback / custom）。Task 19 要把
-- **上传**与 **WOPI PutFile** 两条 writer 迁进同一个 revision 域，它们都不是这 5 个中
-- 的任何一个：
--
--   * 上传 = 用户在桌面 Excel 离线改完再传回来，权威 OOXML 本体被整体替换；
--   * WOPI PutFile = Office online 协议的保存回调，与平台自建 OnlyOffice room 是
--     两套完全不同的生命周期（无 room / 无 generation / 无 forcesave request）。
--
-- 把它们塞进 `onlyoffice` 会让审计轨迹说谎：`source` 是 evidence 与 timeline 的分桶
-- 依据，事后无法再区分「谁改的、走的哪条协议」。所以这里扩词表，而不是复用近似值。
--
-- 幂等：先 DROP CONSTRAINT IF EXISTS 再 ADD。CHECK 的**放宽**方向不会让既有行失效，
-- 因此不需要数据回填。
-- ═══════════════════════════════════════════════════════════════════════════

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'working_paper_content_version'
    ) THEN
        ALTER TABLE working_paper_content_version
            DROP CONSTRAINT IF EXISTS ck_wpcv_source;
        ALTER TABLE working_paper_content_version
            ADD CONSTRAINT ck_wpcv_source CHECK (
                source IN (
                    'html',
                    'onlyoffice',
                    'conflict_resolution',
                    'rollback',
                    'custom',
                    'upload',
                    'wopi'
                )
            );
    END IF;
END $$;
