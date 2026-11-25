# 数据表关联关系分析

> 整理日期：2026-11-18。来源：源码（`backend/app/models`、`backend/app/services`、`backend/app/core/database.py`）+ 本地开发库 `audit_platform` 只读查询（`pg_constraint` / `pg_policies` / `pg_roles`）。
> 配套：表清单 `database-tables.md`，字段明细 `database-tables-columns.md`，全部外键与无外键引用列 `database-relationships-fk.md`。
> 【未核实】= 本次没在代码或库里确认。

## 0. 数据库类型

本项目只用 **PostgreSQL 16**，没有 MySQL。
- 后端连接串 `postgresql+asyncpg://…`（`backend/app/core/config.py:21`，compose 文件同样）。
- 全仓库搜 `mysql / pymysql / aiomysql / mariadb`，只在 `backend/app/core/startup_registry.py:42` 的日志脱敏正则里出现，没有驱动和连接配置。
- 同一个库里还有 Metabase 和 Quartz 建的 151 张表（compose 里 Metabase 的 `MB_DB_DBNAME` 指向同一库），与平台表没有关联；Paperless 用单独的库。

下面所有「连接逻辑」都是 PostgreSQL 下的实现。

## 1. 数据库连接逻辑

**引擎与连接池**（`backend/app/core/database.py:22-61`）

| 模式 | 触发条件 | 连接池 | 关键参数 |
|------|----------|--------|----------|
| PgBouncer | `DB_USE_PGBOUNCER=true` | NullPool（每次取新连接，由 PgBouncer 复用） | 地址换成 `DB_PGBOUNCER_HOST/PORT`；`statement_cache_size=0`、`prepared_statement_cache_size=0`（事务池模式下不能用预编译语句缓存） |
| PG 直连（默认） | URL 以 `postgresql` 开头 | `InstrumentedAsyncAdaptedQueuePool` | `pool_size=max(DB_POOL_SIZE,20)`、`max_overflow=max(DB_MAX_OVERFLOW,80)`、`pool_timeout=30`、`pool_recycle=1800`、`pool_pre_ping` |
| 其他（测试用 SQLite） | 其他 URL | 默认池 | `pool_recycle=3600` |

- `DB_POOL_SIZE` 默认 50、`DB_MAX_OVERFLOW` 默认 100（`config.py:22-23`），所以直连默认最多 150 个连接。
- `DB_DISABLE_SSL=true` 时给 asyncpg 传 `ssl=False`。
- docker-compose 里的 PgBouncer 为 `POOL_MODE=transaction`、`DEFAULT_POOL_SIZE=50`、`MAX_CLIENT_CONN=10000`。

**会话**
- `async_session`：`expire_on_commit=False`（`database.py:83-87`）。
- `get_db()`：每个请求一个会话，结束时关闭；**不自动提交**，由路由或服务显式 `commit`（`database.py:137-140`）。约定是服务层只 `flush`，路由统一 `commit`。
- 同步会话 `get_sync_db()`：成功时 `commit`、异常时 `rollback`，同步引擎延迟取自 `engine.sync_engine`。

**行级安全（RLS）上下文**
- `set_rls_context()` 执行 `SELECT set_config('app.current_project_id', :pid, true)`，只在当前事务内有效（`database.py:143-171`）。SQLite 下跳过。
- 调用点：`deps.require_project_access`（`deps.py:312, 337`），以及若干跨项目读取后「设回本项目」的地方（如 `account_chart.py:419`、`report_line_mapping.py:338`）。
- 启用 RLS 的表只有 7 张：`working_paper`、`adjustments`、`tb_balance`、`review_records`（V005），以及 `adjustment_client_bookings`、`adjustment_review_tasks`、`adjustment_treatment_events`。策略都是 `project_id::text = current_setting('app.current_project_id', true)`；`review_records` 改用子查询 `working_paper_id IN (SELECT id FROM working_paper WHERE project_id = …)`。
- 本地库应用连接用的账号是 `postgres`，`rolsuper=true`、`rolbypassrls=true`，**RLS 在本地实际不生效**。服务器上是否用超级用户取决于 `PG_USER`【未核实】。项目隔离实际靠服务层的 `project_id` 条件和项目级鉴权。

## 2. 关联方式总览

平台表之间有三种关联方式：数据库外键、无外键的引用列（服务层保证）、业务键（编码 / 年度 / 准则等字符串组合）。

