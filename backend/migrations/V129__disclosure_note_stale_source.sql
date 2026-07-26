-- V129: disclosure_notes 增加 stale 来源标注（附注模块联动复盘 P0-3）
--
-- 背景：mark_notes_stale_for_report_change 历史实现是"报表任一变更 → 全项目附注
-- 一刀切 is_stale=true"（实测某项目 181/181 全亮），标记退化成背景噪声。
-- 粒度化后需要记录"因何变更而 stale"，供前端提示与诊断区分（report / workpaper /
-- trial_balance / report_fallback[无 linkage 时的保守全量标记]）。
--
-- additive 可空列，幂等；不改既有语义（stale_source 为 NULL 时前端按历史文案展示）。

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'disclosure_notes' AND column_name = 'stale_source'
    ) THEN
        ALTER TABLE disclosure_notes ADD COLUMN stale_source VARCHAR(32);
        COMMENT ON COLUMN disclosure_notes.stale_source IS
            'stale 来源：report / report_fallback / workpaper / trial_balance；NULL=未标注';
    END IF;
END $$;
