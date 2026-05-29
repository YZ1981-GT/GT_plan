# Implementation Plan: Phase 5 运营卓越

## 概述

基于需求文档 10 项功能（F1~F10）和设计文档架构决策，按依赖关系拆分为 4 个 Sprint 渐进实施。总工时约 12 天。

- Sprint 1（3 天）：基础设施改造 — F4 路由拆分 + F5 字段选择 + F10 事件类型
- Sprint 2（4 天）：后端服务 — F1 待办聚合 + F2 断裂清单 + F3 完整性报告 + F6 SLA 预警 + F7 批量复核
- Sprint 3（3 天）：前端组件 — F1/F2/F3/F7 前端 + F9 GtRowActions
- Sprint 4（2 天）：代码治理 — F8 金额格式化收口 + 集成测试 + UAT

---

## Sprint 1 — 基础设施改造（3 天）

- [x] 1. F4 router_registry 按业务域拆分
  - [x] 1.1 创建 `backend/app/router_registry/` 包结构
    - 新建目录 `backend/app/router_registry/`
    - 创建 `__init__.py`，保留 `register_all_routers(app)` 统一入口函数
    - 按业务域创建至少 5 个子文件：`workpaper.py` / `report.py` / `collaboration.py` / `system.py` / `cycle_engines.py`
    - 每个子文件包含对应 §N 分组编号注释
    - _Requirements: 4.1, 4.2, 4.4_

  - [x] 1.2 迁移现有路由注册到子文件
    - 将 `router_registry.py` 中 87+ 分组按业务域分配到对应子文件
    - `__init__.py` 中 import 各子模块并在 `register_all_routers()` 中依次调用
    - 确保 main.py 调用方式零改动（向后兼容）
    - _Requirements: 4.2, 4.3, 4.5_

  - [x]* 1.3 编写路由拆分回归测试
    - **Property 8: 路由拆分后路径保持不变**
    - **Validates: Requirements 4.3, 4.6**
    - 文件：`backend/tests/test_router_registry_split.py`
    - 验证拆分前后所有 API path + method 集合完全一致

  - [x] 1.4 删除旧 `router_registry.py` 单文件，更新 import 引用
    - 确认所有现有 pytest 路由测试零回归
    - _Requirements: 4.6_

- [x] 2. F5 API 响应字段选择
  - [x] 2.1 实现字段选择核心模块 `backend/app/core/field_selection.py`
    - 实现 `parse_fields(fields: str | None) -> set[str] | None`
    - 实现 `resolve_columns(Model, requested_fields, default_fields, blocked_fields)` 动态 SQLAlchemy column 投影
    - 定义默认摘要字段集（排除 parsed_data/file_content/raw_html）
    - 定义屏蔽字段列表（安全：不暴露敏感字段）
    - _Requirements: 5.1, 5.2, 5.4, 5.5（非功能：安全）_

  - [x] 2.2 在 WorkpaperList / AdjustmentList / ReviewRecordList 端点接入字段选择
    - 各端点添加 `fields: str | None = Query(None)` 参数
    - 调用 `resolve_columns()` 动态构建 SELECT
    - 无效字段名静默忽略
    - 确保分页/排序/过滤等现有查询参数不受影响
    - _Requirements: 5.1, 5.3, 5.4, 5.6_

  - [x]* 2.3 编写字段选择 property 测试
    - **Property 9: 字段选择过滤正确性**
    - **Property 10: 字段选择与分页/排序正交**
    - **Validates: Requirements 5.1, 5.4, 5.6**
    - 文件：`backend/tests/test_field_selection.py`

- [x] 3. F10 SSE/EventBus 事件类型 TypeScript 约束
  - [x] 3.1 确认后端 EventType 枚举为单一真源
    - 验证 `backend/app/models/audit_platform_schemas.py` 中 `EventType` 枚举（26 个值）
    - 无需新建 `sse_event_types.py`（已有枚举即为真源）
    - _Requirements: 10.4_

  - [x] 3.2 前端定义 SSEEventType 联合类型
    - 创建/更新 `frontend/src/types/sse.ts`
    - 定义 `SSEEventType` union type，镜像后端 `EventType` 枚举全部 26 个值（格式 `domain.action`）
    - 收窄 `SyncEventPayload.event_type` 从 `string` 为 `SSEEventType`
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 3.3 渐进式迁移现有 eventBus 订阅代码
    - 更新现有 `eventBus.on('sse:sync-event', ...)` 回调中的 payload 类型
    - 允许 `as SSEEventType` 断言过渡（不破坏现有代码）
    - 确保 vue-tsc 编译零新增错误
    - _Requirements: 10.5, 10.6_

  - [x]* 3.4 编写 SSE 事件类型编译检查测试
    - 文件：`frontend/src/__tests__/sseEventTypes.spec.ts`
    - 验证 SSEEventType 覆盖所有后端事件名
    - 验证 TypeScript 自动补全可用
    - _Requirements: 10.3, 10.5_

