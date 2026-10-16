-- V188: note_section_instances.section_number 去掉 VARCHAR(20) 上限
-- spec: disclosure-note-template-word-realignment Phase 3（design §4.1 第 6 项）
--
-- 附注裁剪页首次打开时（NoteTrimService._init_from_sections）把按报告口径过滤后的全部种子章节
-- 写进本表。种子里不带数字序号的叙述性章节以标题作编号，现算最长 42 字（国企合并口径第七章
-- 「母公司直接或通过其他子公司间接拥有被投资单位半数以上的表决权但未能对其形成控制的」），
-- VARCHAR(20) 放不下 ⇒ PostgreSQL 报 22001（value too long），整页初始化失败。
-- 超 20 字的编号在本 spec 改种子之前就已存在（国企第九章 26 字），真库本表一直 0 行即此故。
--
-- 与 disclosure_notes.note_section（不限长 VARCHAR）同口径；只放宽、不截断。
-- 本表由 ORM create_all 建（没有建表迁移）⇒ 按列现状判断：表不存在或已放宽时什么都不做（可重入）。

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'note_section_instances'
          AND column_name = 'section_number'
          AND character_maximum_length IS NOT NULL
    ) THEN
        ALTER TABLE note_section_instances
            ALTER COLUMN section_number TYPE VARCHAR;
    END IF;
END
$$;
