# Requirements Document — Phase 5 运营卓越

## 一、变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-05-22 | 初始起草，基于《平台全局建议书》剩余 ~60 项中精选 10 项高 ROI |

## 依赖矩阵

| 依赖项 | 类型 | 状态 |
|--------|------|------|
| Phase 1~4 specs (94 tasks) | 前置 | ✅ 已完成 |
| router_registry.py (87+ 分组) | 后端 | ✅ 已有（待拆分） |
| cross_wp_references 400 条 | 数据 | ✅ 已有 |
| ConsistencyDashboard.vue | 前端 | ✅ 已有 |
| ArchiveWizard.vue | 前端 | ✅ 已有 |
| NotificationCenter.vue | 前端 | ✅ 已有 |
| sla_worker.py | 后端 Worker | ✅ 已有 |
| eventBus.ts (mitt + Events 类型) | 前端 | ✅ 已有 |
| fmtAmountUnit (formatters.ts) | 前端 | ✅ 已有 |
| WorkpaperList.vue | 前端 | ✅ 已有 |
| Element Plus (el-dropdown) | 前端 UI | ✅ 已有 |
| displayPrefs store | 前端 | ✅ 已有 |

---

## 二、为什么做（业务痛点）

### 2.1 审计助理无"今日待办"聚合入口（A-1）
- **痛点**：助理需在 WorkpaperList 逐个找自己负责的底稿，无法一眼看到"今天该做什么"
- **影响角色**：审计助理（日常高频操作者）
- **技术根因**：无按人员+紧急度聚合的待办视图；stale 底稿散落在各循环无优先排序

### 2.2 跨循环断裂清单无汇总视图（Q-2）
- **痛点**：400 条 cross_wp_references 分散在各循环，质控人员无法一眼看到"哪些跨循环引用断裂"
- **影响角色**：质控人员（风险把控）
- **技术根因**：ConsistencyDashboard 仅展示循环内一致性，缺少跨循环断裂专项 Tab
- **Sprint 0 实测**：CWR 400 条，severity 分布 blocking=75 / warning=202 / info=75 / recommended=19 / required=29；JSON 无 `is_broken` 字段，断裂检测需运行时 JOIN working_paper 表判断 target 是否存在+是否 stale

### 2.3 归档前无完整性自检报告（P-5）
- **痛点**：ArchiveWizard 流程中无"归档前自检报告"，合伙人签字前不知道是否有遗漏
- **影响角色**：合伙人（签字决策）、项目经理（质量把关）
- **技术根因**：ArchiveWizard 仅做 gate_engine 门禁检查，无结构化完整性报告输出

### 2.4 router_registry.py 单文件 87+ 分组难维护（MT-2）
- **痛点**：新增路由需翻阅大量代码找到正确位置，87+ 个分组在单文件中难以定位
- **影响角色**：开发人员（维护效率）
- **技术根因**：所有路由注册集中在 `register_all_routers()` 单函数，无业务域拆分

### 2.5 API 响应体积过大（FE-2）
- **痛点**：WorkpaperList 等列表 API 返回全量字段（含 parsed_data MB 级 JSON），前端仅需 id/wp_code/status 等摘要字段
- **影响角色**：所有用户（页面加载慢）
- **技术根因**：列表端点无字段选择机制，始终返回完整模型序列化

### 2.6 SLA 超时预警不够前置（M-4）
- **痛点**：sla_worker 检测超时后才告警，缺乏"即将超时"的黄色预警，项目经理无法提前干预
- **影响角色**：项目经理（进度管控）
- **技术根因**：sla_worker 仅检查 `deadline < now()`，无 T-24h/T-8h 前置预警逻辑
- **Sprint 0 实测**：SLA 超时检查对象是 `IssueTicket`（问题单），字段 `due_at`（非 working_paper）；sla_worker 每 30s 循环调用 `issue_ticket_service.check_sla_timeout(db)`；working_paper 表无 deadline 字段 → F6 预警目标是问题单而非底稿

### 2.7 批量复核通过缺乏效率工具（RV-4）
- **痛点**：经理复核 20 个底稿时，对无问题的底稿需逐个点"通过"，重复操作多
- **影响角色**：项目经理（复核效率）
- **技术根因**：ReviewWorkbench 仅支持单底稿操作，无批量通过+统一意见功能

