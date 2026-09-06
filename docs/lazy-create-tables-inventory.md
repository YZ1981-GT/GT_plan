# 懒建表清单（CREATE TABLE IF NOT EXISTS 全仓扫描）

> **判据来源**：`backend/tests/test_cleanup_h4_lazy_table_scan.py`（Property H4 / Requirements C5）。
> 本文档与该测试里的分类常量**双向锁死** —— 改一处必须改另一处，否则测试打红。
>
> **最近实测**：2026-09-06 扫描 `backend/app` + `backend/scripts` 共 **2735** 个 py 文件，
> 发现 **6** 张懒建表（排除 `migrations/` `tests/` `.hypothesis/` 等目录）。

## 为什么要有这份清单

平台的 schema 真源是 `backend/migrations/V*.sql`（由 `MigrationRunner` 在启动时跑）。
业务代码里写 `CREATE TABLE IF NOT EXISTS` 会绕过这条唯一通道，后果有三：

- **schema 漂移检测失效**：`SchemaDriftDetector` 比对 ORM ↔ DB，懒建表两侧都不在，漂移无感；
- **多环境不一致**：表结构取决于「哪个端点先被调用过」，而不是迁移版本号；
- **回滚无路**：迁移有配对的 `R*.sql`，懒建没有。

所以懒建表默认视为债务，只有下面明确分类的才算合法存在。

## 分类总览

| 分类 | 张数 | 是否债务 | 说明 |
|---|---|---|---|
| 业务路由懒建（`KNOWN_LAZY_TABLES`） | 0 | 是 | 当前已全部收口/迁移，为空 |
| 基础设施（`INFRA_TABLES`） | 3 | 否 | 迁移系统自身依赖，无法用迁移创建 |
| 一次性运维脚本（`ONE_OFF_SCRIPT_TABLES`） | 3 | 否 | 仅人工执行脚本时建，生产路径永不触达 |
| 已迁移入 D6（`MIGRATED_TO_D6_TABLES`） | 4 | 已清 | V040/V041 收口 |
| 已彻底消除（`ELIMINATED_LAZY_TABLES`） | 1 | 已清 | 收口哈希链后删除懒建 |

## 一、业务路由懒建表（`KNOWN_LAZY_TABLES`）

**当前为空** —— 历史上的业务懒建表已全部收口，见下面第四、五节。

新增业务表**不得**走懒建：写迁移 `V*.sql` + 配对 `R*.sql`，并在 ORM 里声明模型
（若有意不映射 ORM，须在 `SchemaDriftDetector.KNOWN_ALLOWLIST` 登记并写明设计裁决理由）。

## 二、基础设施表（`INFRA_TABLES`，合法）

这三张是**迁移系统自身**的依赖，存在鸡生蛋问题：它们必须在任何迁移执行**之前**就位，
因此只能懒建。

| 表 | 建表位置 | 用途 |
|---|---|---|
| `schema_version` | `backend/app/core/migration_runner.py` | 已应用迁移的版本台账 |
| `schema_migration_failures` | `backend/app/core/migration_runner.py` | 迁移失败记录（供 `/api/health` 暴露） |
| `schema_drift_log` | `backend/app/core/schema_drift_detector.py` | 每次启动覆写的漂移快照 |

## 三、一次性运维脚本表（`ONE_OFF_SCRIPT_TABLES`，合法）

判据（**三条全满足**才归此类，否则应收口进迁移）：

1. 建表语句在 `backend/scripts/` 下，`backend/app/` 内**零引用**；
2. 脚本是一次性/自愈用途（清理、诊断、补齐），不是业务功能；
3. 该表已在 `SchemaDriftDetector.KNOWN_ALLOWLIST` 登记，或其列集与 ORM 单一真源对齐
   （不构成第二套 schema 真源）。

| 表 | 建表脚本 | 性质 |
|---|---|---|
| `_note_ai_text_backup` | `backend/scripts/fix/_fix_clear_stale_ai_text_content.py` | 清理「已底稿同步章节的残留 AI 草稿 `text_content`」前的回滚备份 |
| `_note_text_markdown_backup` | `backend/scripts/diagnose_note_text_markdown.py` | 清理 `text_content` 里 markdown 残留（`###`/`**`）前的回滚备份 |
| `custom_query_templates` | `backend/scripts/_ensure_custom_query_tables.py` | 旧库/新环境缺表时的**幂等自愈**，非新建语义 |

两张 `_note_*_backup` 的清理动作已完成，但脚本的 `--rollback` 分支依赖它们，故**保留不删**；
两者均已在 `SchemaDriftDetector.KNOWN_ALLOWLIST` 登记（否则启动会报 `db_extra` 漂移噪音）。

`custom_query_templates` 属特殊情形：它**本来就有迁移**（V033 建表 + V051 补 4 列 +
V101 加 `shared_project_ids`），脚本只是为「模板功能报表不存在」这类单点故障提供快速自愈。
脚本头部显式写了 R10.5 单一真源约束，要求其列集/索引集与 ORM
`CustomQueryTemplate` 及上述三个迁移保持一致 —— 改任一处必须同步。

## 四、已迁移入 D6（`MIGRATED_TO_D6_TABLES`，债务已清）

| 表 | 原懒建位置 | 收口迁移 |
|---|---|---|
| `account_note_mapping` | `backend/app/routers/account_note_mapping.py` | V040 |
| `consol_cell_comments` | `backend/app/routers/consol_cell_comments.py` | V040 |
| `consol_worksheet_data` | `backend/app/routers/consol_worksheet_data.py` | V041 |
| `consol_note_data` | `backend/app/routers/consol_note_sections.py` | V041 |

其中 `account_note_mapping` + `consol_cell_comments` 是本 spec（cleanup / Task 8）处理的表；
`consol_worksheet_data` + `consol_note_data` 由实施后复盘补充迁移。

测试 `test_migrated_tables_no_longer_lazy_created` 断言这四张**不再**出现在扫描结果里。

## 五、已彻底消除懒建（`ELIMINATED_LAZY_TABLES`，债务已清）

| 表 | 原懒建位置 | 处置 |
|---|---|---|
| `formula_audit_log` | `backend/app/routers/formula_audit_log.py` | 由 **formula-engine-unification** spec 收口哈希链（2026-06-01 复盘），rollback 端点最后一处 `ensure_table` 已删 |

测试 `test_eliminated_tables_no_longer_lazy_created` 与 `test_formula_audit_log_delegated`
共同锁死这条：既要求扫描结果里没有它，也要求本文档提到 `formula-engine`。

## 维护约定

- **新增懒建表 = 先问能不能写迁移**。能就写迁移，不要往清单里加。
- 确需归入第三类，必须逐条对照那三个判据，并在本文档表格里写明性质与脚本路径。
- 分类常量与本文档是**双向锁死**关系：
  `test_no_unknown_lazy_tables` 保证「扫描到的都已登记」，
  `test_inventory_contains_all_known_tables` / `test_this_spec_tables_identified` /
  `test_formula_audit_log_delegated` 保证「登记的都写进了本文档」。
  只改一侧必然打红 —— 这是有意的。
