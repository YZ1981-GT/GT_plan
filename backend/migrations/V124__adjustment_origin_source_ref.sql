-- V124: adjustments 表增加 origin / source_ref 列（底稿调整汇聚到集中登记）
-- spec: workpaper-adjustment-centralization
--   origin       — 来源标记：'manual'（手工录入，默认）/ 'workpaper'（底稿汇聚）
--   source_ref   — 底稿溯源键 '{wp_id}:{item_id}'，origin='workpaper' 时非空，幂等键
-- 幂等：information_schema.columns 检测列存在性；additive，旧数据 origin 默认 'manual'。
-- origin 过滤保证试算表 recalc 不重复计算底稿来源调整（已由审定表 writeback 体现）。

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'adjustments' AND column_name = 'origin') THEN
    ALTER TABLE adjustments ADD COLUMN origin VARCHAR(20) NOT NULL DEFAULT 'manual';
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'adjustments' AND column_name = 'source_ref') THEN
    ALTER TABLE adjustments ADD COLUMN source_ref VARCHAR(120);
  END IF;
END $$;

-- 部分唯一索引：同一 source_ref 至多一个活跃分录组（支撑汇聚幂等）。
-- 注意：entry_group 内多行共享同一 source_ref，故不能对 source_ref 单独做行级唯一；
-- 唯一性约束在 (source_ref, entry_group_id) 复合层，允许一组多行、禁止多组同 source_ref。
-- 用 entry_group_id 去重后的唯一：借助表达式无法直接；改由服务层 sync 保证幂等，
-- 索引仅为查询加速（非唯一）。
CREATE INDEX IF NOT EXISTS idx_adjustments_source_ref
  ON adjustments(project_id, source_ref)
  WHERE source_ref IS NOT NULL AND is_deleted = false;
