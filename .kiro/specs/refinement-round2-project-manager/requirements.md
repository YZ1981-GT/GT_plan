# Refinement Round 2 — 项目经理视角（多项目作战 + 委派催办 + 简报）

## 起草契约

**起草视角**：某大型事务所项目经理（Manager），同时带 5~8 个在审项目，日常要做委派、催办、跨项目协调、对合伙人汇报、对客户沟通。本轮围绕"项目经理每天 8 小时在系统里干什么、哪里卡住、哪里反复切页"展开。

**迭代规则**：参见 [`../refinement-round1-review-closure/README.md`](../refinement-round1-review-closure/README.md) 的"5 角色轮转"模型。本轮是 Round 2，起草时 Round 1 未完成（允许 Round 1、2 并行起草需求，实施按顺序）。

## 复盘背景（项目经理视角）

以一名同时管 6 个项目的经理视角"走一遍系统"，发现以下断点集中在**多项目聚合 + 催办闭环 + 对外汇报**三件事上：

1. **没有"我的所有项目"聚合视图**：`PartnerDashboard` 是合伙人看所有项目，`PersonalDashboard` 是员工看我的待办，**项目经理没有专属看板**。经理进系统后要挨个点每个项目进 `ProjectProgressBoard`，6 个项目点 6 次。
   - 证据：`audit-platform/frontend/src/router/index.ts` 路由列表中只有 `dashboard/management`、`dashboard/partner`、`my/dashboard`，**无** `dashboard/manager`。

2. **委派无"一次到位"工具**：`batch-assign` 端点（`working_paper.py` 989 行）支持批量分配，但前端 `WorkpaperList` 的批量分配对话框**只能选编制人，不能同时选复核人**；且不能按"循环 + 职级"快速圈选。经理给 D 循环的 20 张底稿分配 3 个审计助理时要点 60 次。
   - 证据：`BatchAssignRequest` schema 已支持 `assigned_to + reviewer` 双字段，前端未充分利用。

3. **催办全靠口头**：`Notification` 模型、`NotificationService`、`NotificationCenter.vue` 组件都存在，但 **DefaultLayout 顶部没有铃铛入口**。用户看不到通知，催办等于失效。
   - 证据：`audit-platform/frontend/src/layouts/DefaultLayout.vue` 顶部只有 `#nav-review-inbox` slot，没有 notification 铃铛；`backend/app/services/issue_ticket_service.py` 185 行触发的 `issue_sla_escalated` 通知发了但前端看不到。

4. **"逾期底稿"没有催办按钮**：`ProjectDashboard` 有"关键待办 Top10"显示逾期底稿，但只列不催——没有一键提醒编制人的按钮。
   - 证据：`audit-platform/frontend/src/views/ProjectDashboard.vue` 第 45-53 行 overdue 表无 action 列。

5. **客户沟通记录与 PBC/函证脱节**：`ProjectProgressBoard.vue` 有"客户沟通记录"面板，可录入承诺事项，但承诺事项**不会生成催办任务**，也不关联 PBC 催收。经理 3 周后想不起来客户承诺过什么，只能翻沟通记录。

6. **跨项目任务聚合缺失**：`TaskTreeView` 页面只能在单项目里看任务，经理要查"所有 D 循环的待分配任务"需要进 6 个项目分别查。
   - 证据：`backend/app/routers/task_tree.py` `list_nodes` 必传 `project_id`，无全局视图。

7. **简报生成只针对单项目**：`ProjectProgressBoard.vue` 的 AI 简报只能导出单项目。经理周会要报 6 个项目的综合简报，必须手动拼。

8. **工时审批入口缺失**：`WorkHoursPage` 只有员工填报和个人查看；**经理找不到批量审批下属工时的入口**。
   - 证据：前端无 `/work-hours/approve` 路由；`WorkHourRecord.status` 有 `approved` 状态但无 UI 流转。

9. **进度看板"简报"Tab 无跨项目对比**：只有单项目简报，看不出 6 个项目哪个最落后、哪个最可能延期。

10. **委派后"通知谁"不清晰**：`AssignmentService._send_assignment_notifications` 会给被委派人发通知，但**经理自己不知道通知发成功没、对方有没有看**。没有"已读回执"展示。

