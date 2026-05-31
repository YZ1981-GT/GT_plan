-- R034: 回滚 V034 - 删除 consol_lock 三列 + consolidation_breakdown 列 + GIN 索引
-- 注：原编号 R027，随 V027→V034 重编号同步改为 R034。
--
-- 回滚范围（仅回滚 V034 新增的列与索引）：
--   1. DROP INDEX idx_consol_trial_breakdown
--   2. consol_trial DROP COLUMN consolidation_breakdown
--   3. projects DROP COLUMN consol_lock / consol_lock_by / consol_lock_at
--
-- 不回滚项（刻意保留，避免误删数据表）：
--   - V034 的 CREATE TABLE IF NOT EXISTS（consol_scope / consol_trial / consol_worksheet /
--     elimination_entries）是对 ORM 现状的基线固化，这些表在本迁移之前已由 create_all
--     建好并承载真实业务数据。回滚 V034 仅意味着撤销"新增列 + 基线纳管"，绝不 DROP 这些表
--     （否则会丢失合并业务数据）。表本身的生命周期由 create_all / ORM 维护。
--   - CREATE TYPE 的 6 个 PG enum 类型同理不回滚（可能被现存表列引用，DROP 会失败或破坏 schema）。
--
-- 全部 DROP 均 IF EXISTS 幂等，重复回滚不报错。

-- 1) GIN 索引
DROP INDEX IF EXISTS idx_consol_trial_breakdown;

-- 2) consol_trial provenance 列
ALTER TABLE consol_trial DROP COLUMN IF EXISTS consolidation_breakdown;

-- 3) projects consol_lock 三列
ALTER TABLE projects DROP COLUMN IF EXISTS consol_lock_at;
ALTER TABLE projects DROP COLUMN IF EXISTS consol_lock_by;
ALTER TABLE projects DROP COLUMN IF EXISTS consol_lock;
