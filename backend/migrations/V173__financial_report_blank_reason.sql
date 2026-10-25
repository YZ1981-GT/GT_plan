-- V173: financial_report.blank_reason —— 报表行留空原因（spec consol-elimination-single-source-push 需求 3.5）
--
-- 合并报表按计算口径逐行求值：公式引用口径外的列（如「年初余额」、权益类「本期发生额」）、引用了留空行、
-- 公式无法解析等情形，该行金额留空（current_period_amount = NULL）并在本列写明原因，不静默写 0。
-- 有值的行本列为 NULL。单体报表生成不写本列（保持 NULL）。
--
-- 存量安全：新增可空列，不改既有数据。幂等：ADD COLUMN IF NOT EXISTS。可回滚：见 R173。

ALTER TABLE financial_report ADD COLUMN IF NOT EXISTS blank_reason TEXT;

COMMENT ON COLUMN financial_report.blank_reason IS
  '报表行留空原因：公式取数超出口径（如年初余额）或引用了留空行时金额为 NULL 并写明原因；有值的行为 NULL';
