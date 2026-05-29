-- V026: schema 漂移日志表（migration-runner-resilience spec / Sprint 2）
--
-- 设计要点：
-- 1. 启动时 SchemaDriftDetector 扫描 ORM ↔ DB 差异，写入此表
-- 2. 每次启动覆盖（DELETE + INSERT），仅保留当前漂移快照
-- 3. /api/health 端点暴露 count + items，drift>0 → status=degraded
-- 4. 4 类 drift_type：orm_extra（ORM 多列） / db_extra（DB 多列）
--                   / type_mismatch（类型不一致） / enum_mismatch（PG enum vs Python Enum）

CREATE TABLE IF NOT EXISTS schema_drift_log (
    id              SERIAL       PRIMARY KEY,
    table_name      VARCHAR(100) NOT NULL,
    column_name     VARCHAR(100),
    drift_type      VARCHAR(50)  NOT NULL,
    detail          TEXT,
    detected_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_schema_drift_type
    ON schema_drift_log (drift_type);

CREATE INDEX IF NOT EXISTS idx_schema_drift_detected_at
    ON schema_drift_log (detected_at DESC);
