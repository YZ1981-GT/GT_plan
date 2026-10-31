-- V229: financial_report 增加计算版本 calc_version 与计算失败原因 calc_error
-- spec formula-hub-integrity-closure（需求 5.1 读取部分、5.5，ADR-FHIC-04，D13-A）
--
-- calc_version：生成该行时的报表计算版本（services/report_freshness.CALC_VERSION）。
-- calc_error：计算失败原因（保留旧值时写）；既有 blank_reason（V173）是口径性留空原因，二者不同时写。
-- 读取侧「是否过期」= is_stale OR calc_version IS DISTINCT FROM 当前版本（report_freshness.stale_clause）。
--
-- 两列可空、不回填：存量行 calc_version 为 NULL ⇒ 读取侧一律判过期，由用户逐项目重新生成（D13-A，X3）。
-- 旧代码不读写这两列 ⇒ 先迁移、后换代码不影响旧代码（X1）。PostgreSQL 加可空列不重写表。
-- 回滚：R229。

ALTER TABLE financial_report ADD COLUMN IF NOT EXISTS calc_version INTEGER;
ALTER TABLE financial_report ADD COLUMN IF NOT EXISTS calc_error VARCHAR(500);
