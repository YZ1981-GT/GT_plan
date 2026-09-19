-- V078: adjustments 表扩展 passed 错报相关字段（A13 错报自动生成）
ALTER TABLE adjustments ADD COLUMN IF NOT EXISTS passed_reason TEXT;
ALTER TABLE adjustments ADD COLUMN IF NOT EXISTS passed_communication_date TIMESTAMPTZ;