- [x] 4. Sprint 1 Checkpoint
  - 确保所有测试通过，ask the user if questions arise。
  - 验证：所有现有 API 路径不变 / vue-tsc 零新增错误 / 字段选择端点可用

---

## Sprint 2 — 后端服务（4 天）

- [x] 5. F1 待办聚合后端
  - [x] 5.1 实现待办聚合服务 `backend/app/services/my_todo_service.py`
    - 实现紧急度计算逻辑：critical（stale）> high（SLA ≤ 24h）> medium（未解决复核意见）> normal
    - 聚合查询 working_paper + wp_index + review_records + issue_tickets
    - 按紧急度降序排序返回 TodoItem 列表
    - 性能目标：≤ 500ms（50 底稿规模）
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 5.2 实现待办聚合路由 `backend/app/routers/my_todo.py`
    - `GET /api/projects/{project_id}/my-todo`
    - 返回 `MyTodoResponse`（items + total）
    - 注册到 router_registry（新 §N 编号）
    - _Requirements: 1.1, 1.4_

  - [x]* 5.3 编写待办聚合 property 测试
    - **Property 1: 待办紧急度排序正确性**
    - **Property 2: 待办响应字段完整性**
    - **Validates: Requirements 1.1, 1.2, 1.4**
    - 文件：`backend/tests/test_my_todo_aggregation.py`

- [x] 6. F2 跨循环断裂清单后端
  - [x] 6.1 实现断裂清单服务 `backend/app/services/cross_cycle_breakage_service.py`
    - 读取 cross_wp_references（400 条）引用定义
    - 运行时 JOIN working_paper + wp_index 表判断 target 是否断裂：target_missing（项目内无对应 wp_code）或 target_stale（prefill_stale=true）
    - 按 severity 降序排列（blocking > required > warning > recommended > info，5 级）
    - 计算统计摘要（各 severity 级别条数）
    - _Requirements: 2.2, 2.3, 2.6_

  - [x] 6.2 实现断裂清单路由 `backend/app/routers/cross_cycle_breakage.py`
    - `GET /api/projects/{project_id}/cross-cycle-breakage`
    - 返回 `BreakageListResponse`（items + summary）
    - 性能目标：≤ 1s（400 条 CWR 规模）
    - _Requirements: 2.2, 2.4, 2.6_

  - [x]* 6.3 编写断裂清单 property 测试
    - **Property 3: 断裂清单过滤正确性**
    - **Property 4: 断裂清单 severity 排序**
    - **Property 5: 断裂统计摘要一致性**
    - **Validates: Requirements 2.2, 2.3, 2.6**
    - 文件：`backend/tests/test_cross_cycle_breakage.py`

- [x] 7. F3 归档前完整性自检报告后端
  - [x] 7.1 实现完整性报告服务 `backend/app/services/archive_completeness_service.py`
    - 四类检查：缺失底稿 / 未签字底稿 / 未解决复核意见 / stale 底稿
    - 每类计算 count + items 列表 + is_blocking 标记
    - `can_proceed = True` 当且仅当无 blocking 类别有 count > 0
    - _Requirements: 3.2, 3.3, 3.4, 3.5_

  - [x] 7.2 实现完整性报告路由 `backend/app/routers/archive_completeness.py`
    - `GET /api/projects/{project_id}/archive-completeness-report`
    - 返回 `CompletenessReportResponse`（categories + can_proceed + generated_at）
    - _Requirements: 3.1, 3.2_

  - [x]* 7.3 编写完整性报告 property 测试
    - **Property 6: 完整性报告结构不变量**
    - **Property 7: 归档阻断逻辑**
    - **Validates: Requirements 3.2, 3.3, 3.4, 3.5**
    - 文件：`backend/tests/test_archive_completeness_report.py`

