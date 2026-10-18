-- V191: 交付件版本 / 在线编辑 / 文字回填完整性 + 底稿质量评分缺列
-- （原 V189，因并发会话已占用 V189/V190 改号至 V191；2026-10-18 从 stash 恢复适配）
-- spec: deliverable-writeback-and-online-edit-integrity（design §5）
--
-- 1. 版本号唯一索引 + OO 底版 / 会话 / 渲染上下文，防并发重复版本与陈旧底版静默覆盖。
-- 2. 章节文字基线与正文区指纹，冲突只看正文、不再拿含 TB 金额的 source_snapshot_hash 误判。
-- 3. working_paper 两列已有 3 个生产读方 + 2 个写方，却从未迁移 / ORM 声明：程序完成 / 裁剪端点因此 500。
--
-- 全部 additive + IF NOT EXISTS，可重入。唯一索引创建前先显式检查重复，给出可诊断错误而不是静默选一条。

ALTER TABLE word_export_task_versions
    ADD COLUMN IF NOT EXISTS base_version_no INTEGER;
ALTER TABLE word_export_task_versions
    ADD COLUMN IF NOT EXISTS oo_doc_key VARCHAR(160);
ALTER TABLE word_export_task_versions
    ADD COLUMN IF NOT EXISTS render_context JSONB;

DO $$
DECLARE
    duplicate_count integer;
BEGIN
    SELECT count(*) INTO duplicate_count
    FROM (
        SELECT word_export_task_id, version_no
        FROM word_export_task_versions
        GROUP BY word_export_task_id, version_no
        HAVING count(*) > 1
    ) d;
    IF duplicate_count > 0 THEN
        RAISE EXCEPTION 'V191 拒绝创建版本号唯一索引：存在 % 组重复 (word_export_task_id, version_no)，请先人工核对', duplicate_count;
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_word_export_versions_task_no
    ON word_export_task_versions (word_export_task_id, version_no);

ALTER TABLE deliverable_section_state
    ADD COLUMN IF NOT EXISTS text_baseline TEXT;
ALTER TABLE deliverable_section_state
    ADD COLUMN IF NOT EXISTS text_source_hash VARCHAR(64);
ALTER TABLE deliverable_section_state
    ADD COLUMN IF NOT EXISTS outside_hash VARCHAR(64);
ALTER TABLE deliverable_section_state
    ADD COLUMN IF NOT EXISTS text_render_context JSONB;

ALTER TABLE working_paper
    ADD COLUMN IF NOT EXISTS quality_score INTEGER;
ALTER TABLE working_paper
    ADD COLUMN IF NOT EXISTS procedure_completion_rate NUMERIC(5, 2);

COMMENT ON COLUMN word_export_task_versions.base_version_no IS 'OnlyOffice 编辑会话打开时的交付件版本号；NULL=非 OO 或历史数据';
COMMENT ON COLUMN word_export_task_versions.oo_doc_key IS 'OnlyOffice document.key；同一会话强制保存与关闭保存共用';
COMMENT ON COLUMN word_export_task_versions.render_context IS '交付件渲染上下文（附注交叉引用显示编号等），OO 版本继承底版';
COMMENT ON COLUMN deliverable_section_state.text_baseline IS '生成/上次裁决时交付件正文区真实文字；冲突三方展示基线';
COMMENT ON COLUMN deliverable_section_state.text_source_hash IS '生成/上次回填时上游正文 SHA-256；冲突只比较正文，不含 TB 金额';
COMMENT ON COLUMN deliverable_section_state.outside_hash IS '正文区以外标题/表格/表题指纹；改动只拒绝结构回填';
COMMENT ON COLUMN deliverable_section_state.text_render_context IS '正文渲染过滤上下文；安全行级补丁重放用';
COMMENT ON COLUMN working_paper.quality_score IS '底稿质量评分 0~100';
COMMENT ON COLUMN working_paper.procedure_completion_rate IS '程序完成率百分比 0~100';
