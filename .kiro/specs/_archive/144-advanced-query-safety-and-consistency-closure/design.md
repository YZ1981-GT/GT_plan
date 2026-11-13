# 设计文档：高级查询安全与一致性收口

## 1. 现状与裁决

当前生产有两套 planner：业务语义源走 `QueryOrchestrator`，白名单物理表走 `builder_dsl`。本轮不强行合并 planner，只统一安全、错误、预算、审计和前端状态原则。

### ADR-AQS-01：三个高级查询写端点改为无依赖 410 桩

前端生产调用方为 0，而确认端点的 `preview_id` 未消费，服务最多预览 10,000 项却可能写入原始全部目标。采用 410 而非直接删除路由：旧客户端得到可诊断结果，且变更可逆。桩不带 `get_db`、`get_current_user` 或请求模型，保证不触达业务数据。替代方式是下钻到权威页面后编辑，或复制经地址库校验的公式引用。

### ADR-AQS-02：OwnershipGuard 同时判项目存活与成员关系

`_accessible_project_ids` 的成员和分派查询 JOIN `projects` 并过滤未删除；`_can_access_project` 在任何角色捷径之前查询项目存活。这样 admin/partner 仍可访问全部活项目，但不能访问回收站项目。`filter_accessible_rows` 对全局角色也只保留活项目行。

### ADR-AQS-03：请求了数据变换就必须得到该变换

`group`/`pivot` 模块缺失或内部异常不再追加 warning 后返回原始行，而是抛统一 `QUERY_TRANSFORM_FAILED`。合法性错误保留原来的领域错误码。

### ADR-AQS-04：按真实方言设置超时

通过 `db.get_bind().dialect.name` 判断方言。SQLite 等非 PostgreSQL 方言跳过 `SET LOCAL`；PostgreSQL 事务探测或设置失败直接抛出 `QUERY_GUARD_UNAVAILABLE`，不得无预算执行。查询被 PG 取消仍映射为 408。

### ADR-AQS-05：严格 DSL 与稳定输出

为 JOIN、聚合建立严格 Pydantic 模型；列表在模型层限长。编译前验证输出键唯一、普通字段全部属于 GROUP BY。分组而未显式排序时按所有分组列升序，保证 offset 翻页稳定。深 offset 与业务视图同为 100,000 上限。

### ADR-AQS-06：审计和错误分层

构建器成功执行复用 `audit_helper.record_query_execution`，source 使用 `builder:<table>`，作用域和 total 进入 details。SQLAlchemy 异常生成 32 位追踪号，只向前端返回通用中文消息；异常详情留在服务端 logger。

### ADR-AQS-07：范围摘要进入业务缓存键

在业务编排器进入缓存前解析一次 `CycleScopeCache`，把“不限”或排序后的循环集合摘要并入 scope signature。数据内容仍使用既有短 TTL；全平台事件版本化不在本轮临时重造。
### ADR-AQS-08：前端以请求代际和冻结上下文为准

三个查询宿主各维护递增 request generation。每次请求捕获自己的 generation，只有仍为最新时才能落 rows/error/loading。上下文变化调用统一 `invalidateResult()`，同时推进 generation、清 rows、COUNT token、引用状态和 lastRun。

`CustomQueryFieldPicker` 新增 `projectId` prop，并传给 `useAcnr`；宿主所选项目是真源。项目变化时清空已选地址，因为 addr_id 本身不编码项目，而当前值和权限均按项目解析。

全局弹窗保存服务端 `count_token`，仅 `resetPage=false` 且查询定义未变时发送。指标树使用页面版的骨架模式；需要底稿 sheet 时由现有选区器按底稿编码请求预览，不依赖一次加载全量底稿树。

## 2. 组件改动

### 后端

- `routers/custom_query.py`：`cell-writeback` 改 410 桩，移除端点运行依赖；保留共享类型兼容导入。
- `routers/custom_query_writeback.py`：两个端点改 410 桩。
- `router_registry/system.py`：保留伴生 router 注册，更新退役说明。
- `services/custom_query/ownership_guard.py`：活项目过滤。
- `services/custom_query/query_orchestrator.py`：循环范围缓存身份、变换 fail-closed。
- `services/custom_query/execution_guard.py`：按方言 fail-closed。
- `services/custom_query/builder_dsl.py`：严格 DSL、预算和稳定分组排序。
- `routers/query_builder.py`：错误脱敏、成功审计。

### 前端

- `CustomQueryFieldPicker.vue`：显式项目 prop。
- `CustomQueryDialog.vue`：请求代际、上下文失效、COUNT token、指标树轻量加载。
- `CustomQueryTab.vue`：请求代际、项目/年度/源变化清结果、picker 项目传递。
- `AdvancedQueryBuilder.vue`：请求代际、范围变化清结果、picker 项目传递。

## 3. 错误契约

| 场景 | HTTP | error_code |
|---|---:|---|
| 高级查询写端点退役 | 410 | `ADVANCED_QUERY_WRITEBACK_RETIRED` |
| 回收站或无权项目 | 403 | `FORBIDDEN_PROJECT` |
| 分组/透视内部失败 | 500 | `QUERY_TRANSFORM_FAILED` |
| PG 查询保护无法设置 | 503 | `QUERY_GUARD_UNAVAILABLE` |
| DSL 过大/不一致 | 422/400 | 现有 Pydantic 码或 `INVALID_QUERY_SHAPE` |
| 数据库执行失败 | 400 | `QUERY_EXECUTION_FAILED` + `correlation_id` |

## 4. 验证策略

先以现有高级查询测试作为基线，再增加一个后端安全收口测试文件和前端三组定点测试。每个安全判据至少做一次反向故障注入：恢复写端点、去掉活项目条件、让分组异常降级、吞 PG 超时设置错误、允许深 offset、让旧请求覆盖新请求，均须变红。真 PG 只读验证索引与查询计划，浏览器验证上下文切换、翻页和无错误运行。

## 5. 延期项

- W3 系统审计预置、W6 对象级反向入口继续由 `advanced-query-linkage-closure` 承接。
- 查询证据、附件/凭证动作、QueryArtifact、AI 与知识库联动另立后续 spec。
- 跨进程导出闸和全平台事件版本化需要 Redis/事件总线统一设计，本轮不做局部副本。
- `SnapshotWriter`、预览服务及其底层契约的物理删除需先处理 workpaper-sync 测试和清册，另批执行。
