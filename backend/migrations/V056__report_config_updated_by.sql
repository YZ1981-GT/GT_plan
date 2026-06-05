-- V056: report_config 加 updated_by 字段（公式变更审计追踪）
ALTER TABLE report_config ADD COLUMN IF NOT EXISTS updated_by UUID;