## 本轮范围

Round 2 聚焦"项目经理的工作台体验"——让经理进系统后有一个页面能看完 6 个项目的核心状态，完成绝大多数日常动作（委派、催办、审批工时、生成简报）。

**不扩散到**：合伙人侧（Round 1 已覆盖）、质控规则（Round 3）、单项目底稿编辑器细节（Round 4）。

## 需求列表

### 需求 1：新增"项目经理看板"聚合视图

**用户故事**：作为项目经理，我希望一个页面看清我名下所有项目的进度、风险、待办。

**验收标准**：

1. The 系统 shall 新增路由 `/dashboard/manager` 和页面 `ManagerDashboard.vue`，挂在侧边栏"我的工作台"分组，权限限制 `role in ('manager', 'admin')`。
2. The 页面 shall 分四个区块：**项目总览**（卡片网格，每个项目一张卡：完成率、待复核、逾期、风险等级）、**跨项目待办**（合并所有项目的待复核/待分配/待审批工时，可按项目筛选）、**本周关键动作**（我需要做的 Top 5 事项）、**团队负载**（我名下员工工时分布）。
3. When 我点击项目卡片，the 系统 shall 跳转到对应 `ProjectProgressBoard`；点击"待复核"跳复核工作台（已限定该项目）；点击"待分配"跳 `WorkpaperList` 并预设筛选 `assigned_to IS NULL`。
4. The 后端 shall 新增 `GET /api/dashboard/manager/overview` 返回 `{projects: [...], cross_todos: {pending_review, pending_assign, pending_approve}, team_load: [...]}`；PM 只能看到自己作为 `manager` 或 `signing_partner` 参与的项目，SOD 守卫过滤。
5. The 看板 shall 有"上次更新 Xs 前"时间戳和刷新按钮，不做轮询避免 6000 并发时压后端。

### 需求 2：顶部通知铃铛接入

**用户故事**：作为项目经理，我希望系统给我发的通知（工单升级、问题申报、工时待批）我能在顶部立刻看到红点。

**验收标准**：

1. The `DefaultLayout.vue` 顶部 shall 新增 `#nav-notifications` slot，嵌入已有 `NotificationCenter.vue` 组件（现挂在 components 但无注入点），铃铛带未读 badge。
2. The `collaboration.ts` store 的 `fetchNotifications` shall 在应用启动时调用一次，并通过 SSE（`event_bus._notify_sse`，已有基础设施）推送实时更新，不轮询。
3. When 未读通知 > 0，the 铃铛 shall 显示红点；点击展开面板列最近 20 条，点击单条标记已读并跳转到 `related_object`（底稿/问题单/工时等）。
4. The 面板 shall 支持"全部标为已读"和分类筛选（系统通知/委派/SLA 升级/工时审批）。
5. The 通知 shall 按 `notification_type` 提供跳转规则表（后端或前端 map）：如 `ASSIGNMENT_CREATED` → 跳 `/projects/{id}/workpapers?assigned=me`、`issue_sla_escalated` → 跳问题单详情。

### 需求 3：增强批量委派对话框

**用户故事**：作为项目经理，我希望一次把 20 张 D 循环底稿分给 3 个助理（按职级/专业自动均衡），并同时指定复核人。

**验收标准**：

1. The `WorkpaperList` 批量委派对话框 shall 同时支持"编制人（必填）"与"复核人（可选）"两个字段，调用现有 `POST /projects/{id}/working-papers/batch-assign`（字段已支持，前端补）。
2. The 对话框 shall 提供**三种分配策略**选择：
   - 手动：所有底稿分给同一人
   - 轮询：按选中的候选人列表均匀分
   - 按职级：helper/senior 分初级底稿，manager 分复杂底稿（阈值从 `WpIndex.complexity` 读取，无该字段时按 `audit_cycle` 映射表走）
3. When 选择轮询/按职级，the 对话框 shall 显示**预览表**，列出每条底稿将分给谁，允许逐条微调再提交。
4. The 对话框 shall 复用 `StaffSelectDialog`（已存在），候选人范围限制为当前项目 `ProjectAssignment` 中 `role in ('auditor', 'senior_auditor', 'manager')`。
5. The 提交后 shall 一次性发 `Notification` 给所有被分配的人（`assignment_service._send_assignment_notifications` 复用），经理本人收到"已分配 20 张，3 人收到通知"的 toast。