- [x] 8. F6 SLA 超时前置预警
  - [x] 8.1 扩展 sla_worker 添加前置预警逻辑
    - 在 `sla_worker.run()` 主循环中新增 `_check_prewarning()` 分支
    - 查询 IssueTicket.due_at 在 (now, now+24h] 的未完成问题单 → 黄色预警
    - 查询 IssueTicket.due_at 在 (now, now+8h] 的未完成问题单 → 橙色预警
    - 幂等去重：Redis key `sla:prewarning:{ticket_id}:{level}` TTL=24h
    - _Requirements: 6.1, 6.2, 6.5_

  - [x] 8.2 预警通知写入 NotificationCenter
    - 复用现有 Notification 模型，type='sla_prewarning'
    - 通知内容包含：问题单编号、剩余时间、责任人（owner_id）、关联底稿
    - 推送到对应项目经理
    - 预警记录写入 audit_log（可追溯）
    - _Requirements: 6.3, 6.4（非功能：可观测性）_

  - [x] 8.3 实现预警自动解决逻辑
    - 问题单状态变为 resolved/closed 后标记对应预警为"已解决"
    - _Requirements: 6.6_

  - [x]* 8.4 编写 SLA 预警 property 测试
    - **Property 11: SLA 预警级别分类正确性**
    - **Property 12: SLA 预警幂等性**
    - **Property 13: SLA 预警自动解决**
    - **Validates: Requirements 6.1, 6.2, 6.5, 6.6**
    - 文件：`backend/tests/test_sla_prewarning.py`

- [x] 9. F7 批量复核通过后端
  - [x] 9.1 实现批量复核路由 `backend/app/routers/batch_review.py`
    - `POST /api/projects/{project_id}/batch-review-pass`
    - 请求体：`BatchReviewRequest`（wp_ids + comment，默认"已审阅，无异议"）
    - RBAC：仅 manager/partner/admin 角色可调用
    - _Requirements: 7.1, 7.3（非功能：安全）_

  - [x] 9.2 实现批量复核事务逻辑
    - 单事务中遍历所有选中底稿
    - 状态不允许通过的跳过并记录原因（如未提交复核）
    - 返回 `BatchReviewResult`（success_count + skipped_count + skipped_items）
    - 操作结果写入 audit_log（含成功/跳过明细）
    - _Requirements: 7.4, 7.5, 7.6（非功能：事务性、可观测性）_

  - [x]* 9.3 编写批量复核 property 测试
    - **Property 14: 批量复核事务原子性**
    - **Property 15: 批量复核跳过 + 计数不变量**
    - **Validates: Requirements 7.4, 7.5, 7.6**
    - 文件：`backend/tests/test_batch_review_pass.py`

- [x] 10. Sprint 2 Checkpoint
  - 确保所有测试通过，ask the user if questions arise。
  - 验证：6 个新端点可用 / SLA worker 预警逻辑正确 / 批量复核 RBAC 生效

---

## Sprint 3 — 前端组件（3 天）

- [x] 11. F1 待办聚合前端
  - [x] 11.1 实现 MyTodoCard 组件
    - 创建 `frontend/src/components/dashboard/MyTodoCard.vue`
    - 调用 `GET /api/projects/{project_id}/my-todo` 获取待办列表
    - 显示：底稿编号、名称、所属循环、紧急度标签（红/橙/黄/灰）、最后更新时间
    - 空状态显示"暂无待办，保持好状态 ✓"
    - 点击待办项跳转到对应底稿编辑器
    - _Requirements: 1.4, 1.5, 1.6_

  - [x]* 11.2 编写 MyTodoCard 前端测试
    - 文件：`frontend/src/__tests__/MyTodoCard.spec.ts`
    - 测试：列表渲染 / 紧急度颜色映射 / 空状态 / 点击跳转
    - _Requirements: 1.4, 1.5, 1.6_