### 2.8 金额格式化入口分散（G-3）
- **痛点**：大部分用 `displayPrefs.fmt()`，但仍有个别组件自定义 toFixed/toLocaleString，导致格式不一致
- **影响角色**：所有用户（数据展示一致性）
- **技术根因**：无 ESLint 规则强制收口，历史代码遗留

### 2.9 表格行操作按钮过多（UI-6）
- **痛点**：部分表格每行 4-5 个操作按钮，视觉杂乱，挤压数据列宽
- **影响角色**：所有用户（视觉体验）
- **技术根因**：无统一的"超过 N 个按钮收入更多下拉"规范组件

### 2.10 SSE/EventBus 事件类型缺乏编译期约束（FE-7）
- **痛点**：eventBus 已有 Events 类型映射，但 SSE 服务端推送的事件名为运行时字符串，前后端事件名不同步时无编译期报错
- **影响角色**：开发人员（类型安全）
- **技术根因**：后端 SSE 事件名为 Python 字符串常量，前端 `sse:sync-event` payload 的 `event_type` 字段无枚举约束
- **Sprint 0 实测**：后端 `EventType` 枚举已有 26 个值（`backend/app/models/audit_platform_schemas.py`），格式为 `domain.action`（如 `workpaper.saved` / `adjustment.created` / `materiality.changed`）；前端 SSEEventType 应与此枚举一一对应

---

## 三、范围边界

### 必做（In Scope）

| 编号 | 功能项 | 来源 |
|------|--------|------|
| F1 | 我的待办聚合入口（今日待办卡片） | A-1 |
| F2 | 跨循环断裂清单 Tab | Q-2 |
| F3 | 归档前完整性自检报告 | P-5 |
| F4 | router_registry 按业务域拆分 | MT-2 |
| F5 | API 响应字段选择（?fields=...） | FE-2 |
| F6 | SLA 超时前置预警（T-24h/T-8h） | M-4 |
| F7 | 批量复核通过 | RV-4 |
| F8 | 金额格式化统一收口 | G-3 |
| F9 | 表格行操作按钮"更多"下拉菜单 | UI-6 |
| F10 | SSE/EventBus 事件类型 TypeScript 约束 | FE-7 |

### 排除（Out of Scope）

- 不涉及 GraphQL 引入（仅实现轻量 ?fields= 查询参数方案）
- 不涉及 sla_worker 架构重写（仅扩展预警分支）
- 不涉及 ReviewWorkbench 整体重构（仅新增批量通过入口）
- 不涉及 eventBus 替换为其他方案（保留 mitt，仅增强类型）
- 不涉及 router_registry 路由路径变更（仅文件拆分，API 路径不变）
- 不涉及前端 SSE 重连机制改造（Phase 1 已有指数退避）

---

## 四、功能需求（EARS 范式）

### F1 我的待办聚合入口

**User Story:** 作为审计助理，我希望有一个"今日待办"卡片，按紧急度排序显示我负责的底稿，以便快速定位当天工作重点。

#### 验收标准

1. WHEN 审计助理登录系统，THE 待办聚合服务 SHALL 返回该用户负责的所有未完成底稿，按紧急度降序排列
2. THE 紧急度排序规则 SHALL 为：stale 底稿优先 > SLA 即将超时 > 有未解决复核意见 > 普通待办
3. WHEN 底稿状态变更（stale 传播/复核意见新增/SLA 临近），THE 待办列表 SHALL 在下次刷新时反映最新状态
4. THE 待办卡片 SHALL 显示：底稿编号、底稿名称、所属循环、紧急度标签（红/橙/黄/灰）、最后更新时间
5. WHEN 用户点击待办项，THE 系统 SHALL 跳转到对应底稿编辑器
6. IF 用户无任何待办项，THE 系统 SHALL 显示"暂无待办，保持好状态 ✓"空状态

### F2 跨循环断裂清单

**User Story:** 作为质控人员，我希望在 ConsistencyDashboard 看到"跨循环断裂清单"Tab，按严重度排序，以便快速定位需要修复的跨循环引用。

#### 验收标准

1. THE ConsistencyDashboard SHALL 新增"跨循环断裂清单"Tab
2. WHEN 用户切换到断裂清单 Tab，THE 系统 SHALL 加载所有 cross_wp_references 中 target 底稿不存在（项目内无对应 wp_code）或 target 底稿 `prefill_stale=true` 的记录（运行时 JOIN working_paper 表判断）
3. THE 断裂清单 SHALL 按 severity 降序排列（blocking > warning > info）
4. THE 每条断裂记录 SHALL 显示：ref_id、source_wp_code、target_wp_code、severity、断裂原因（missing/stale）、最后检查时间
5. WHEN 用户点击某条断裂记录，THE 系统 SHALL 跳转到 source 底稿对应位置
6. THE 系统 SHALL 显示断裂统计摘要：blocking N 条 / warning N 条 / info N 条

