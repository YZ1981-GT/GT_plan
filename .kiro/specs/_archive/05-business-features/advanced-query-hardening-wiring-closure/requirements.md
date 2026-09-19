# Requirements Document

## Introduction

高级查询模块（`/api/query` 白名单构建器 + `/api/custom-query` 业务视图）存在一个**已建成但未接线的服务层**：`backend/app/services/custom_query/` 20 个文件中，`query_orchestrator` / `execute_compatibility` / `export_service` / `writeback_preview` / `param_sql_builder` / `template_service` / `template_scope_adapter` 共 7 个模块在 `backend/app/` 全域 **router 引用数为 0**，只被同包内部与测试引用。这是「additive 注入即死代码」的教科书形态：能力声明存在、契约测试存在、生产链路从不经过。

对应实测基线（工作树 `git status --porcelain` 为 0 条，全部为 HEAD 已入库状态）：

| 测试文件 | 实测 |
|---|---|
| `backend/tests/test_advanced_query_hardening_wave012.py` | 60 failed |
| `backend/tests/test_custom_query_template_scope_hardening.py` | 7 failed |
| `backend/tests/test_custom_query_templates.py::TestEnsureCustomQueryTables` | 8 failed |
| **后端合计** | **75 failed / 20 passed** |
| `advancedQueryFrontend.spec.ts` + `advancedQueryFrontend-p7.spec.ts` | **5 failed / 48 passed** |

浏览器与真实 PG 侧另有独立实证（非测试推断）：

- 未认证直连 `GET /api/custom-query/indicators`、`/wp-id-by-code`、`/wp-sheet-preview` 三端点全部返回 **200**（响应体分别约 700335 / 165 / 3117 bytes）。
- 高级构建器选 `trial_balance`、无筛选执行返回 100 行，生成的 SQL **无 `WHERE project_id`**；以认证 token 取 `limit=1000` 仅选 `project_id` 列，实际 1000 行**覆盖 9 个不同项目**。
- 传入无效 `acnr_targets` 仍返回 200、无 warning、字段被静默忽略。
- 真实 PG `statement_timeout = 0`；`tb_ledger` 约 6,971,441 行；高级查询白名单主表中仅 4 张启用 FORCE RLS。
- 指标树单次响应约 578057 字符 / 3089 节点 / 2766 叶子，浏览器慢请求监控记录 **3391ms**。

本 spec 的目标不是新增能力，而是**把已存在的服务层真正接进生产链路，并关闭安全、分页、预算、模板与前端契约五处缺口**，以 75 + 5 条已入库红测试作为验收基线。

## Glossary

| 术语 | 含义 |
|---|---|
| 业务视图 | `/api/custom-query` 链路，按指标树选数据源（report / trial_balance / workpaper 等 14 个取数器） |
| 白名单构建器 | `/api/query` 链路，按表 + 字段 + 算子 + JOIN 的 DSL 自由组合查询 |
| adapter | `ExecuteCompatibilityAdapter`，legacy 请求体 ↔ `QueryRequest` / `QueryResult` 的双向转换层 |
| 编排器 | `QueryOrchestrator`，统一执行链 Ownership_Check → resolve → cache → fetch → group → pivot → serialize |
| 技术列 | `id` / `project_id` / `is_deleted` / `created_at` / `updated_at` 等非业务语义列 |
| tie-breaker | 追加在用户排序之后的唯一键排序项，保证重复排序键下翻页确定性 |
| 全有或全无 | 多目标操作中任一目标校验失败即整体拒绝，不产生部分执行/部分写入 |
| fail-open | 异常被吞成成功响应（如 `except Exception` → 200 + `{"error": str(e)}`） |
| 复杂度预算 | JOIN 条数 / 分组维度 / 聚合个数 / 导出行数 / 执行时长的显式上限 |

## Requirements

### Requirement 1: 只读端点认证与项目归属校验

三个业务视图只读端点当前仅 `Depends(get_db)`，无认证、无归属校验，匿名可读。`wp_sheet_preview` 更严重：降级分支会调用 `init_workpaper_from_template` **写文件**，即无认证端点触发副作用。

#### Acceptance Criteria

1.1. WHEN 未认证请求访问 `/api/custom-query/indicators`、`/wp-id-by-code`、`/wp-sheet-preview` THEN 系统 SHALL 返回 401，且不执行任何数据库查询。

