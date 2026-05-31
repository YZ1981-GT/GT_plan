# 全仓懒建表扫描清单（CREATE TABLE IF NOT EXISTS）

> 扫描日期：2026-06-01
> 排除目录：`migrations/`、`tests/`、`.hypothesis/`、`node_modules/`
> 关联 Bug 条件：C5（懒建表绕 D6，drift detector 盲区）
> 关联属性：H4（懒建表入 D6）

## 一、业务路由懒建表（需治理）

以下文件在运行时通过 `ensure_table()` 函数执行 `CREATE TABLE IF NOT EXISTS`，绕开 D6 MigrationRunner：

| # | 表名 | 文件路径 | 处理归属 |
|---|------|----------|----------|
| 1 | `formula_audit_log` | `backend/app/routers/formula_audit_log.py` | **formula-engine-unification spec** |
| 2 | `account_note_mapping` | `backend/app/routers/account_note_mapping.py` | **本 spec（global-modules-cleanup Task 8）** |
| 3 | `consol_cell_comments` | `backend/app/routers/consol_cell_comments.py` | **本 spec（global-modules-cleanup Task 8）** |
| 4 | `consol_worksheet_data` | `backend/app/routers/consol_worksheet_data.py` | **本 spec（V041 迁移，ensure_table 已删）** |
| 5 | `consol_note_data` | `backend/app/routers/consol_note_sections.py` | **本 spec（V041 迁移，ensure_table 已删）** |

## 二、基础设施表（合理使用，无需治理）

以下是 D6 MigrationRunner 自身的基础设施表，属于 bootstrap 阶段必须的自举建表，不算"绕开 D6"：

| # | 表名 | 文件路径 | 说明 |
|---|------|----------|------|
| 6 | `schema_version` | `backend/app/core/migration_runner.py` | MigrationRunner 自身版本追踪表（自举） |
| 7 | `schema_migration_failures` | `backend/app/core/migration_runner.py` | 迁移失败记录表（自举） |
| 8 | `schema_drift_log` | `backend/app/core/schema_drift_detector.py` | drift detector 日志表（V026 兜底安全网） |

## 三、工具/生成器（合理使用，无需治理）

| # | 文件路径 | 说明 |
|---|----------|------|
| 9 | `backend/scripts/gen/gen_schema_sync_migration.py` | 迁移 SQL 生成器（输出 D6 迁移文件，非运行时懒建） |

## 四、文档中的 DDL 示例（仅文档，无需治理）

- `docs/proposals/workpaper-development-v2.md` — 合并报表设计文档中的 SQL 示例
- `docs/proposals/global-modules-status-and-improvement-2026-05-31.md` — 盘点文档引用
- `docs/adr/ADR-CONSOL-003-v027-baseline-migration.md` — ADR 文档

## 五、处理计划

### 本 spec 处理（Task 8 + 复盘补充）
- `account_note_mapping` → V040 迁移 ✅
- `consol_cell_comments` → V040 迁移 ✅
- `consol_worksheet_data` → V041 迁移 ✅
- `consol_note_data` → V041 迁移 ✅

### formula-engine-unification spec 处理
- `formula_audit_log` → 该 spec 审计收口时统一迁移

### 待评估（合并模块后续）
- ~~`consol_worksheet_data`~~ — 已入 V041 迁移
- ~~`consol_note_data`~~ — 已入 V041 迁移

> 注：合并模块的 `consol_worksheet_data` 和 `consol_note_data` 两表已有 ORM 模型但懒建未入 D6，
> 建议在合并模块下一轮维护时统一纳入迁移。本 spec 不处理以避免跨 spec 冲突。

## 六、结论

全仓共发现 **5 处业务路由懒建表**（绕 D6）：
- 1 处归 formula-engine-unification spec
- 4 处归本 spec（V040 + V041 迁移，ensure_table 全部删除）✅

基础设施表（schema_version / schema_migration_failures / schema_drift_log）属于 D6 自举，合理使用。