### F3 归档前完整性自检报告

**User Story:** 作为合伙人，我希望在 ArchiveWizard 归档前看到完整性自检报告，以便确认无遗漏后再签字归档。

#### 验收标准

1. WHEN 用户进入 ArchiveWizard 第一步（就绪检查），THE 系统 SHALL 自动生成完整性自检报告
2. THE 自检报告 SHALL 包含四类检查项：缺失底稿清单、未签字底稿清单、未解决复核意见清单、stale 底稿清单
3. THE 每类检查项 SHALL 显示：数量统计 + 详细列表（底稿编号/名称/责任人/状态）
4. IF 存在 blocking 级别的缺失（如必填底稿缺失或未签字），THE 系统 SHALL 阻断归档流程并高亮显示阻断项
5. WHEN 自检报告无 blocking 项时，THE 系统 SHALL 允许用户继续归档流程
6. THE 自检报告 SHALL 支持导出为 PDF（供合伙人留档）

### F4 router_registry 按业务域拆分

**User Story:** 作为开发人员，我希望 router_registry 按业务域拆分为多个文件，以便快速定位和维护路由注册。

#### 验收标准

1. THE router_registry.py SHALL 拆分为至少 5 个独立文件（按业务域：workpaper / report / collaboration / system / cycle_engines）
2. THE 拆分后 SHALL 保留 `register_all_routers(app)` 统一入口函数（向后兼容 main.py 调用）
3. THE 拆分后所有 API 路径 SHALL 与拆分前完全一致（零 breaking change）
4. THE 每个子文件 SHALL 包含清晰的业务域注释和路由分组编号（§N）
5. IF 新增路由，THE 开发人员 SHALL 仅需在对应业务域文件中追加（无需翻阅全文件）
6. THE 拆分后 SHALL 通过所有现有路由相关测试（零回归）

### F5 API 响应字段选择

**User Story:** 作为前端开发者，我希望列表 API 支持 `?fields=id,wp_code,status` 字段选择，以便减少响应体积、加速页面加载。

#### 验收标准

1. THE WorkpaperList API SHALL 支持 `?fields=` 查询参数，仅返回指定字段
2. WHEN `?fields=` 参数缺失，THE API SHALL 返回默认摘要字段集（排除 parsed_data 等大字段）
3. THE 字段选择 SHALL 支持至少以下列表端点：WorkpaperList / AdjustmentList / ReviewRecordList
4. IF 请求的字段名不存在，THE API SHALL 忽略无效字段名（不报错）
5. THE 响应体积 SHALL 在排除 parsed_data 后减少至少 60%（对含 parsed_data 的底稿列表）
6. THE 字段选择 SHALL 不影响分页、排序、过滤等现有查询参数

### F6 SLA 超时前置预警

**User Story:** 作为项目经理，我希望在 SLA 超时前 24 小时和 8 小时收到预警通知，以便提前干预避免超时。

#### 验收标准

1. WHEN 问题单（IssueTicket）距 `due_at` 截止时间 ≤ 24h 且 > 8h，THE sla_worker SHALL 生成黄色预警通知
2. WHEN 问题单距 `due_at` 截止时间 ≤ 8h，THE sla_worker SHALL 生成橙色预警通知
3. THE 预警通知 SHALL 推送到对应项目经理的 NotificationCenter
4. THE 预警通知 SHALL 包含：问题单编号、剩余时间、责任人（owner_id）、关联底稿
5. THE sla_worker SHALL 对同一问题单的同级预警仅发送一次（幂等，不重复推送）
6. WHEN 问题单在预警后状态变为 resolved/closed，THE 系统 SHALL 自动标记预警为"已解决"

### F7 批量复核通过

**User Story:** 作为项目经理，我希望勾选多个底稿后一键通过复核并附统一意见"已审阅，无异议"，以便提升复核效率。

#### 验收标准