### 2.1 主键

- 374 张 ORM 表里 358 张是单列 UUID 主键 `id`。
- 复合主键 10 张：

| 表 | 主键 | 说明 |
|----|------|------|
| `tb_ledger`、`tb_aux_ledger` | (id, year) | 为按年分区预留；本地库里两表是普通表（`relkind='r'`），没有分区 |
| `sys_user_role` | (user_id, role_id) | 账号-角色多对多 |
| `sys_role_project` | (role_id, project_id) | 角色-项目多对多 |
| `procedure_trim_cycle_confirmations` | (project_id, audit_cycle) | 每项目每循环一行粗裁确认 |
| `enum_dict_overrides` | (dict_key, value) | 枚举字典覆盖 |
| `working_paper_oo_content_revision`、`working_paper_sync_entry_state` | (wp_id, entry_id) | 每底稿每在线编辑条目一行 |
| `working_paper_sync_scope_index` | (resource_kind, resource_id) | 同步范围索引 |
| `working_paper_sync_operation_contributor` | (operation_id, participant_id) | 同步操作参与者 |

### 2.2 外键约束

本地库平台表共有 **831 条外键约束**（全部列表见 `database-relationships-fk.md` 第 1 节）。

| 删除规则 | 条数 | 含义 |
|----------|------|------|
| NO ACTION | 549 | 被引用行有引用时不能删（平台主要做软删除，物理删除很少） |
| RESTRICT | 166 | 同上，立即检查；证据、附件、审计链相关表多用它 |
| CASCADE | 70 | 删父行时一起删子行，主要是项目下的运行记录、配置子表、会话子表 |
| SET NULL | 46 | 删父行时把引用列置空 |

**被引用最多的表**：`users` 250 条、`projects` 216 条、`working_paper` 41 条、`service_identities` 22 条、`staff_members` 16 条、`ledger_datasets` 11 条；其余主要是在线编辑同步链内部（`working_paper_sync_operation` 13、`working_paper_artifact` 12、`working_paper_content_version` 11）。

**复合外键**（都在附件域，把项目与年度一起锁进引用，防止跨项目、跨年度挂错版本）：
- `attachment_versions (attachment_id, project_id, audit_year)` → `attachments (id, project_id, audit_year)`
- `attachments (current_version_id, id, project_id, audit_year)` → `attachment_versions (id, attachment_id, project_id, audit_year)`
- `attachment_versions (previous_version_id, attachment_id, project_id, audit_year)` → 自身
- `legacy_attachment_alias` 对上面两张表各有一条同形的复合外键

**自引用**（32 条，树或版本链）：如 `projects.parent_project_id`、`sys_dept.parent_id`、`knowledge_folders.parent_id`、`procedure_instances.parent_id`、`ledger_datasets.previous_dataset_id`、`users.parent_partner_id`、`bad_debt_detail_rows.parent_row_id`、各类 `previous_version_id` / `superseded_by`。

**数据库有、ORM 没声明的外键**（18 条）：
- 只在迁移里建的表，属正常：`checklist_responses`（project_id / wp_id / updated_by）、`workpaper_template_override_version`（3 条）、两张迁移备份表。
- ORM 漏声明（10 条）：上面 5 条附件复合外键、`working_paper.current_content_version_id`、`workpaper_extraction_log.user_id`、`evidence_upload_attempts.command_root_id`、`guidance_handoff_visibility.superseded_by`、`project_workbook_sheet_entry.workbook_instance_id`。用 `Base.metadata.create_all` 建的测试库里没有这些约束。

ORM 声明的外键在库里全部存在。

### 2.3 无外键的引用列

按列名能对应到平台表、但库里和 ORM 都没有外键的列（完整列表见 `database-relationships-fk.md` 第 2 节）：

| 指向 | 列数 | 例子 |
|------|------|------|
| `projects` | 33 | `tb_publish_ack.project_id`、`consol_note_data.project_id`、`workpaper_field_overrides.project_id`、`temporary_grants.project_id` |
| `users` | 26 | 各表的操作人列 |
| `working_paper` | 15 | `procedure_instances.wp_id`、`pbc_checklist.wp_id`、`attachment_working_paper.working_paper_id`、`sampled_vouchers.working_paper_id` |
| `ledger_datasets` | 10 | **四表** `tb_balance / tb_ledger / tb_aux_balance / tb_aux_ledger` 的 `dataset_id`、`account_chart.dataset_id`、`sampling_records.dataset_id` |
| `entry_group_id`（分录组业务键，本身不指向某张表） | 10 | `adjustments` 与 `adjustment_entries` 用它把一笔分录的多行归为一组；`adjustment_collaboration` 等按它挂到这一组；`elimination_entries` 用它给抵销分录分组 |

