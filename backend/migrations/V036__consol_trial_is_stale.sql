-- V036: consol_trial 加 is_stale 列（P1 — 子公司 TB 变更后母公司 trial 需重算标记）
-- 注：原编号 V029，因与 work 分支底稿模块迁移 V029__attachment_lineage 撞号，重编号为 V036。
-- 子公司 trial_balance 审定数变更时，事件 handler 标记母合并项目 trial is_stale=true，
-- 前端据此提示"子公司数据已更新，建议重新汇总"（不自动重算，用户决定）
ALTER TABLE consol_trial ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT false;

-- 部分索引：仅 stale 行（重算后清零，命中少，索引小）
CREATE INDEX IF NOT EXISTS idx_consol_trial_stale
    ON consol_trial (project_id, year)
    WHERE is_stale = true AND is_deleted = false;