1.2. WHEN 已认证用户请求上述端点且携带的 `project_id` 不在其可访问项目集合内 THEN 系统 SHALL 返回 403 `FORBIDDEN_PROJECT`，且在返回前不构建指标树、不读取底稿单元格、不触发模板初始化。

1.3. WHEN `get_indicators` 收到无效或不可访问的 `project_id` THEN 系统 SHALL 在建树之前完成归属校验（校验先于 `_resolve_project_template_type` / `_build_consol_units_tree` / `_build_workpaper_tree` 的任何调用）。

1.4. WHEN `wp_sheet_preview` 的归属校验未通过 THEN 系统 SHALL 不调用 `init_workpaper_from_template`，即不产生任何文件写入副作用。

1.5. WHERE 归属校验发生 THE 系统 SHALL 复用 `OwnershipGuard.assert_target_accessible` 作为唯一入口，不新写第二套项目可见性判定。

1.6. WHEN 归属校验因 `project_id` 格式非法而无法确定目标项目 THEN 系统 SHALL fail-closed 拒绝并记录一条 `advanced_query.ownership_denied` 审计。

### Requirement 2: 白名单构建器项目作用域

`query_builder.py` 全链路零 `project_id` 注入，`_build_select` 只做表/列/算子白名单。任何 admin / manager / partner 可一次查询跨全部客户项目；缓存键写死 `project_id="__query_builder__"`，跨项目共用命名空间。

#### Acceptance Criteria

2.1. WHEN 构建器执行查询且目标表含 `project_id` 列 THEN 系统 SHALL 强制注入 `project_id IN (可访问项目集合)` 过滤，该过滤 SHALL 不可由用户 DSL 覆盖或移除。

2.2. WHEN 用户角色为 admin / partner（全项目可访问）THEN 系统 SHALL 允许不限项目，但 SHALL 在响应中标注实际生效的项目作用域。

2.3. WHEN 目标表为不含 `project_id` 的全局配置表（`report_config`）THEN 系统 SHALL 跳过项目过滤，并在响应 warnings 中标注该表为全局配置。

2.4. WHEN 构建器计算缓存键 THEN 系统 SHALL 把实际生效的项目作用域纳入键，使不同作用域的用户不共享缓存条目。

2.5. WHEN 请求显式指定 `project_id` 且该项目不可访问 THEN 系统 SHALL 返回 403 `FORBIDDEN_PROJECT`，不执行查询。

2.6. WHERE 白名单构建器执行前 THE 系统 SHALL 调用 `table_whitelist.enforce_query_plan` 作为表 / JOIN / 算子 / 聚合的单一门禁，替代当前私有的 `_resolve_table` / `_resolve_column` 旁路。

### Requirement 3: 统一执行契约与单一执行路径

`custom_query.execute_query` 当前内联分发 14 个 `_query_*`，`ExecuteCompatibilityAdapter` 零调用。同时 `QueryRequest` / `QueryResult` / `ColumnMeta` 与 adapter 已读取的字段互不兼容：adapter 读 `result.limit` / `result.offset` / `column.source`，而三个 dataclass 均无这些字段。

#### Acceptance Criteria

3.1. WHEN `/api/custom-query/execute` 被调用 THEN 系统 SHALL 经 `ExecuteCompatibilityAdapter.execute` 作为唯一执行路径，该 adapter 在一次请求中 SHALL 被调用恰好一次。

3.2. WHEN 编排器或 adapter 抛出运行时异常 THEN 系统 SHALL 不存在任何旧内联分支作为 fallback 兜底执行。

3.3. WHEN legacy 请求体缺少新增字段 THEN adapter SHALL 填充安全默认值；WHEN 请求体含全部新字段 THEN adapter SHALL 无损传递。

3.4. THE `QueryRequest` SHALL 提供 `source` / `year` / `filters` / `columns` / `sort` / `limit` / `offset` 字段，与业务视图 legacy 请求体一一对应。

3.5. THE `QueryResult` SHALL 携带 `total` / `limit` / `offset` / `warnings`，且 `to_payload` / `from_payload` 往返 SHALL 无损保留全部列元数据。

3.6. THE `ColumnMeta` SHALL 提供 `source` 字段，形态为 `{"manual": bool, "provenance": list, "trace": list}`，并在 adapter 的 legacy 响应转换与缓存 payload 往返中原样保留。

