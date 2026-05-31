# ADR-CONSOL-003: V027 基线迁移纳入 D6

## 状态
已接受 (2026-05-31)

## 背景

合并模块所有表从未进入 D6 迁移系统：
- `grep consol_trial|consol_worksheet|consol_scope|elimination_entries` 在 `backend/migrations/*.sql` = **0 命中**
- 全部 consol 表靠 `init_tables.py` 的 `Base.metadata.create_all()` 首次建表
- `create_all()` 只在表不存在时建表，对已存在表**永不 ALTER**
- 后期加到 ORM 的字段（如 `consol_lock`）在已部署 DB 永不出现

这意味着合并模块在"老库升级"路径无 schema 演进能力（冻结在首次建库那刻）。

## 决策

**新增 V027 基线迁移，把合并模块 ORM 现状固化为幂等 SQL，纳入 D6 治理**：

1. `V027__consol_schema_baseline.sql`：
   - `projects` 表加 `consol_lock` / `consol_lock_by` / `consol_lock_at` 三列（`ADD COLUMN IF NOT EXISTS`）
   - `consol_trial` 加 `consolidation_breakdown JSONB`（B1 provenance）
   - 合并核心表 `CREATE TABLE IF NOT EXISTS` 基线固化（与 ORM 一致）
   - GIN 索引 `idx_consol_trial_breakdown`

2. `R027__consol_schema_baseline_rollback.sql`：配套回滚（DROP COLUMN / DROP INDEX）

3. 全部使用 `IF NOT EXISTS` 幂等：
   - 对已部署老库：仅补缺列（consol_lock / consolidation_breakdown），不重建已有表
   - 对全新库：`create_all` 已建表后此迁移 no-op
   - 两条路径都收敛到"列齐全"

## 后果

- 合并模块从"create_all 时代"遗留正式纳入 D6 迁移体系
- 后续合并字段变更走 V028+ 迁移，不再依赖 `create_all()` 兜底
- `schema_drift_detector` 可守护合并表结构（ORM vs DB 对齐）
- 已部署环境升级时自动补齐缺失列，无需手动 ALTER
- D6 MigrationRunner 启动时自动执行，幂等重跑安全
