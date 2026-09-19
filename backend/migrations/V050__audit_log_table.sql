-- V050: 补建 app_audit_log 轻量操作审计表
-- 背景：password_confirm._write_audit_log / eqcr_judgment / qc_report_export
--   三处路由原按 `INSERT INTO audit_log (...)` 写轻量操作审计，但：
--   ① 应用层从未迁移过 audit_log 表（哈希链审计表是 audit_log_entries，V033 建）；
--   ② 真实 PG 中 audit_log 表名被 **Metabase** 占用（共库污染，schema 完全不同：
--      id integer / topic / model / model_id ...，无 action 列）。
--   因此三处 INSERT 长期 UndefinedColumn 失败 → 污染 PG 事务 + 噪音日志，
--   二次确认（X-Confirmation-Token）链路连带异常。
--   修法：应用层改用独立表名 app_audit_log（避开 Metabase 占用），
--   三处路由 SQL 同步改名。
-- 注意：本表区别于哈希链审计表 audit_log_entries（不可变追加式）；
--   app_audit_log 是轻量操作流水（best-effort，可丢失），二者并存不冲突。

CREATE TABLE IF NOT EXISTS app_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(64),
    resource_id VARCHAR(64),
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_audit_log_user_id ON app_audit_log (user_id);
CREATE INDEX IF NOT EXISTS idx_app_audit_log_action ON app_audit_log (action);
CREATE INDEX IF NOT EXISTS idx_app_audit_log_created_at ON app_audit_log (created_at);