3.7. WHEN 14 个 `_query_*` 取数器被调用 THEN 它们 SHALL 作为注入的 `business_fetcher` 被编排器驱动，而非由 router 直接分发。

3.8. WHEN ACNR 目标解析失败 THEN 系统 SHALL 返回 4xx 且 SHALL NOT 触达任何取数器。

### Requirement 4: 稳定分页

业务视图 `QueryRequest.offset` 声明后**全文件零使用**（14 个取数器签名均为 `(db, pid, year, filters, limit)`，SQL 只拼 `LIMIT :lim`），前端却在传 `offset: 0` —— 业务视图实际不存在第 2 页。`total` 等于截断后行数，无法判断是否有下一页。构建器侧 `order_by` 为空即无 `ORDER BY` 却直接 `.offset()`。

#### Acceptance Criteria

4.1. WHEN 查询带 `group_by` 或 `pivot` THEN `total` SHALL 反映分组/透视**之后**的行数，而非原始取数行数。

4.2. WHEN 用户提供 `sort` THEN 系统 SHALL 在用户排序项**之后追加**唯一 tie-breaker，不替换用户排序；WHEN 用户未提供 `sort` THEN 系统 SHALL 使用领域默认排序 + tie-breaker。

4.3. WHEN 同一查询以相同参数重复执行 THEN 结果行顺序 SHALL 完全一致（重复排序键下亦然）。

4.4. WHEN `offset` 超过 `total` THEN 系统 SHALL 返回空 `rows` 且 `total` 保持不变。

4.5. WHEN 逐页取完全部页 THEN 各页 `rows` 的并集 SHALL 等于全量结果集且各页之间 SHALL 无重叠。

4.6. WHEN `limit = 0`、`limit` 超出上限、或 `offset < 0` THEN 系统 SHALL 返回 422。

4.7. WHEN `sort` 引用不存在的字段或非法方向值 THEN 系统 SHALL 返回 422，不执行查询。

4.8. WHEN 取数层被驱动 THEN 系统 SHALL 请求未截断的源行集，SHALL NOT 在取数层预先施加展示用 `limit`（避免 `total` 退化为截断行数）。

### Requirement 5: 规范错误处理与审计

`custom_query.py` 的 `except Exception` 把全部异常（含超时、连接中断、列不存在）吞成 200 `{"rows": [], "error": str(e)}`。前端看到的是空结果而非失败原因。另有一条必然报错的 SQL：`SELECT id FROM working_paper WHERE wp_code = :code`，而 `working_paper` 表无 `wp_code` 列（该列在 `wp_index`）。

#### Acceptance Criteria

5.1. WHEN 请求处理中抛出 `HTTPException` THEN 系统 SHALL 原样上抛并保留原状态码，SHALL NOT 回滚事务、SHALL NOT 降级为 200。

5.2. WHEN 抛出非预期异常 THEN 系统 SHALL 回滚事务并返回 500，响应体 SHALL 含 correlation id 供日志关联。

5.3. WHEN 查询失败 THEN 系统 SHALL NOT 返回 2xx 携带 `error` 字段的形态。

5.4. WHEN cell-writeback 需按 `wp_code` 定位底稿 THEN 系统 SHALL 经 `wp_index` JOIN 查询，SHALL NOT 引用 `working_paper.wp_code`。

5.5. WHEN 归属校验拒绝、查询超时或预算超限 THEN 系统 SHALL 各记录一条可区分 `action` 的审计，且审计写入失败 SHALL NOT 掩盖原始错误响应。

### Requirement 6: JOIN 安全与复杂度预算

`JOIN_WHITELIST` 登记了三处仅按 `project_id` 关联的 JOIN（`trial_balance → wp_index`、`adjustments → wp_index`、`projects → 8 张业务表`），构成项目内笛卡尔积。`LIMIT` 施加在笛卡尔积之后，PG 仍须物化整个 join 结果；导出路径 `fetchmany` 无行数上限。全仓 `statement_timeout` 命中数为 0。

#### Acceptance Criteria

6.1. WHEN 登记或使用一条 JOIN THEN 其 ON 条件 SHALL 至少含一个非 `project_id` 的业务键；仅按 `project_id` 关联的 JOIN SHALL 被拒绝并给出可读原因。

6.2. WHEN 单次查询声明的 JOIN 条数超过上限 THEN 系统 SHALL 返回 400 并标明上限值。

