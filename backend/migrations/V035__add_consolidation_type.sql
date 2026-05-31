-- V035: projects 表加 consolidation_type 列（母子合并 vs 母分汇总）
-- 注：原编号 V028，因与 work 分支底稿模块迁移撞号，重编号为 V035。
-- subsidiary = 母子合并（需抵销，默认）
-- branch = 母分汇总（直接加总，无抵销/商誉/少数股东）
ALTER TABLE projects ADD COLUMN IF NOT EXISTS consolidation_type VARCHAR(20);

-- 注：默认 NULL 视为 subsidiary（向后兼容已有合并项目）
