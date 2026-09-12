# Implementation Plan

## Overview

以已入库的 **75 条后端红 + 5 条前端红**为验收基线，把 7 个零引用服务模块接进生产链路，并关闭安全、分页、预算、模板、前端五处缺口。

任务完成的定义是**对应测试由红转绿 + 变异检验打红**，不是「代码已写」。标 `*` 的为测试/验证类子任务，按平台约定同样全部完成。

## Tasks

- [ ] 1. 固化红基线与辐射面
- [x] 1.1 记录后端 75 / 前端 5 的逐条失败清单为判据 JSON
  - 产物 `backend/scripts/check/advanced_query_hardening_baseline.json`，含每条 `nodeid` + 失败类型（缺字段 / 缺端点 / 缺文件 / 断言不符）
  - 脚本 `backend/scripts/check/check_advanced_query_baseline.py` 支持 `--check`（只读比对，不改文件）
  - _Requirements: 全部_

- [x] 1.2 按引用关系反查回归辐射面
  - 扫 `backend/tests/**` 对 `routers.custom_query` / `routers.query_builder` / `services.custom_query.*` / `services.query_cache` 的实际 import 与 monkeypatch 引用，产出目标测试文件清单
  - 禁止用全量 `backend/tests`（1522 文件）
  - _Requirements: 全部_

- [ ] 2. 统一执行契约的数据模型对齐
- [x] 2.1 `ColumnMeta` 增加 `source` 字段
  - `backend/app/services/custom_query/query_orchestrator.py`：新增 `source: Optional[str]`，取值 ∈ {manual, provenance, trace}
  - `build_column_meta` / `mount_addr_id` / `_finalize_columns` 同步透传
  - _Requirements: 3.6_ · _属性: P8_

- [x] 2.2 `QueryRequest` 补齐业务视图字段
  - 新增 `source` / `year` / `filters` / `columns` / `sort` / `limit` / `offset`；`page` / `page_size` 保留为派生视图不破坏既有绿测试
  - `cache_def()` 纳入新字段，保证缓存键随分页与排序变化
  - _Requirements: 3.4_

- [x] 2.3 `QueryResult` 补齐 `limit` / `offset` 并修往返
  - 新增 `limit` / `offset`（`execute_compatibility.py:106-107` 已在读取，当前必 `AttributeError`）
  - `to_payload` / `from_payload` 补全新字段与 `ColumnMeta.source`
  - _Requirements: 3.5_ · _属性: P8_

- [x] 2.4* 列元数据与 adapter 往返属性测试
  - Property 7 / 8 各一条 Hypothesis 测试，`max_examples ≥ 100`
  - _Requirements: 3.3, 3.5, 3.6_ · _属性: P7, P8_

- [ ] 3. 只读端点认证与归属校验
- [x] 3.1 三个只读端点加认证依赖
  - `backend/app/routers/custom_query.py`：`get_indicators`(67) / `wp_id_by_code`(814) / `wp_sheet_preview`(899) 增加 `current_user: User = Depends(get_current_user)`
  - 参数名与顺序须满足契约测试直调形态（`get_indicators(project_id, response, db, current_user)`）
  - _Requirements: 1.1_ · _属性: P1_

- [x] 3.2 归属校验置于取数与副作用之前
  - `get_indicators` 的守卫先于 `_resolve_project_template_type` / `_build_consol_units_tree` / `_build_workpaper_tree`
  - `wp_sheet_preview` 的守卫先于 `init_workpaper_from_template`（消除无认证端点写文件）
  - 统一复用 `ownership_guard.assert_target_accessible`，不新写可见性判定
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6_ · _属性: P2, P3_

- [x] 3.3* 只读门禁属性测试与调用计数断言
  - Property 1 / 2 / 3 各一条，断言 403 时树构建器与模板初始化调用计数为 0
  - _Requirements: 1.1, 1.2, 1.4_ · _属性: P1, P2, P3_

- [ ] 4. 模板表结构幂等脚本
- [x] 4.1 新建 `backend/scripts/_ensure_custom_query_tables.py`
  - 导出 `DDL` / `INDEXES_DDL` / `CHECK_SQL` / `ALTER_ADD_COLUMNS` / `main`；`CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`
  - 导入无副作用（`main` 仅 `__main__` 下执行）
  - _Requirements: 10.1, 10.2, 10.3, 10.4_ · _属性: P22_