1. THE ReviewWorkbench SHALL 支持多选底稿（checkbox 勾选）
2. WHEN 用户勾选 ≥ 1 个底稿并点击"批量通过"，THE 系统 SHALL 弹出确认弹窗显示选中数量和默认意见
3. THE 默认复核意见 SHALL 为"已审阅，无异议"，用户可修改
4. WHEN 用户确认批量通过，THE 后端 SHALL 在单个事务中更新所有选中底稿的复核状态为"通过"
5. IF 批量操作中任一底稿状态不允许通过（如未提交复核），THE 系统 SHALL 跳过该底稿并在结果中报告
6. THE 批量操作完成后 SHALL 显示结果摘要：成功 N 个 / 跳过 N 个（含原因）

### F8 金额格式化统一收口

**User Story:** 作为开发人员，我希望全仓库金额格式化统一收口到 `fmtAmountUnit`，消除 toFixed/toLocaleString 遗漏，以便保证金额显示一致性。

#### 验收标准

1. THE 代码库 SHALL 消除所有非 `fmtAmountUnit` / `displayPrefs.fmt()` 的金额格式化调用
2. WHEN grep 全仓库 `toFixed` 和 `toLocaleString`，THE 结果 SHALL 仅出现在 `formatters.ts` 内部实现中（非业务组件）
3. THE 迁移 SHALL 不改变任何页面的金额显示效果（视觉回归零差异）
4. THE 系统 SHALL 新增 ESLint 自定义规则：禁止在 `.vue` / `.ts` 文件中直接调用 `toFixed()` 用于金额格式化
5. IF 存在合理的非金额 toFixed 用途（如百分比格式化），THE ESLint 规则 SHALL 支持 `// eslint-disable-next-line` 豁免

### F9 表格行操作按钮"更多"下拉菜单

**User Story:** 作为用户，我希望表格行操作按钮超过 2 个时自动收入"更多"下拉菜单，以便减少视觉杂乱、增加数据列宽。

#### 验收标准

1. THE 系统 SHALL 提供 `GtRowActions` 通用组件，接收操作列表并自动处理显隐逻辑
2. WHEN 操作按钮 ≤ 2 个，THE 组件 SHALL 直接平铺显示所有按钮
3. WHEN 操作按钮 > 2 个，THE 组件 SHALL 仅显示前 2 个常用按钮 + "更多"下拉菜单（el-dropdown）
4. THE "更多"下拉菜单 SHALL 使用 Element Plus el-dropdown 组件，菜单项支持图标+文字+禁用状态
5. THE 组件 SHALL 支持通过 props 配置哪些按钮外露（priority 排序）
6. THE 系统 SHALL 在至少 3 个高频表格页面（WorkpaperList / IssueTicketList / ReviewWorkbench）接入 GtRowActions

### F10 SSE/EventBus 事件类型 TypeScript 约束

**User Story:** 作为前端开发者，我希望 SSE 推送的事件类型与 EventBus 的 Events 类型映射完全对齐，编译期即可检查事件名拼写错误。

#### 验收标准

1. THE 系统 SHALL 定义 `SSEEventType` 枚举（或 union type），列举所有后端 SSE 推送的 event_type 值
2. THE `SyncEventPayload.event_type` 字段 SHALL 从 `string` 收窄为 `SSEEventType` 联合类型
3. WHEN 开发者在 `eventBus.on('sse:sync-event', ...)` 回调中使用 `payload.event_type` 时，THE TypeScript 编译器 SHALL 提供自动补全
4. THE 后端 SHALL 导出 `SSE_EVENT_TYPES` 常量列表（Python），前端 `SSEEventType` 与之一一对应
5. IF 前后端事件名不同步（如后端新增事件未同步到前端类型），THE 开发者 SHALL 在 CI 类型检查中发现（vue-tsc 报错）
6. THE 类型收窄 SHALL 不破坏现有 eventBus 订阅代码（渐进式迁移，允许 `as SSEEventType` 断言过渡）

---

## 五、非功能需求

| 维度 | 要求 | 适用功能 |
|------|------|----------|
| 性能 | F1 待办聚合查询 ≤ 500ms（单用户 50 底稿规模） | F1 |
| 性能 | F2 断裂清单加载 ≤ 1s（400 条 CWR 规模） | F2 |
| 性能 | F5 字段选择后列表 API 响应体积减少 ≥ 60% | F5 |
| 兼容性 | F4 拆分后所有现有 pytest 路由测试零回归 | F4 |
| 兼容性 | F8 金额格式化迁移后所有页面视觉零差异 | F8 |
| 兼容性 | F10 类型收窄后 vue-tsc 零新增错误 | F10 |
| 可观测性 | F6 预警发送记录写入 audit_log（可追溯） | F6 |
| 可观测性 | F7 批量操作结果写入 audit_log（含成功/跳过明细） | F7 |
| 安全 | F7 批量复核通过仅限 manager/partner/admin 角色 | F7 |
| 安全 | F5 字段选择不暴露敏感字段（如 password_hash） | F5 |
| 幂等性 | F6 同一底稿同级预警 24h 内仅发送一次 | F6 |
| 事务性 | F7 批量操作在单事务中执行，状态不允许的跳过（非全回滚），仅 DB 错误时回滚 | F7 |