另有 216 个 `_id` 列无法按名称对应到单一表，主要是：
- 多态引用：同时有 `*_type` / `object_type` 列，如 `logs.object_id`、`audit_log_entries.object_id`、`editing_locks.resource_id`、`evidence_refs.source_id`、`archive_manifest_edges.source_id / target_id`。
- 附注章节、规则等业务编号：`disclosure_notes.section_id`、`consol_note_*.section_id`、`cross_check_results.rule_id`、`formula_push_state.rule_id`。
- 追踪与幂等 id：`trace_id`、`request_id`、`event_id`、`generation_id`。

### 2.4 业务键关联

很多核心关联不走 id，而是走「项目 + 年度 + 编码」组合。主要业务键：

| 业务键 | 出现的表 | 说明 |
|--------|----------|------|
| `project_id + year` | 四表、`trial_balance`、`adjustments`、`financial_report`、`disclosure_notes`、合并各表 | 几乎所有按年数据都带这两列 |
| `account_code`（客户科目） | 四表、`account_mapping.original_account_code` | 客户自己的科目编码 |
| `standard_account_code`（标准科目） | `account_mapping`、`trial_balance`、`adjustment_entries`、`consol_trial`、`report_line_mapping` | 试算表、调整、合并、报表之间的公共键 |
| `company_code` | 四表、`trial_balance`、`adjustments`、`companies`、`consol_scope` | 单体固定 `'001'`；合并时区分子企业 |
| `wp_code` | `wp_index`、`template_library`、`tb_publish_ack`、JSON 配置 | 底稿编码；`working_paper` 本身没有这一列 |
| `report_type + row_code` | `report_config`、`financial_report` | 报表行 |
| `note_section` | `disclosure_notes`、附注模板 JSON | 附注章节号 |
| `entry_group_id` | `adjustments`、`adjustment_entries`、协作 / 处理表 | 一笔调整分录的分组 |
| `(wp_id, item_id)` | `checklist_responses` | 底稿表单逐项内容的唯一键 |

## 3. 核心业务链路的连接逻辑

### 3.1 四表 → 数据集

- 四表的 `dataset_id` 指向 `ledger_datasets.id`，但**没有外键**（`audit_platform_models.py:304-306`）；`import_batch_id` 有外键指向 `import_batches`。
- 统一过滤 `get_active_filter`（`services/dataset_query.py:27-110`）：
  - 默认：`project_id = ? AND year = ? AND dataset_id = <生效数据集> AND is_deleted = false`。
  - 生效数据集由 `get_active_dataset_id` 查：`ledger_datasets.project_id = ? AND year = ? AND status = 'active'`，按 `activated_at DESC NULLS LAST, created_at DESC` 取第一条（`dataset_service.py:50-65`）。
  - 绑定模式 `force_dataset_id`：下游对象（附注、审计报告、底稿等）记了 `bound_dataset_id` 时，锁定读那一版数据。
  - 查不到生效数据集时只按 `project_id + year + is_deleted` 过滤；查询出错时默认回滚后退化成同样条件，`strict=True` 时直接抛错（公式推送等写入方用）。
- 下游绑定列 `bound_dataset_id` 在 `disclosure_notes`、`audit_report`、`working_paper` 上**有外键**（`disclosure_notes` 为 RESTRICT）。

### 3.2 余额表 → 科目映射 → 试算表

`TrialBalanceService.recalc_unadjusted`（`services/trial_balance_service.py:59-298`）：

```text
tb_balance（生效数据集、只取叶子科目）
  └─ 最长前缀匹配 account_mapping：
       mapping.is_deleted = false
       AND (bal.account_code = mapping.original_account_code
            OR bal.account_code LIKE mapping.original_account_code || '.%')
       ORDER BY length(original_account_code) DESC LIMIT 1   → standard_account_code
  └─ 按 standard_account_code 汇总（金额按方向归一成借正贷负）
  └─ 写入 trial_balance（project_id, year, company_code, standard_account_code）
```