6.3. WHEN 分组维度数或聚合个数超过上限 THEN 系统 SHALL 返回 400 并标明上限值。

6.4. WHEN 执行查询或导出 THEN 系统 SHALL 设置语句级超时；WHEN 超时触发 THEN 系统 SHALL 返回可识别的超时错误码而非空结果。

6.5. WHEN 客户端断开连接 THEN 系统 SHALL 取消在途查询，不继续占用连接池。

6.6. WHEN 导出行数达到硬上限 THEN 系统 SHALL 截断并在文件内显式标注被截断，SHALL NOT 静默产出不完整文件。

6.7. WHERE 预算常量已在 `export_service` / `writeback_preview` / `PivotConfig` 中定义 THE 系统 SHALL 复用这些既有常量，SHALL NOT 在 router 层另写一套阈值。

### Requirement 7: 技术列与 PII 收敛

`TABLE_WHITELIST` 15 张表的 `fields` 全部包含 `id` / `project_id` / `is_deleted` / `created_at` / `updated_at`，`staff_members` 另含 `email` / `phone` / `user_id`。前端 `dsl.fields = []` 是默认值，用户不选字段即命中「无 fields 默认全字段」分支，结果表第一列是 UUID。

#### Acceptance Criteria

7.1. WHEN 用户未显式选择字段 THEN 系统 SHALL 使用该表的业务默认列集，SHALL NOT 返回技术列。

7.2. WHEN `GET /api/query/schema` 下发字段清单 THEN 系统 SHALL 区分业务列与技术列，使前端可默认只展示业务列。

7.3. WHEN 用户显式选择技术列 THEN 系统 SHALL 允许（保留排查能力），但 SHALL 在响应 warnings 中标注。

7.4. WHEN 字段属于 PII（`email` / `phone` / `user_id`）THEN 系统 SHALL 仅对具备相应权限的角色下发，其余角色 SHALL 从 schema 中隐去该字段并在被显式请求时返回 403。

7.5. WHERE 业务默认列集被定义 THE 定义 SHALL 位于 `table_whitelist` 单一真源内，与 `fields` 并列声明，SHALL NOT 在前端复制第二份。

### Requirement 8: 模板作用域治理

`TemplateScopeAdapter` 与 `TemplateService` 生产零引用，router 自写 CRUD。`delete_template` 允许 admin 删他人模板；分享目标项目未逐个鉴权；`scope` 的 legacy `global` 与 canonical `public` 未收敛。

#### Acceptance Criteria

8.1. WHEN 模板被读写 THEN 系统 SHALL 经 `TemplateScopeAdapter.normalize` / `normalize_record` 归一 `scope`，legacy `global` SHALL 对外呈现为 canonical 值并在 UI 显示为「公开」。

8.2. WHEN `scope` 为团队级 THEN 系统 SHALL 要求配置中存在项目锚点，SHALL NOT 复用 `shared_project_ids` 推断锚点。

8.3. WHEN 模板声明 `shared_project_ids` THEN 系统 SHALL 对其中**每个** project_id 逐个鉴权。

8.4. WHEN 任一分享目标鉴权失败 THEN 系统 SHALL 在写入之前回滚，SHALL NOT 落库任何部分结果。

8.5. WHEN 非模板创建者（**包括 admin**）尝试 update 或 delete THEN 系统 SHALL 返回 403。

8.6. WHEN 执行模板 THEN 系统 SHALL 重新校验目标项目归属并复用主 execute 链路，SHALL NOT 另走旁路。

8.7. WHEN 只读角色保存模板 THEN 系统 SHALL 仅允许私人 scope，分享相关字段 SHALL fail-closed 置空。

### Requirement 9: 回写预览与确认端点

`writeback_preview.py`（30KB，含 `WritebackPreviewService.generate` / `WritebackConfirmationGate.validate`）生产零引用，router 上不存在 `writeback_preview` / `writeback_confirm` 端点。

#### Acceptance Criteria

9.1. THE router SHALL 提供 `writeback_preview` 与 `writeback_confirm` 两个端点，分别接 `WritebackPreviewService.generate` 与 `WritebackConfirmationGate.validate`。

9.2. WHEN 只读角色调用上述端点 THEN 系统 SHALL 返回 403。

9.3. WHEN 请求含无权访问的项目 THEN 系统 SHALL 返回 403，且 `WritebackPreviewService.generate` 与 `SnapshotWriter.write_cell` SHALL 均不被调用。

