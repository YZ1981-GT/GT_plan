-- V090: 用户自定义科目工作包表（spec workpaper-account-multifile-aggregation 需求 6）
-- 支持"导出模板→编辑→导入"形成项目级/事务所级自定义科目工作包；
-- resolve_package_sheets 按优先级（项目>事务所>内置行业>通用）解析。

CREATE TABLE IF NOT EXISTS custom_account_packages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope           VARCHAR(16) NOT NULL,          -- 'project' | 'firm'
    scope_id        UUID NOT NULL,                 -- project_id 或 firm_id
    wp_code         VARCHAR(32) NOT NULL,          -- 父码（如 D2）
    industry        VARCHAR(32),                   -- 行业标签（制造业/商贸/通用…）
    package_json    JSONB NOT NULL,                -- 完整工作包结构（sheets/sheet_type/字段定义）
    created_by      UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted      BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT uq_custom_account_pkg UNIQUE (scope, scope_id, wp_code)
);

CREATE INDEX IF NOT EXISTS idx_custom_account_pkg_lookup
    ON custom_account_packages (scope, scope_id, wp_code)
    WHERE is_deleted = false;

COMMENT ON TABLE custom_account_packages IS '用户自定义科目工作包（项目级/事务所级），优先于内置 account_package_registry';
COMMENT ON COLUMN custom_account_packages.scope IS '作用域: project(项目级) | firm(事务所级)';
COMMENT ON COLUMN custom_account_packages.package_json IS '工作包结构 JSON: {account_name, industry, sheets:[{sheet_name, sheet_type, source_wp_code}]}';