- 「叶子科目」= 同项目、同年度、同数据集下没有以它为前缀的子科目（`tb_balance_rollup.leaf_condition`），避免父子科目重复计算。
- 子科目没映射时继承最近已映射的父科目；一个祖先都没映射的科目被丢弃。
- `account_mapping` 唯一键 `(project_id, original_account_code)`；`trial_balance` 唯一键 `(project_id, year, company_code, standard_account_code)`。
- 科目名称兜底取 `account_chart`（`project_id = ? AND source = 'standard'`）。
- 损益类（5、6 开头）取序时账发生额，没有发生额时退回余额表期末数。

### 3.3 调整分录 → 试算表

`recalc_adjustments`（`trial_balance_service.py:303-357`）：

```sql
SELECT ae.standard_account_code, adj.adjustment_type,
       SUM(ae.debit_amount) - SUM(ae.credit_amount)
FROM adjustment_entries ae JOIN adjustments adj ON ae.adjustment_id = adj.id
WHERE adj.project_id = ? AND adj.year = ? AND adj.is_deleted = false
  AND adj.review_status = 'approved'
  AND (adj.origin IS NULL OR adj.origin <> 'workpaper')
  AND <客户已入账 / 不予更正的处理口径>
GROUP BY ae.standard_account_code, adj.adjustment_type
```

- 按 `standard_account_code` 回写 `trial_balance.rje_adjustment / aje_adjustment`；贷方性质科目取反。
- `audited_amount = unadjusted_amount + rje_adjustment + aje_adjustment + wp_adjustment`。
- 来源为底稿的分录被排除，因为底稿结果已通过发布门进入 `wp_adjustment`。

### 3.4 试算表 → 报表（配置表驱动）

- 选准则：`ReportConfigService.resolve_applicable_standard` 读 `projects.template_type` 与 `report_scope`，拼成 `{template_type}_{report_scope}`（默认 `soe_standalone`），不在合法列表里就用 `enterprise`（`report_config_service.py:89-109`）。
- 读配置：`load_effective_report_configs`（`formula_settings/effective_report.py:42-95`）
  - 准则层：`report_config.applicable_standard = <准则> AND is_deleted = false`；
  - 项目层：`applicable_standard = 'project:{project_id}'`（`report_config` **没有 project_id 列**，项目层靠这个字符串编码）；
  - 按 `(report_type, row_code)` 合并，项目层只覆盖公式字段，项目独有的行追加。
- 取数：报表公式按 `trial_balance.project_id = ? AND year = ? AND standard_account_code = <公式里的科目> AND is_deleted = false` 取数（`report_engine.py:611-614`）。
- 结果：写入 `financial_report`，唯一键 `(project_id, year, report_type, row_code)`；与 `report_config` 靠 `report_type + row_code` 对应，没有外键。
- `report_config` 唯一键 `(report_type, row_code, applicable_standard)`；库里没有任何表用外键引用它。

### 3.5 底稿

```text
projects ─< wp_index (project_id, wp_code 唯一) ─< working_paper (wp_index_id 外键)
                 │
                 └─ wp_code = wp_template.template_code（生成时按编码取最新版本模板）
working_paper ─< checklist_responses (wp_id, item_id 唯一)   表单逐项内容
working_paper ─< attachment_working_paper / evidence_links     附件与证据
```

- `working_paper` 没有 `wp_code` 列，按编码找底稿必须 JOIN `wp_index`。
- 模板关联靠编码：`WpIndex.wp_code == WpTemplate.template_code`（`template_engine.py:260`）；同一编码有多版时按 `created_at` 取最新（`template_engine.py:554`）。`template_library` 用 `wp_code` 列，`gt_wp_coding` 只有 `code_prefix / code_range`，按前缀匹配。
- `checklist_responses` 没有 ORM 模型，写入一律 `INSERT … ON CONFLICT (wp_id, item_id) DO UPDATE`。
- `wp_code` → 前端渲染类型 `componentType` 的映射不在库里，在 `backend/app/data/wp_code_overrides.json`。

### 3.6 附注

