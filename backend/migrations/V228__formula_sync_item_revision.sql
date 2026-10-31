-- V228: formula_sync_item 增加修订号 revision
-- spec formula-hub-integrity-closure（需求 8.1，ADR-FHIC-11，D10）
--
-- 待确认事项被新的发布 / 模板新版本 / 其他项目推送原地覆盖时修订号 +1（服务层单条
-- INSERT … ON CONFLICT DO UPDATE … RETURNING 原子递增）；处理待确认以修订号为唯一 CAS 依据：
-- 缺修订号 428，与当前不等 409。原先只比上游版本，来自其他项目的推送上游版本恒为空，覆盖后照样放行。
--
-- NOT NULL DEFAULT 1：存量行与迁移后仍在运行的旧代码写入的行都取 1（X1 先迁移、后推送；旧代码不读该列）。
-- PostgreSQL 11 起常量默认值的加列不重写表。
-- 回滚：R228。

ALTER TABLE formula_sync_item ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1;