9.4. WHEN 多目标中任一目标归属校验失败 THEN 系统 SHALL 整体 403，SHALL NOT 产生部分写入。

9.5. WHEN 预览项数超过 `MAX_PREVIEW_ITEMS` 或生成超过预览超时 THEN 系统 SHALL 返回可识别错误码，复用既有常量。

### Requirement 10: 模板表结构幂等保障

`backend/tests/test_custom_query_templates.py::TestEnsureCustomQueryTables` 8 条测试全红，因 `backend/scripts/_ensure_custom_query_tables.py` 不存在。

#### Acceptance Criteria

10.1. THE 系统 SHALL 提供 `backend/scripts/_ensure_custom_query_tables.py`，导出 `main` / `DDL` / `INDEXES_DDL` / `CHECK_SQL` / `ALTER_ADD_COLUMNS`。

10.2. WHEN 模块被导入 THEN SHALL 无副作用（不连库、不执行 DDL）。

10.3. THE `DDL` SHALL 使用 `CREATE TABLE IF NOT EXISTS`，`INDEXES_DDL` SHALL 使用 `CREATE INDEX IF NOT EXISTS`，重复执行 SHALL 幂等。

10.4. THE `DDL` 的 scope CHECK 约束 SHALL 覆盖全部合法 scope 取值，`ALTER_ADD_COLUMNS` SHALL 覆盖旧库可能缺失的新增列。

10.5. WHERE 该脚本与 `V101` / `V102` 迁移并存 THE 两者的列与索引定义 SHALL 一致，SHALL NOT 出现第二套互相漂移的真源。

### Requirement 11: 前端契约对齐

`CustomQueryTab.vue:516` 使用 `canDo('edit', 'project_settings')` 判定构建器可用，而后端判据是 `role ∈ (admin, manager, partner)` —— 两套判据会漂移。测试 mock 仅返回 `currentRole` 未返回 `canDo`，导致 2 条测试报 `canDo is not a function`。

#### Acceptance Criteria

11.1. WHEN 前端判定高级构建器入口可用性 THEN 判据 SHALL 与后端 `_QUERY_BUILDER_ROLES` 语义一致，且该判据 SHALL 有单一来源。

11.2. WHEN 角色不足 THEN 入口 SHALL 显示为禁用（可见不可点）并给出中文原因提示，且绕过 UI 直接调用 SHALL 被后端 403 拦截。

11.3. WHEN 前端渲染查询结果 THEN 默认 SHALL NOT 展示技术列，且 SHALL 提供显式开关以查看技术列。

11.4. WHEN 结果行数达到当前页上限 THEN 前端 SHALL 提供翻页能力并展示真实 `total`，SHALL NOT 仅提示「可能被截断」。

11.5. WHEN 模板 scope 为 legacy `global` THEN 前端 SHALL 显示为 canonical「公开」。

11.6. WHEN 只读角色保存模板 THEN 前端 SHALL 仅提交私人 scope；WHEN 用户有分享权限 THEN SHALL 仅提交去重后的可编辑项目集合。

11.7. WHERE 前端测试 mock `usePermissionMatrix` THE mock SHALL 返回组件实际消费的全部成员，避免以 mock 缺失伪装成生产缺陷。

### Requirement 12: 指标树加载性能

`get_indicators` 单次返回 9 大类完整树（实测 578057 字符 / 3089 节点 / 2766 叶子 / 3391ms），`CustomQueryTab.loadIndicators` 每次挂载全量拉取且无缓存。

#### Acceptance Criteria

12.1. WHEN 指标树首次加载 THEN 系统 SHALL 仅返回顶层大类与其子类骨架，叶子明细 SHALL 按需加载。

12.2. WHEN 用户展开某个大类 THEN 系统 SHALL 仅加载该分支的子节点。

12.3. WHEN 树结构 schema 升版 THEN 前端缓存 SHALL 自动失效（复用 `X-Indicators-Schema-Version`）。

12.4. WHEN 同一会话内重复打开查询入口 THEN 前端 SHALL 复用缓存骨架，SHALL NOT 重复全量拉取。

12.5. WHEN 懒加载接入后 THEN 首屏指标树响应体 SHALL 显著小于当前全量体积，且该收敛 SHALL 由可执行判据度量而非目视。