- [x] 12. F2 跨循环断裂清单前端
  - [x] 12.1 在 ConsistencyDashboard 新增"跨循环断裂清单"Tab
    - 修改 `ConsistencyDashboard.vue`，新增 Tab
    - 调用 `GET /api/projects/{project_id}/cross-cycle-breakage`
    - 显示断裂统计摘要（blocking N / warning N / info N）
    - 列表显示：ref_id、source_wp_code、target_wp_code、severity、断裂原因、最后检查时间
    - 点击断裂记录跳转到 source 底稿
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x]* 12.2 编写 CrossCycleBreakageTab 前端测试
    - 文件：`frontend/src/__tests__/CrossCycleBreakageTab.spec.ts`
    - 测试：Tab 切换 / 列表渲染 / severity 排序 / 统计摘要 / 点击跳转
    - _Requirements: 2.1, 2.4, 2.5_

- [x] 13. F3 归档前完整性自检报告前端
  - [x] 13.1 在 ArchiveWizard 第一步集成完整性报告面板
    - 修改 `ArchiveWizard.vue`，在就绪检查步骤自动调用完整性报告 API
    - 显示四类检查项：数量统计 + 详细列表（底稿编号/名称/责任人/状态）
    - blocking 项高亮显示，阻断归档流程
    - 无 blocking 项时允许继续
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 13.2 实现报告 PDF 导出功能
    - 添加"导出 PDF"按钮
    - 使用浏览器 print API 或 html2canvas 生成 PDF
    - _Requirements: 3.6_

  - [x]* 13.3 编写 ArchiveCompletenessReport 前端测试
    - 文件：`frontend/src/__tests__/ArchiveCompletenessReport.spec.ts`
    - 测试：报告面板渲染 / blocking 高亮 / 阻断逻辑 / 空报告
    - _Requirements: 3.1, 3.4, 3.5_

- [x] 14. F7 批量复核通过前端
  - [x] 14.1 在 ReviewWorkbench 添加批量操作 UI
    - 添加 checkbox 多选列
    - 添加"批量通过"按钮（勾选 ≥ 1 个时启用）
    - 弹出确认弹窗：显示选中数量 + 默认意见"已审阅，无异议"（可修改）
    - 调用 `POST /api/projects/{project_id}/batch-review-pass`
    - 显示结果摘要：成功 N 个 / 跳过 N 个（含原因）
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 7.6_

  - [x]* 14.2 编写批量复核前端测试
    - 测试：多选 / 确认弹窗 / 默认意见 / 结果摘要
    - _Requirements: 7.2, 7.6_

- [x] 15. F9 GtRowActions 通用组件
  - [x] 15.1 实现 GtRowActions 组件
    - 创建 `frontend/src/components/common/GtRowActions.vue`
    - Props：`actions: RowAction[]`（key/label/icon/priority/disabled/danger/hidden）+ `maxVisible: number`（默认 2）
    - 按 priority 升序排列，前 maxVisible 个外露，其余收入 el-dropdown
    - el-dropdown 菜单项支持图标+文字+禁用状态
    - Emit：`action(key: string)`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 15.2 在 3 个高频表格页面接入 GtRowActions
    - WorkpaperList：替换现有行操作按钮
    - IssueTicketList：替换现有行操作按钮
    - ReviewWorkbench：替换现有行操作按钮
    - _Requirements: 9.6_

  - [x]* 15.3 编写 GtRowActions 组件测试
    - **Property 16: GtRowActions 可见性逻辑**
    - **Validates: Requirements 9.2, 9.3, 9.5**
    - 文件：`frontend/src/__tests__/GtRowActions.spec.ts`
    - 测试：0/1/2/5 个按钮 / 含 hidden / priority 排序 / dropdown 渲染

- [x] 16. Sprint 3 Checkpoint
  - 确保所有测试通过，ask the user if questions arise。
  - 验证：前端组件渲染正确 / 与后端 API 联调通过 / vue-tsc 零新增错误

---

## Sprint 4 — 代码治理 + 集成测试 + UAT（2 天）

- [x] 17. F8 金额格式化统一收口
  - [x] 17.1 扫描并替换非标金额格式化调用
    - grep 全仓库 `toFixed` 和 `toLocaleString` 在 `.vue` / `.ts` 文件中的调用
    - 将金额相关的 toFixed/toLocaleString 替换为 `fmtAmountUnit` / `displayPrefs.fmt()`
    - 保留非金额用途的 toFixed（如百分比格式化）
    - 确保替换后页面金额显示效果不变
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 17.2 新增 ESLint 自定义规则
    - 创建 ESLint 规则：禁止在 `.vue` / `.ts` 文件中直接调用 `toFixed()` 用于金额格式化
    - 支持 `// eslint-disable-next-line` 豁免（非金额用途）
    - 确保 `formatters.ts` 内部实现不受规则影响
    - _Requirements: 8.4, 8.5_

