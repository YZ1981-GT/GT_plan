-- V053: 补充 projecttype 枚举缺失的值（验资/税审）
-- 前端向导已有选项但 PG 枚举未定义，选择后创建项目 500
ALTER TYPE projecttype ADD VALUE IF NOT EXISTS 'capital_verification';
ALTER TYPE projecttype ADD VALUE IF NOT EXISTS 'tax_audit';