### 需求 4：逾期底稿一键催办

**用户故事**：作为项目经理，我希望在项目看板看到逾期底稿列表时，直接点"催办"就能给编制人发一条提醒。

**验收标准**：

1. The `ProjectDashboard.vue` 第 45-53 行的 overdue 表 shall 新增"操作"列，按钮"催办"与"重新分配"。
2. The 后端 shall 新增 `POST /api/projects/{project_id}/workpapers/{wp_id}/remind`，请求体 `{message?: string}`。由于 `WorkingPaper` 无 `due_date` 字段、`wp_progress_service` 用 `created_at` 估算逾期（代码锚定：`backend/app/services/wp_progress_service.py:75`），默认消息模板调整为："您编制的底稿 {wp_code} {wp_name} 已创建 {days} 天尚未完成，请尽快推进。" 不使用"逾期"措辞避免语义误导。
3. The 催办 shall 创建 `Notification(type='workpaper_reminder')` 发给 `assigned_to`，并在 `IssueTicket` 创建 `source='reminder'` 记录（复用 R1 需求 2 预留的枚举值）。
4. The 单个底稿 7 天内最多发 3 次催办（按自然日计，依据 README 跨轮约束第 5 条不考虑节假日），超过提示"已连续催办 3 次，请考虑重新分配"。
5. The "重新分配"按钮 shall 弹出 StaffSelectDialog，选定后调用 `PUT /working-papers/{wp_id}/assign`，新编制人收到"项目 X 底稿 Y 已转交给您"通知，原编制人收到"底稿 Y 已被重新分配"通知。
6. **预留增强（本轮不做）**：`WorkingPaper.due_date` 字段本轮不新增，留待 Round 6+ 或当业务明确"按项目阶段推算 due_date"规则后统一实施。

### 需求 5：客户承诺事项→可跟踪任务

**用户故事**：作为项目经理，我在沟通记录里写的客户承诺（"本周五前提供银行询证函回函"），系统应自动变成我的待办，到期前提醒我。

**代码锚定前置说明**：`Communication / ClientCommunication` 模型 grep 零命中，当前 `ProjectProgressBoard.vue` 的沟通记录前端存在但**后端数据存储位置待确认**——可能塞在 `Project.metadata` JSON、`annotations` 或 `process_record` 中。本需求首任务（见 tasks.md）必须**先定位**当前沟通记录的落地位置，再决定是新建 `client_communications` 表还是在现有 JSON 结构里扩字段。

**验收标准**：

1. The design 阶段 shall 首先完成"沟通记录当前存储位置调研"作为 0 号前置任务，产出 ADR 记录决策（新建表 vs 扩字段）。
2. The 沟通记录 shall 支持 `commitments` 结构化字段 `[{content, due_date, status, related_pbc_id?}]`，存储方式由前置任务决定。
3. When 录入/编辑沟通记录并包含 `commitments`，the 后端 shall 为每条承诺创建 `IssueTicket(source='client_commitment', due_at=due_date, owner_id=record.created_by)`（复用 R1 需求 2 预留的枚举值）。
4. The PM 看板"跨项目待办"区块 shall 新增"客户承诺"子 tab，列出所有到期前 7 天的承诺；逾期未完成的承诺置顶红标。
5. When 承诺完成后，the PM shall 能在承诺条目点击"已完成"，系统关闭对应 `IssueTicket` 并在沟通记录时间线追加"✅ {commitment_content} 已完成"。
6. When 承诺关联了 PBC 条目（后续 Round 扩展），the 关闭承诺 shall 同步更新 PBC 状态（本轮预留字段但不实现联动，避免越界）。

### 需求 6：简报跨项目合并导出

**用户故事**：作为项目经理，周会要汇报 6 个项目。我希望在 PM 看板一键选中 6 个项目，导出一份合并简报。

**验收标准**：

