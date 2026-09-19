-- V060: 临时授权表
-- 支持项目经理/合伙人为特定用户授予有限时间内的操作权限
-- ADR: docs/adr/ADR-030-temporary-grant-dedicated-table.md

CREATE TABLE IF NOT EXISTS temporary_grants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    operation_code VARCHAR(64) NOT NULL,
    grantee UUID NOT NULL,
    approver UUID NOT NULL,
    reason TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 查询活跃授权：按 grantee + project + operation 高频查询
CREATE INDEX IF NOT EXISTS idx_temporary_grants_active_lookup
    ON temporary_grants (grantee, project_id, operation_code)
    WHERE is_active = TRUE;

-- 过期清理
CREATE INDEX IF NOT EXISTS idx_temporary_grants_expires_at
    ON temporary_grants (expires_at)
    WHERE is_active = TRUE;

-- 审计追溯
CREATE INDEX IF NOT EXISTS idx_temporary_grants_project_id
    ON temporary_grants (project_id);

CREATE INDEX IF NOT EXISTS idx_temporary_grants_approver
    ON temporary_grants (approver);