- [x] 4.2 与 V101 迁移交叉锁死
  - 守卫测试比对脚本 DDL 与 `V101__advanced_query_template_sharing.sql` 的列集与索引集一致，防第二套真源漂移
  - _Requirements: 10.5_ · _属性: P22_

- [ ] 5. JOIN 安全与复杂度预算
- [x] 5.1 移除三处纯 project_id 的 JOIN 登记
  - `backend/app/services/custom_query/table_whitelist.py`：删 `trial_balance → wp_index`(219)、`adjustments → wp_index`(235)、`projects → 8 张业务表`(253-262)
  - `projects` 保留在 `TABLE_WHITELIST` 与作为 JOIN 目标，仅禁其作 base 向下发散
  - _Requirements: 6.1_ · _属性: P15_

- [x] 5.2 新增 JOIN 业务键校验与导入期不变式
  - `enforce_join_business_key(base, target, on_pairs)` → 400 `JOIN_MISSING_BUSINESS_KEY`
  - `_assert_all_joins_have_business_key()` 在模块导入期执行，违规登记直接导入失败
  - _Requirements: 6.1_ · _属性: P15_

- [x] 5.3 新增复杂度预算门禁
  - `MAX_JOINS_PER_QUERY` / `MAX_GROUP_DIMS` / `MAX_AGGREGATES` + `enforce_complexity_budget`
  - 复用 `export_service` 与 `writeback_preview` 已有常量，不另写阈值
  - _Requirements: 6.2, 6.3, 6.7_ · _属性: P16_

- [x] 5.4* JOIN 与预算属性测试
  - Property 15 / 16 各一条；含「移除违规 JOIN 后无笛卡尔积回归」断言
  - _Requirements: 6.1, 6.2, 6.3_ · _属性: P15, P16_

- [ ] 6. 技术列与 PII 分层
- [x] 6.1 `table_whitelist` 增加列分层声明
  - `derive_field_tiers` 纯函数集中派生 `default_fields` / `technical_fields` / `pii_fields`，避免 15 张表手写漂移
  - `staff_members` 的 `email` / `phone` / `user_id` 登记为 PII
  - _Requirements: 7.1, 7.5_ · _属性: P17_

- [x] 6.2 构建器默认列改为业务默认列集
  - `backend/app/routers/query_builder.py:404-410` 的「无 fields 默认全字段」分支改用 `default_fields`
  - 显式请求技术列仍允许，但在 warnings 标注
  - _Requirements: 7.1, 7.3_ · _属性: P17_

- [x] 6.3 schema 下发分层与 PII 按角色过滤
  - `GET /api/query/schema` 下发三层字段；无权角色隐去 PII，显式请求 → 403 `PII_FIELD_FORBIDDEN`
  - _Requirements: 7.2, 7.4_ · _属性: P18_

- [x] 6.4* 列分层属性测试
  - Property 17 / 18 各一条
  - _Requirements: 7.1, 7.4_ · _属性: P17, P18_

- [ ] 7. 稳定分页
- [x] 7.1 新建 `pagination.py`
  - `resolve_sort` / `apply_pagination` / `DEFAULT_SORT_BY_SOURCE` / `TIE_BREAKER_BY_SOURCE`
  - 非法 sort 字段 → 422 `INVALID_SORT_FIELD`；非法方向 → 422 `INVALID_SORT_DIRECTION`
  - _Requirements: 4.2, 4.7_ · _属性: P10_

- [x] 7.2 编排器接入分页步
  - `QueryOrchestrator._run_pipeline` 固定顺序：group → pivot → resolve_sort → 排序 → `total` → 切片
  - `offset` 超 `total` 返回空 rows 且 `total` 不变
  - _Requirements: 4.1, 4.3, 4.4, 4.5_ · _属性: P9, P11, P12_

- [x] 7.3 分页边界双入口 422
  - `custom_query.QueryRequest` 加 pydantic `ge/le`；编排器入口独立校验防绕过 router 直调
  - _Requirements: 4.6_ · _属性: P13_

- [x] 7.4* 分页属性测试
  - Property 9 / 10 / 11 / 12 / 13 各一条
  - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6_ · _属性: P9, P10, P11, P12, P13_

- [ ] 8. 取数器下沉为 business_fetcher
- [x] 8.1 新建 `business_fetchers.py` 注册表
  - 14 个 `_query_*` + 3 个前缀路由（`disclosure_note:` / `consol_unit:` / `workpaper:`）迁入注册表
  - 签名改为接收 `fetch_limit`（预算上限），移除展示 `limit` 预截断
  - _Requirements: 3.7, 4.8_