1. The `ManagerDashboard.vue` shall 在项目总览区新增"批量选择 + 导出合并简报"按钮。
2. The 后端 shall 新增 `POST /api/projects/briefs/batch?project_ids=&use_ai=`，返回单一 Markdown 或 Word 文件，结构：封面（日期/经理名/项目数）→ 每项目一节（完成率/关键问题/下周计划）→ 综合风险汇总。
3. The 端点 shall 调用现有 `progress_board.brief` 逐项目生成，再拼接；AI 模式下额外传给 LLM 做全局总结（复用 `unified_ai_service`），非阻塞失败时回退到纯拼接。
4. The 生成 shall 用 `ExportJobService`（已存在）异步化，前端轮询进度；超过 6 个项目时强制走后台任务。
5. The 导出结果 shall 落到 `ExportTaskService` 历史，7 天内复用（避免每次周会重复生成耗 AI）。

### 需求 7：工时审批入口

**用户故事**：作为项目经理，我希望每周一打开"工时审批"页看到我名下员工上周工时，勾选几条点"批准"。

**验收标准**：

1. The 前端 shall 新增路由 `/work-hours/approve` 和页面 `WorkHoursApproval.vue`，挂"我的工作台"分组，权限 `role in ('manager', 'admin')`。
2. The 页面 shall 显示表格：员工/日期/项目/小时/描述/状态，默认筛选状态 `confirmed`（已确认待审批）、日期范围为上周一到上周日。
3. The 行 shall 支持多选、批量批准/退回；单行行内"批准"/"退回+原因"操作。
4. The 后端 shall 新增 `POST /api/workhours/batch-approve`，请求体 `{hour_ids: UUID[], action: 'approve'|'reject', reason?: string}`，状态流转 `confirmed→approved` 或 `confirmed→draft`（退回）。
5. When 批准，the 系统 shall 发 `Notification(type='workhour_approved')` 给员工；退回时通知附原因。
6. The 经理端 shall 看到"本周已审批 X 小时 / 未审批 Y 小时"统计卡。

### 需求 8：委派已读回执

**用户故事**：作为项目经理，我委派完一批底稿，想知道对方是否看到了通知。

**验收标准**：

1. The `Notification.is_read` 字段（已有）shall 在 PM 看板委派记录区展示为"🔵 未读 / ✅ 已读 {时间}"。
2. The `GET /api/dashboard/manager/assignment-status?project_id=&days=7` shall 返回近 N 天委派记录：`[{wp_code, assignee_name, assigned_at, notification_read_at|null}]`。
3. When 委派 48 小时后对方仍未读，the PM 看板 shall 红标提示"建议当面跟进"。
4. 本需求**仅展示不介入业务**，不会因未读导致委派失效。

## UAT 验收清单（手动验证）

1. 用 `admin/admin123`（role 改为 manager 测试，或新建 manager 账号）登录，进 `/dashboard/manager`，验证看到本人作为 manager 参与的项目卡片。
2. 顶部铃铛点击展开，制造一条委派通知（给自己委派一张底稿），验证 1 秒内铃铛红点出现。
3. 进 `WorkpaperList` 选 10 张底稿，用"按职级"策略分配，验证预览表正确、提交后 10 张状态更新、3 个人各收到 1 条通知。
4. 进 `ProjectDashboard` 找一张逾期底稿，点"催办"，验证编制人收到通知；同一张底稿连续催办 3 次，第 4 次被提示阻断。
5. 在沟通记录录入一条承诺（"本周五提供银行流水"），日期设为 2 天后，验证"客户承诺"tab 立刻出现，PM 到期前 1 天收到提醒通知。
6. PM 看板勾选 3 个项目，点"导出合并简报（AI）"，验证异步任务完成后下载的 Word 包含 3 节 + 综合总结。
7. 下属账号连续 3 天提交工时并点"确认"，经理进 `/work-hours/approve` 批量批准，员工收到"工时已批准"通知。

## 不在本轮范围

- Round 1 复核闭环（已另起）
- 质控规则扩展（Round 3）
- 底稿编辑器 / 助理新人上手（Round 4）
- EQCR 独立复核（Round 5）
- 完整 PBC/函证功能（Round 6 或按 Round 1 方案 B 提前实施）

## 验收完成标志

需求 1~8 的所有验收标准满足、UAT 7 项手动清单走完，Round 2 关闭，进入 Round 3。

## 变更日志