- 定位键：`disclosure_notes.project_id + year + note_section`（另有 `section_id / parent_section_id` 构成章节树，无外键）。取上年附注用 `year = 本年 - 1`。
- 底稿 → 附注：`last_sync_wp_id` 有外键指向 `working_paper`；哪个底稿推哪一章，由 `backend/data/note_workpaper_sync_registry.json` 决定。
- 模板：`template_type = 'listed'` 读 `note_template_listed.json`，否则读 `note_template_soe.json`（`disclosure_engine.py:991-995`）。
- 报表行 ↔ 附注章节：`note_account_mapping (template_type, report_row_code, note_section_code)`，模板级，没有 project_id。

### 3.7 合并

- 企业关系：`projects` 上有上级与最终控制方的名称和代码（`parent_company_code`、`ultimate_company_code`），以及自引用外键 `parent_project_id`。合并项目 `report_scope = 'consolidated'`。
- `companies (project_id, company_code, parent_code, ultimate_code)`、`consol_scope (project_id, year, company_code, is_included)` 都靠 `company_code` 字符串与 `trial_balance.company_code` 关联，没有外键。
- `consol_trial (project_id, year, standard_account_code)`：`consol_amount = individual_sum + consol_adjustment + consol_elimination`，个别数按标准科目从各子企业试算表汇总。
- `elimination_entries (project_id, year, account_code, entry_group_id …)` 按标准科目进入差额。
- 合并报表取数：`trial_balance.project_id = ? AND year = ? AND company_code IN (范围内企业)`（`consol_report_service.py:545-549`）。

### 3.8 用户、成员与权限

```text
users ─< project_users (project_id, user_id；未删除时唯一)        项目成员与级别
users ─< staff_members (user_id 可空)  ─< project_assignments (staff_id)  人员档案与委派
users ─< sys_user_role >─ sys_role ─< sys_role_project >─ projects        数据权限角色
```

- 委派表 `project_assignments` 用的是 `staff_id`，不是 `user_id`；从委派找到登录账号要经过 `staff_members.user_id`。
- `users.role` 枚举与 `sys_role.role_key` 两套并存，靠取值相同对应。
- 项目级鉴权读 `project_users`；四表过滤里的可选权限检查（`current_user_id`）也读它。

## 4. 配置依赖

### 4.1 项目上的配置开关

`projects` 上几列决定后续选用哪套配置：

| 列 | 决定什么 | 读取位置 |
|----|----------|----------|
| `template_type`（soe / listed） + `report_scope`（standalone / consolidated） | 报表配置用哪套准则；附注模板用哪份 JSON | `report_config_service.py:89-109`、`disclosure_engine.py:991-995` |
| `report_scope = 'consolidated'` | 是否走合并链路；公式推送跳过合并项目 | 合并服务、公式推送 |
| `audit_period_end` | 审计年度（年度取它的年份） | 各服务 |
| `accounting_standard_id` | 外键指向 `accounting_standards`；在报表 / 附注 / 底稿模板选择中**没找到读取方** | `core.py:121-123` |

### 4.2 配置表及被引用方式

| 配置表 | 用途 | 被引用方式 |
|--------|------|------------|
| `report_config` | 报表行与公式（准则层 + 项目层） | 业务键 `applicable_standard + report_type + row_code`；无外键 |
| `formula_template` / `formula_template_version` / `formula_setting` / `formula_template_subscription` | 公式模板、版本、项目层设置、订阅 | 外键：版本、设置随模板 CASCADE；订阅 NO ACTION |
| `wp_template` / `wp_template_meta` / `wp_template_metadata` | 底稿模板与元数据 | 元数据外键指向模板；底稿与模板靠 `wp_code = template_code` |
| `wp_template_set` | 模板集 | `workpaper_generation_operations.template_set_id` 外键（SET NULL） |
| `template_library` / `project_template_selections` | 模板库与项目选择 | 选择表外键指向模板库 |
| `workpaper_template_version` / `workpaper_sheet_classification` | 模板版本与 sheet 归类 | 归类外键指向版本 |
| `procedure_row_definitions` / `procedure_template_revisions` | 程序行定义与版本登记 | `procedure_row_tasks.definition_key` 外键；版本登记无外键引用 |
| `gt_wp_coding` | 致同底稿编码规则 | 按 `code_prefix / code_range` 查，无外键 |
| `note_content_templates` / `note_content_template_versions` | 附注正文模板 | 版本外键 RESTRICT |
| `consol_note_detail_template` / `_version` | 合并附注明细模板 | 版本外键 CASCADE |
| `qc_rule_definitions`、`gate_rule_configs` | 质控规则、门禁规则 | 按 `rule_code` 查，无外键 |
| `ai_model_config` | AI 模型 | 按 `model_type + is_active` 查，无外键 |
| `audit_report_template`、`review_templates`、`report_format_templates` | 报告、复核、报表格式模板 | 无外键引用 |
| `shared_config_templates` / `config_references` | 共享配置模板与引用 | 引用表外键 |
| `sys_role` | 数据权限角色 | `sys_user_role`、`sys_role_project` 外键 CASCADE |
| `system_settings`、`feature_flags`、`enum_dict_overrides` | 系统键值、功能开关、枚举覆盖 | 按键读取 |

