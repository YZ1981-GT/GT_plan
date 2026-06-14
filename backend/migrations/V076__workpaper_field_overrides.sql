-- V076: 统一字段覆盖存储表（底稿基础设施套件）
-- 多个底稿模块共享的"系统自动值+用户可覆盖"模式
CREATE TABLE IF NOT EXISTS workpaper_field_overrides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    year INT NOT NULL,
    scope VARCHAR(50) NOT NULL,
    item_key VARCHAR(100) NOT NULL,
    field VARCHAR(50) NOT NULL,
    value JSONB,
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, year, scope, item_key, field)
);

CREATE INDEX IF NOT EXISTS ix_field_overrides_scope
    ON workpaper_field_overrides(project_id, year, scope);