- v1.1 (2026-05-05) 跨轮交叉核验修正：
  - 需求 4 催办消息改用"已创建 X 天"措辞（WorkingPaper 无 due_date 字段，wp_progress_service 用 created_at 估算）；自然日口径明示
  - 需求 5 增加"沟通记录存储位置调研"作为设计阶段 0 号前置任务（`Communication` 模型 grep 零命中）
  - 需求 4/5 的 `IssueTicket.source` 值均依赖 R1 需求 2 的枚举预留
- v1.0 (2026-05-05) 项目经理视角首稿，基于 Round 1 起草后状态。

## 补充需求（v1.2，长期运营视角）

以下 2 条由合伙人第三轮深度复盘新增，聚焦"**项目成本管控 + 人员离职交接**"——PM 实际工作中出事最频繁的两个场景。

### 需求 9：项目预算/工时预警与盈亏看板

**用户故事**：作为项目经理，我希望项目启动时填预算工时，随项目推进看到"已耗 / 预算 / 预估超支"，超支前就能收到红灯预警，而不是年终合伙人找我算账。

**代码锚定**：`Project` 表无 `budget_hours / contract_amount` 字段（grep 零命中），`ProjectProgressBoard` 无盈亏视图。

**验收标准**：

1. The `Project` 表 shall 新增字段 `budget_hours: int | null / contract_amount: decimal | null / budgeted_by / budgeted_at`；项目向导创建时填入（本轮先做此两项最核心字段，完整账单模型留 R6+）。
2. The `ManagerDashboard` 项目卡 shall 显示工时"已耗 X / 预算 Y"进度条，>90% 橙色、>100% 红色闪烁。
3. The 后端 shall 新增 `GET /api/projects/{id}/cost-overview` 返回 `{budget_hours, actual_hours, remaining_hours, burn_rate_per_day, projected_overrun_date, contract_amount, cost_by_role: [...]}`（按 role 拆分成本，role 级小时费率配置在 `system_settings.hourly_rates`）。
4. When 实际工时 > 预算 80%，the 系统 shall 发 `Notification(type='budget_alert_80')` 给 PM 与 signing_partner；>100% 发 `budget_overrun`。
5. The `WorkHoursApproval.vue` 批量审批时 shall 预估"审批后将超预算 N 小时"，PM 手动确认才能批。
6. The PM 提交月度简报（R2 需求 6）时 shall 自动包含项目盈亏快照。

### 需求 10：人员离职 / 长假交接工作流

**用户故事**：作为项目经理，当 T0 员工突然离职或请长假时，我希望系统一键把他名下所有底稿/工单/待办转给其他人，且留痕"某年某月由 A 转交 B"。

**代码锚定**：当前 `ProjectAssignment` 软删除 + `WorkingPaper.assigned_to` 手动改是仅有能力，无批量转交工具，无"为什么转、转给谁"的审计链。

**验收标准**：

1. The 后端 shall 新增 `POST /api/staff/{staff_id}/handover`，请求体 `{scope: 'all'|'by_project', project_ids?: UUID[], target_staff_id, reason_code('resignation'|'long_leave'|'rotation'|'other'), reason_detail, effective_date}`。
2. The 执行器 shall 批量：更新 `WorkingPaper.assigned_to`、`IssueTicket.owner_id`、`ProjectAssignment` 转移权限；每条变更写 `handover_records` 新表留痕。
3. The 交接记录归属项目 `audit_log` 哈希链（R1 需求 9 落地），不可篡改。
4. The 前端 `StaffManagement.vue` 对每个 staff 新增"交接"按钮，弹窗选目标人 + 原因；预览"将转交 N 张底稿、M 张工单、K 个项目"。
5. When `reason_code='resignation'` 且执行完成，the 系统 shall 自动把该 staff 所有未完成独立性声明（R1 需求 10）标记为 `superseded_by_handover`，避免阻断 gate。
6. The 交接完成发 `Notification(type='handover_received')` 给新负责人，内含交接清单链接。

## 变更日志（续）

- v1.2 (2026-05-05) 长期运营视角增强：
  - 新增需求 9：项目预算/工时预警与盈亏看板（事务所最常见的"账算不清"问题）
  - 新增需求 10：离职/长假交接工作流（人员流动高频场景）