---

## 六、测试矩阵

| 功能 | 单元测试 | PBT | 集成测试 | 前端 vitest | UAT |
|------|----------|-----|----------|-------------|-----|
| F1 待办聚合 | 排序算法 + 紧急度计算 | 紧急度排序稳定性 | API 端点 + 数据聚合 | 待办卡片渲染 | 助理登录看到待办 |
| F2 断裂清单 | severity 排序 + 断裂检测 | — | ConsistencyDashboard Tab | Tab 切换 + 列表渲染 | 质控看到断裂项 |
| F3 完整性报告 | 四类检查逻辑 | — | ArchiveWizard 集成 | 报告面板渲染 | 合伙人归档前看到报告 |
| F4 路由拆分 | — | — | register_all_routers 回归 | — | 所有 API 路径不变 |
| F5 字段选择 | 字段过滤逻辑 | — | 列表端点 ?fields= | — | 列表加载速度提升 |
| F6 SLA 预警 | T-24h/T-8h 判断逻辑 | 时间边界 property | sla_worker 集成 | 通知卡片渲染 | 经理收到预警 |
| F7 批量复核 | 状态校验 + 事务逻辑 | — | 批量 API 端点 | 批量操作 UI | 经理批量通过 |
| F8 格式化收口 | — | — | — | 金额显示回归 | 页面金额一致 |
| F9 行操作按钮 | — | — | — | GtRowActions 组件 | 按钮收纳正确 |
| F10 事件类型 | — | — | — | 类型编译检查 | vue-tsc 零错误 |

### 测试文件清单（预期）

| 文件 | 覆盖功能 |
|------|----------|
| `backend/tests/test_my_todo_aggregation.py` | F1 |
| `backend/tests/test_cross_cycle_breakage.py` | F2 |
| `backend/tests/test_archive_completeness_report.py` | F3 |
| `backend/tests/test_router_registry_split.py` | F4 |
| `backend/tests/test_field_selection.py` | F5 |
| `backend/tests/test_sla_prewarning.py` | F6 |
| `backend/tests/test_batch_review_pass.py` | F7 |
| `frontend/src/__tests__/MyTodoCard.spec.ts` | F1 |
| `frontend/src/__tests__/CrossCycleBreakageTab.spec.ts` | F2 |
| `frontend/src/__tests__/ArchiveCompletenessReport.spec.ts` | F3 |
| `frontend/src/__tests__/GtRowActions.spec.ts` | F9 |
| `frontend/src/__tests__/sseEventTypes.spec.ts` | F10 |

---

## 七、成功判据

| 指标 | 目标 |
|------|------|
| F1 待办聚合响应时间 | ≤ 500ms |
| F2 断裂清单覆盖 CWR 数 | 400 条全量扫描 |
| F3 自检报告检查维度 | 4 类（缺失/未签字/未解决意见/stale） |
| F4 拆分后子文件数 | ≥ 5 个业务域文件 |
| F5 响应体积缩减 | ≥ 60%（排除 parsed_data） |
| F6 预警级别 | 2 级（黄色 T-24h / 橙色 T-8h） |
| F7 批量操作事务性 | 单事务，全成功或全回滚 |
| F8 toFixed/toLocaleString 遗漏数 | 0（仅 formatters.ts 内部） |
| F9 接入 GtRowActions 页面数 | ≥ 3 个高频页面 |
| F10 SSEEventType 覆盖事件数 | 与后端 SSE_EVENT_TYPES 一一对应 |
| 现有测试回归 | 零新增失败 |
| vue-tsc 编译 | 零新增错误 |

---

## 八、术语表