- [x] 8.2 `total` 语义修正
  - 取数层返回未截断行集或独立 `COUNT`，使 `total` 不再等于截断行数
  - _Requirements: 4.8_ · _属性: P9_

- [ ] 9. 构建器项目作用域
- [x] 9.1 新建 `builder_scope.py`
  - `resolve_builder_scope` / `apply_scope_to_select` / `scope_signature`；复用 `ownership_guard.get_accessible_project_ids`
  - `report_config` 等全局配置表跳过过滤并在 warnings 标注
  - _Requirements: 2.1, 2.2, 2.3_ · _属性: P4_

- [x] 9.2 作用域注入与缓存键隔离
  - `_build_select` 的 WHERE 组装最后一步追加作用域约束（用户 DSL 不可覆盖）
  - 缓存键把 `scope_signature` 替换写死的 `"__query_builder__"`
  - 显式指定不可访问 project_id → 403
  - _Requirements: 2.1, 2.4, 2.5_ · _属性: P4, P5_

- [x] 9.3 构建器改走 `enforce_query_plan` 单一门禁
  - 替换私有 `_resolve_table` / `_resolve_column` 旁路，表/JOIN/算子/聚合统一经服务层门禁
  - _Requirements: 2.6_

- [x] 9.4* 作用域属性测试
  - Property 4 / 5 各一条；含「结果行 project_id 集合 ⊆ 可访问集合」断言
  - _Requirements: 2.1, 2.4_ · _属性: P4, P5_

- [ ] 10. 语句超时与取消
- [x] 10.1 新建 `execution_guard.py`
  - `statement_timeout` 异步上下文管理器（`SET LOCAL`，需确认在事务内）；`QUERY_TIMEOUT_MS` / `EXPORT_TIMEOUT_MS`
  - _Requirements: 6.4_

- [x] 10.2 查询与导出接入超时、取消与导出硬上限
  - `query_builder.execute_query` / `export_excel` / 编排器取数步接入；超时 → 408 `QUERY_TIMEOUT`
  - `CancelledError` 分支显式 `rollback` 后重抛，释放连接
  - 导出达 `EXPORT_ROW_HARD_LIMIT` 时在文件内标注截断
  - _Requirements: 6.4, 6.5, 6.6, 6.7_

- [ ] 11. 执行路径收敛到 adapter
- [x] 11.1 `custom_query.execute_query` 改走 `ExecuteCompatibilityAdapter.execute`
  - 移除 14 个内联 `if/elif` 分发，改由注册表经编排器驱动
  - adapter 在一次请求中恰好调用一次；不留任何 fallback 分支
  - _Requirements: 3.1, 3.2, 3.7_ · _属性: P6_

- [x] 11.2 ACNR 目标解析失败不触达取数器
  - 解析失败 → 4xx `TARGET_UNRESOLVABLE`，取数器调用计数为 0
  - _Requirements: 3.8_

- [x] 11.3* 单一路径属性测试
  - Property 6 一条；含「adapter 抛错时取数器调用计数为 0」断言
  - _Requirements: 3.1, 3.2_ · _属性: P6_

- [ ] 12. 规范错误处理与审计
- [x] 12.1 移除 fail-open except
  - `custom_query.py:1076-1082` 的 `except Exception → 200 {"error": ...}` 改为：`HTTPException` 原样上抛不 rollback；其余 rollback + 500 + `correlation_id`
  - _Requirements: 5.1, 5.2, 5.3_ · _属性: P14_

- [x] 12.2 修正 `working_paper.wp_code` 错误 SQL
  - `custom_query.py:2289` 改为经 `wp_index` JOIN（该表无 `wp_code` 列，现状必抛 `UndefinedColumn`）
  - _Requirements: 5.4_

- [x] 12.3 审计动作可区分
  - 归属拒绝 / 超时 / 预算超限各记可区分 `action`；审计失败不掩盖原始错误
  - _Requirements: 5.5_

- [x] 12.4* 错误契约属性测试
  - Property 14 一条：断言不存在「2xx 且响应体含 error」形态
  - _Requirements: 5.1, 5.3_ · _属性: P14_

- [ ] 13. 模板作用域治理接线
- [x] 13.1 router 模板 CRUD 委托 `TemplateService` 与 `TemplateScopeAdapter`
  - `scope` 读写经 `normalize` / `normalize_record`，legacy `global` 归一为 canonical
  - 团队级 scope 要求配置项目锚点，不复用 `shared_project_ids` 推断
  - _Requirements: 8.1, 8.2_