### 4.3 文件配置（不在库里）

| 文件 | 作用 | 读取方 |
|------|------|--------|
| `backend/data/wp_account_mapping.json` | 底稿 ↔ 科目映射（致同 2025 修订版），库里没有对应表 | 业务分类、调整影响、高级查询、地址库、一致性检查、附注引擎等 10 多个模块 |
| `backend/app/data/wp_code_overrides.json` | `wp_code` → 前端渲染类型，按修改时间热重载 | `wp_code_override_loader.py:17` |
| `backend/data/formula_push_rules.json` | 公式推送规则（试算表 → 底稿 → 附注） | `formula_push/rules.py:39` |
| `backend/data/note_workpaper_sync_registry.json` | 底稿 ↔ 附注章节 | `note_wp_mapping_service.py:62-66` |
| `note_template_soe.json` / `note_template_listed.json` / `note_templates_seed.json` | 附注模板与种子 | `disclosure_engine.py` |
| `backend/data/consol_note_section_mapping.json` | 合并附注 ↔ 单体附注章节 | `consol_note_section_mapping.py:21-33` |

改这些文件等于改关联规则，需要和代码一起评审。

## 5. 发现的问题与风险

| 编号 | 问题 | 影响 | 证据 |
|------|------|------|------|
| 1 | RLS 在本地不生效：应用用超级用户 `postgres` 连接，超级用户绕过 RLS | 项目隔离完全依赖服务层条件；服务器是否同样用超级用户【未核实】 | `pg_roles`：`rolsuper=true, rolbypassrls=true` |
| 2 | RLS 只覆盖 7 张表，带 `project_id` 的表有 240 张 | 即使改用普通账号，绝大多数表也没有库级隔离 | `pg_policies` |
| 3 | 四表 `dataset_id` 没有外键 | 删除或改动数据集不会被库拦住，靠服务层维护 | `audit_platform_models.py:304-306` |
| 4 | `report_config` 用 `applicable_standard = 'project:{id}'` 表示项目层 | 项目删除后项目层配置行不会随之清理；按项目查找或清理只能做字符串匹配 | `effective_report.py:31-32` |
| 5 | 33 个 `project_id` 列、15 个指向底稿的列没有外键 | 可能产生指向已删除项目或底稿的孤儿行 | `database-relationships-fk.md` 第 2 节 |
| 6 | 10 条外键只在库里有、ORM 没声明 | 测试用 `create_all` 建的库少了这些约束，测试测不到违反约束的情况 | 2.2 节 |
| 7 | `get_active_filter` 的可选权限检查没过滤 `project_users.is_deleted` | 已移出团队的成员仍能通过这道检查（只在传了 `current_user_id` 时生效） | `dataset_query.py:69-79` |
| 8 | `recalc_adjustments` 只过滤 `adjustments.is_deleted`，没过滤 `adjustment_entries.is_deleted` | 单独软删的明细行仍会计入试算表；是否存在单删明细的路径【未核实】 | `trial_balance_service.py:335-349` |
| 9 | `projects.accounting_standard_id` 有外键但没找到用于选模板的读取方 | 准则实际由 `template_type + report_scope` 决定，这一列可能已闲置 | 4.1 节 |
| 10 | `tb_ledger`、`tb_aux_ledger` 主键含 `year`、模型注释写「按年分区」，库里是普通表 | 大账套下序时账查询只能靠索引 | `pg_class.relkind = 'r'` |
| 11 | 平台表与 Metabase 表共用一个库，Metabase 也有一张 `audit_log` | 容易查错表；迁移和备份会带上 Metabase 数据 | 第 0 节 |

以上问题本次只做记录，没有修改代码或数据库。
