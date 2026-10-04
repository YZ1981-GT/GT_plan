-- R173：回滚 V173（financial_report.blank_reason）
-- 🔴 回滚会丢失合并报表留空行的原因说明（金额仍为 NULL，页面只能显示空白、无法说明为什么空）。
ALTER TABLE financial_report DROP COLUMN IF EXISTS blank_reason;