- [x] 13.2 分享目标逐个鉴权 + 写前回滚
  - `shared_project_ids` 每个元素经 `assert_target_accessible`；任一失败先 `rollback` 再 403，落库记录数为 0
  - _Requirements: 8.3, 8.4_ · _属性: P19_

- [x] 13.3 非 owner 恒不可改删
  - `delete_template`(2089) 移除 admin 例外分支
  - _Requirements: 8.5_ · _属性: P20_

- [x] 13.4 模板执行复用主链路
  - `execute_template` 重新校验目标归属并复用主 execute（即 adapter 路径），不走旁路
  - _Requirements: 8.6, 8.7_

- [x] 13.5* 模板治理属性测试
  - Property 19 / 20 各一条
  - _Requirements: 8.3, 8.4, 8.5_ · _属性: P19, P20_

- [ ] 14. 回写预览与确认端点
- [x] 14.1 新增 `writeback_preview` / `writeback_confirm` 端点
  - 参数名固定 `body` / `request` / `db` / `current_user`（契约测试直调）；`get_visible_project_ids` 以模块级名字引用以便 monkeypatch
  - 接 `WritebackPreviewService.generate` 与 `WritebackConfirmationGate.validate`
  - _Requirements: 9.1_

- [x] 14.2 校验顺序与全有或全无
  - 只读角色 403 → 项目可见性 403 → 逐目标 `assert_target_accessible` 403 → 才调用 generate / write_cell
  - 任一目标失败时 `write_cell` 调用计数为 0
  - _Requirements: 9.2, 9.3, 9.4_ · _属性: P21_

- [x] 14.3 预览预算复用既有常量
  - `MAX_PREVIEW_ITEMS` / `DEFAULT_PREVIEW_TIMEOUT_S` 超限 → 400 `PREVIEW_LIMIT_EXCEEDED`
  - _Requirements: 9.5_

- [x] 14.4* 回写权限属性测试
  - Property 21 一条
  - _Requirements: 9.3, 9.4_ · _属性: P21_

- [ ] 15. 指标树懒加载
- [x] 15.1 后端 `indicators` 支持 depth / branch
  - 默认 `depth=1` 返回骨架；`branch` 参数按分支取子树；`X-Indicators-Schema-Version` 递增至 10
  - _Requirements: 12.1, 12.2, 12.3_ · _属性: P24_

- [x] 15.2 前端 `el-tree` 改 lazy load
  - `CustomQueryDialog.vue` / `CustomQueryTab.vue` 接 `lazy` + `load`；`CustomQueryTab.loadIndicators` 补 sessionStorage 缓存（当前每次挂载全量拉）
  - _Requirements: 12.1, 12.2, 12.4_ · _属性: P24_

- [x] 15.3* 首屏体积收敛判据
  - 可执行判据度量骨架节点数与响应体积相对全量的收敛比，不用目视
  - _Requirements: 12.5_ · _属性: P24_

- [ ] 16. 前端契约对齐
- [x] 16.1 新建 `useQueryBuilderAccess` 统一判据
  - 与后端 `_QUERY_BUILDER_ROLES` 语义对齐，替换 `CustomQueryTab.vue:516` 的 `canDo('edit','project_settings')`
  - 角色不足时入口禁用 + 中文原因提示
  - _Requirements: 11.1, 11.2_ · _属性: P23_

- [x] 16.2 技术列前端分层消费
  - 新建 `components/query/queryFieldTiers.ts` 消费后端下发分层；`AdvancedQueryBuilder.vue` 字段下拉分两组，默认只选业务列；结果表默认隐藏技术列 + 显式开关
  - 不在前端硬编码列名（真源在 `table_whitelist`）
  - _Requirements: 11.3, 7.5_ · _属性: P17_

- [x] 16.3 业务视图接入真实翻页
  - 消费后端 `total` / `limit` / `offset`，替换「可能被截断」提示为可翻页
  - _Requirements: 11.4_

- [x] 16.4 模板 scope 显示与 fail-closed 提交
  - legacy `global` 显示为「公开」；只读角色仅提交私人 scope；有权限时仅提交去重后可编辑项目
  - _Requirements: 11.5, 11.6_