- [x] 18. 集成测试 + 端到端验证
  - [x] 18.1 F6 SLA 预警集成测试
    - 验证 sla_worker 完整循环：检测 → 预警生成 → 通知推送 → 自动解决
    - 验证幂等性（多次运行不重复通知）
    - _Requirements: 6.1~6.6_

  - [x] 18.2 F1/F2/F3 数据聚合集成测试
    - 验证待办聚合端点与真实数据联调
    - 验证断裂清单与 cross_wp_references 数据一致
    - 验证完整性报告与 ArchiveWizard gate_engine 协同
    - _Requirements: 1.1~1.6, 2.1~2.6, 3.1~3.6_

  - [x] 18.3 F5 字段选择性能验证
    - 验证排除 parsed_data 后响应体积减少 ≥ 60%
    - 验证分页/排序/过滤与字段选择正交
    - _Requirements: 5.5, 5.6_

- [x] 19. Final Checkpoint — 全量回归
  - 确保所有测试通过，ask the user if questions arise。
  - 运行 `python -m pytest backend/tests/` 全量后端测试
  - 运行前端 vitest 全量测试
  - 运行 vue-tsc 编译检查零新增错误
  - 确认所有现有功能零回归

---

## UAT 验收清单

| # | 功能 | 验收场景 | 预期结果 |
|---|------|----------|----------|
| 1 | F1 待办聚合 | 审计助理登录，查看待办卡片 | 按紧急度排序显示负责底稿，点击可跳转 |
| 2 | F2 断裂清单 | 质控人员打开 ConsistencyDashboard 断裂 Tab | 显示断裂记录 + 统计摘要，按 severity 排序 |
| 3 | F3 完整性报告 | 合伙人进入 ArchiveWizard 第一步 | 自动生成 4 类自检报告，blocking 项阻断归档 |
| 4 | F4 路由拆分 | 开发人员访问任意 API 端点 | 所有 API 路径与拆分前完全一致 |
| 5 | F5 字段选择 | 前端调用 WorkpaperList API 带 ?fields= | 响应仅含指定字段，体积减少 ≥ 60% |
| 6 | F6 SLA 预警 | 问题单距 SLA 截止 ≤ 24h | 项目经理收到黄色/橙色预警通知 |
| 7 | F7 批量复核 | 经理勾选 5 个底稿点击"批量通过" | 单事务更新，显示成功/跳过摘要 |
| 8 | F8 格式化收口 | grep 全仓库 toFixed/toLocaleString | 仅出现在 formatters.ts 内部 |
| 9 | F9 行操作按钮 | 打开 WorkpaperList 表格 | 操作 > 2 个时收入"更多"下拉菜单 |
| 10 | F10 事件类型 | 运行 vue-tsc 编译 | 零新增错误，SSEEventType 自动补全可用 |

---

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 每个 Sprint 末尾有 Checkpoint 确保增量验证
- Property tests 验证通用正确性，unit tests 验证具体场景和边界
- F4 路由拆分是 Sprint 1 首要任务，后续新路由（F1/F2/F3/F6/F7）直接注册到拆分后的子文件
- F5 字段选择是通用中间件，Sprint 2 的列表端点可直接复用
- F10 事件类型约束是编译期保障，Sprint 1 完成后后续开发即受益

### Sprint 0 偏差修正（已回灌到三件套）

| 偏差项 | 修正内容 |
|--------|----------|
| F2 CWR 无 `is_broken` 字段 | 断裂检测改为运行时 JOIN working_paper 表（target_missing / target_stale） |
| F6 SLA 监控对象 | 从"底稿 deadline"修正为"IssueTicket.due_at"（working_paper 无 deadline 字段） |
| F10 SSE 事件名 | 从臆造 10 个修正为镜像后端 EventType 枚举 26 个值（格式 `domain.action`） |
| F4 路由数量 | 从 87 修正为 123 个 `app.include_router` 调用 |
| F8 toFixed 遗漏 | 金额相关仅 ~5 处（大部分是百分比/文件大小/耗时），工作量远小于预期 |
| CWR severity | 从 3 级修正为 5 级（blocking/required/warning/recommended/info） |