| 术语 | 定义 |
|------|------|
| **CWR** | Cross Workpaper Reference，跨底稿引用（cross_wp_references 表/JSON） |
| **stale** | 底稿数据过期状态，因上游数据变更导致 prefill 结果不再准确 |
| **SLA** | Service Level Agreement，服务级别协议（底稿完成时限） |
| **severity** | 严重度等级：blocking（阻断签字）/ warning（提示）/ info（仅披露） |
| **断裂** | 跨循环引用的 target 底稿不存在、已删除、或处于 stale 状态 |
| **sla_worker** | 后端定时任务，每 15 分钟扫描 SLA 超时状态 |
| **NotificationCenter** | 前端通知中心组件（DefaultLayout 顶栏） |
| **eventBus** | 前端全局事件总线（基于 mitt 库，Events 类型映射） |
| **fmtAmountUnit** | 金额格式化统一函数（formatters.ts），支持元/万元/千元换算 |
| **GtRowActions** | 本 spec 新增的表格行操作通用组件 |
| **ArchiveWizard** | 归档三步向导视图（就绪检查→选项→确认执行） |
| **ConsistencyDashboard** | 一致性仪表盘视图（质控人员使用） |
| **ReviewWorkbench** | 复核工作台视图（项目经理/合伙人使用） |
| **router_registry** | 后端路由注册表（backend/app/router_registry.py） |
| **parsed_data** | 底稿解析后的 JSON 数据（MB 级，含所有 sheet 内容） |
| **gate_engine** | 门禁引擎，归档/签字前的强制检查机制 |
| **displayPrefs** | 前端显示偏好 store（金额单位/字号/小数位数） |
| **mitt** | 轻量级 TypeScript 事件发射器库 |
| **SSEEventType** | 本 spec 新增的 SSE 事件类型联合类型 |


---

## 附录 A：Sprint 0 实测基线

| 基线变量 | 实测值 | 来源 |
|----------|--------|------|
| N_router_include_calls | 123 | `router_registry.py` 中 `app.include_router` 调用数 |
| N_cwr_total | 400 | `cross_wp_references.json` references 数组长度 |
| N_cwr_severity_blocking | 75 | severity='blocking' 条数 |
| N_cwr_severity_warning | 202 | severity='warning' 条数 |
| N_cwr_severity_info | 75 | severity='info' 条数 |
| N_cwr_severity_5_levels | 5 | blocking/warning/info/recommended/required |
| N_toFixed_occurrences | ~40+ | grep `.toFixed(` 在 .vue/.ts 文件中（含非金额用途如百分比/文件大小/耗时） |
| N_toFixed_amount_only | ~5 | 真正金额格式化遗漏（ReportView 变动率 / Adjustments 借贷合计） |
| EventType_enum_count | 26 | `backend/app/models/audit_platform_schemas.py` EventType 枚举值数 |
| EventType_format | `domain.action` | 如 `workpaper.saved` / `adjustment.created` |
| SLA_target_model | IssueTicket | sla_worker 监控对象是问题单（`due_at` 字段），非 working_paper |
| WorkingPaper.assigned_to | ✅ 存在 | `workpaper_models.py` 中 `assigned_to: UUID FK users.id` |
| CWR_json_schema | ref_id/source_wp/targets[]/severity/category | 无 `is_broken` 字段，断裂需运行时 DB 查询 |
| Notification_model | ✅ 存在 | `backend/app/models/core.py` class Notification |

### Sprint 0 偏差修正

| 起草假设 | 实测结果 | 偏差影响 | 修正方案 |
|----------|----------|----------|----------|
| F2 CWR 有 `is_broken` 字段 | JSON 无此字段 | F2 实现从纯文件读取变为 DB JOIN | 改为运行时查询 target wp_code 是否存在+是否 stale |
| F6 SLA 监控底稿 deadline | working_paper 无 deadline 字段 | F6 预警目标改为 IssueTicket.due_at | 验收标准已修正为"问题单" |
| F10 SSE 事件名臆造 10 个 | 实际 EventType 枚举 26 个 | F10 SSEEventType 需覆盖 26 个值 | design 中 SSE_EVENT_TYPES 列表替换为真实枚举 |
| F4 router_registry 87 分组 | 实际 123 个 include_router 调用 | 拆分工作量略大于预期 | 工时不变（3 天足够） |
| F8 toFixed 遗漏大量 | 实际金额相关仅 ~5 处 | F8 工作量远小于预期（0.5 天→0.2 天） | 大部分 toFixed 是百分比/文件大小/耗时，非金额 |
| CWR severity 3 级 | 实际 5 级（含 recommended/required） | F2 断裂清单排序需覆盖 5 级 | 排序规则扩展为 blocking > required > warning > recommended > info |
