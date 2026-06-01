-- V048: 补建 system_settings 键值配置表
-- 背景：cost_overview_service / rotation_check_service / quality_rating_service
--   均按 `SELECT value FROM system_settings WHERE key = '...'` 读运行期可调配置
--   （hourly_rates / rotation_limit_listed|unlisted / qc_rating_weights），
--   但该表从未迁移 → UndefinedTable。各 service 虽 try/except 回退默认值，
--   但失败查询会污染 PG 事务致后续查询级联崩（cost-overview 500 即此）。
--   补齐该意图表，使配置可持久化 + 杜绝事务污染。

CREATE TABLE IF NOT EXISTS system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT,
    description VARCHAR(500),
    updated_by UUID,
    updated_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);