- [x] 16.5 修正测试 mock 陈旧
  - `advancedQueryFrontend.spec.ts:48-51` 的 `usePermissionMatrix` mock 仅返回 `currentRole`，补齐组件实际消费成员，消除 `canDo is not a function` 假红
  - _Requirements: 11.7_

- [x] 16.6* 前后端判据一致属性测试
  - Property 23 一条：5 个角色逐一比对前端 `canUseBuilder` 与后端 403
  - _Requirements: 11.1_ · _属性: P23_

- [ ] 17. Checkpoint — 契约基线转绿
- [x] 17.1 三个后端契约文件全绿
  - `test_advanced_query_hardening_wave012.py` / `test_custom_query_template_scope_hardening.py` / `test_custom_query_templates.py` 由 75 failed → 0 failed
  - 前端 5 failed → 0 failed
  - _Requirements: 全部_

- [x] 17.2 接线判据守卫
  - 断言 7 个模块的 router 引用数 > 0；判据用「唯一消费方 + 真实执行」而非符号 grep
  - _Requirements: 3.1, 3.7, 8.1, 9.1_ · _属性: P6_

- [ ] 18. 真库与浏览器实测
- [x] 18.1 真实 PG 验证
  - `statement_timeout` 生效；构建器结果 project_id 集合受限（当前实测 1000 行覆盖 9 个项目）；移除违规 JOIN 后无笛卡尔积回归
  - _Requirements: 2.1, 6.1, 6.4_

- [x] 18.2 Playwright 实测
  - 三个只读端点未认证 401（当前实测均 200）；构建器默认列无 UUID；业务视图可翻第 2 页；指标树首屏体积收敛（当前 578057 字符 / 3391ms）
  - _Requirements: 1.1, 7.1, 11.4, 12.5_

- [x] 18.3 回归辐射面执行
  - 按 1.2 产出的目标清单执行，不跑全量
  - _Requirements: 全部_

- [ ] 19. 变异检验与收口
- [x] 19.1 变异检验全部锚点
  - 每条新守卫改一字/删一调用/改一常量，要求恰好打红预期测试；四态判别 RED / GREEN / ANCHOR-MISS / WRONG-TEST
  - 脚本支持 `--check-anchors` 只读复现判据
  - _Requirements: 全部_

- [x] 19.2 死代码清理与产物入库核查
  - 删除被 adapter 路径取代的内联分支（不留 DEPRECATED 注释）
  - `git status --porcelain -- <产物清单>` 见 `??` 即登记并 add，防「spec 全绿但产物未入库」
  - _Requirements: 全部_

- [x] 19.3 更新 spec 状态与 INDEX
  - 回写 `.kiro/specs/INDEX.md`；汇总交付与遗留建议
  - _Requirements: 全部_

## Notes

- 标 `*` 的子任务为测试/验证类，按平台约定全部完成，保留 `*` 供 UI 区分。
- 顶层任务（无小数编号）与 Checkpoint 不纳入依赖图。
- 24 条属性逐条一个测试、`max_examples ≥ 100`、标签 `Feature: advanced-query-hardening-wiring-closure, Property N`。
- 不新增表结构变更；如实测发现 V101 / V102 未应用，补幂等 `IF NOT EXISTS` 迁移而非改写既有 V 号。
- 单一真源约束：项目可见性 → `OwnershipGuard`；白名单门禁 → `enforce_query_plan`；预算阈值 → 既有常量；列分层 → `table_whitelist`。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3", "3.1", "4.1", "5.1", "6.1"] },
    { "id": 2, "tasks": ["2.4", "3.2", "4.2", "5.2", "5.3", "6.2", "6.3", "7.1", "9.1", "10.1"] },
    { "id": 3, "tasks": ["3.3", "5.4", "6.4", "7.2", "7.3", "8.1", "9.2", "9.3", "10.2"] },
    { "id": 4, "tasks": ["7.4", "8.2", "9.4", "11.1", "11.2", "13.1", "14.1", "15.1"] },
    { "id": 5, "tasks": ["11.3", "12.1", "12.2", "12.3", "13.2", "13.3", "13.4", "14.2", "14.3", "15.2"] },
    { "id": 6, "tasks": ["12.4", "13.5", "14.4", "15.3", "16.1", "16.2", "16.3", "16.4", "16.5"] },
    { "id": 7, "tasks": ["16.6", "17.1", "17.2"] },
    { "id": 8, "tasks": ["18.1", "18.2", "18.3"] },
    { "id": 9, "tasks": ["19.1", "19.2", "19.3"] }
  ]
}
```
