-- V126: 审计检查复核门禁签认（audit-check-review-gate-hardening / Task 5.1）
-- 项目概览「审计检查」作为完成复核最后一次检查的签认留痕。
--   audit_check_signoff — 每次签认的汇总快照 + 是否存在未处理阻断项
-- summary_snapshot 记签认当时的项目汇总（P10）；blocking_present 记签认时
-- 是否有未处理阻断项（只提示不阻断，Req8.3/P14）。
-- 幂等：CREATE TABLE / INDEX IF NOT EXISTS。additive，不改动既有表。

CREATE TABLE IF NOT EXISTS audit_check_signoff (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID NOT NULL,
    year         INT  NOT NULL,
    signed_by    UUID NOT NULL,
    signed_by_name VARCHAR(100),
    signed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    summary_snapshot JSONB NOT NULL,   -- {decided,passed,failed,uncovered,pass_rate,blocking_count}
    blocking_present BOOLEAN NOT NULL DEFAULT false,
    note         TEXT,
    is_deleted   BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_audit_check_signoff_proj_year
    ON audit_check_signoff(project_id, year) WHERE is_deleted = false;
