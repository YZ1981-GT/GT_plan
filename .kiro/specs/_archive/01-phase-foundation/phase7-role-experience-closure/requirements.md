# Requirements Document — Phase 7: EQCR + QC + 工时体验闭环

## 一、变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-05-22 | 初始起草，基于《平台全局建议书》E-2/E-3/E-4 + Q-3/Q-4/Q-5 + W-1/W-2/M-2/M-5 + RV-3 + P-2/P-4 共 13 项功能 |

## 依赖矩阵

| 依赖项 | 类型 | 状态 |
|--------|------|------|
| Phase 6 F4 项目级权限端点 | 前置 | ❌ 待 Phase 6 实施（EQCR/QC 权限判断需要） |
| eqcr_snapshots 表 + eqcr_snapshot_service.py (Phase 4) | 后端 | ✅ 已有 |
| IssueTicket 模型 + issue_ticket_service.py (Phase 15) | 后端 | ✅ 已有 |
| SSEEventType 联合类型 (32 值) + eventBus.ts | 前端 | ✅ 已有 |
| knowledge_base router + KnowledgeBase.vue | 后端+前端 | ✅ 已有 |
| *_cycle_validation_rules.json (11 循环) | 数据 | ✅ 已有 |
| PartnerProjectDashboard.vue + DashboardAggregatorService | 前端+后端 | ✅ 已有 |
| LinkagePanoramaView + ForceGraph.vue (联动全景图 spec) | 前端 | ✅ 已有 |
| ReviewWorkbench + ReviewRecord.priority (Phase 2) | 前端+后端 | ✅ 已有 |
| python-docx (Phase 3 附注 Word 导出基础) | 后端依赖 | ✅ 已有 |
| ECharts + vue-echarts | 前端 | ✅ 已有 |
| ProjectAssignment 模型 (project_assignments 表) | 后端 | ✅ 已有 |
| WorkingPaper 模型 + WpIndex | 后端 | ✅ 已有 |

---

## 二、为什么做（业务痛点）

### 2.1 EQCR 独立复核意见无结构化模板（E-2）
- **痛点**：5 个判断维度（重大错报/持续经营/关键审计事项/其他信息/审计报告）缺乏标准化输入，EQCR 合伙人只能写纯文本
- **影响角色**：EQCR 独立复核合伙人
- **技术根因**：eqcr_snapshot_service 仅聚合数据供只读查看，无结构化判断表单；无 JSONB 字段存储 5 维度结构化结论

### 2.2 EQCR 与项目团队沟通无审计轨迹（E-3）
- **痛点**：EQCR 提出问题后，项目团队回复散落在各处，无独立的沟通审计轨迹
- **影响角色**：EQCR 独立复核合伙人、项目团队
- **技术根因**：IssueTicket 模型已有完整问题单机制（source 枚举含 11 值），但无 EQCR 专属可见性隔离；EQCR 问题单需仅 EQCR↔项目团队可见（排除其他角色）

### 2.3 EQCR 指标仪表盘缺乏历史趋势（E-4）
- **痛点**：EqcrMetrics 仅显示当前项目状态，无法看到"本所 EQCR 通过率趋势"
- **影响角色**：EQCR 独立复核合伙人、质控管理层
- **技术根因**：eqcr_snapshots 表有 created_at + year 字段可支持历史聚合，但无趋势统计端点

### 2.4 复核意见模板缺失（Q-3）
- **痛点**：质控人员每次写复核意见都从零开始，常见问题（如"请补充审计程序执行记录"）重复输入
- **影响角色**：质控人员、项目经理（复核效率）
- **技术根因**：knowledge_base router 已有全局/项目级文档管理，但无"复核意见模板"子分类；无一键插入机制

### 2.5 QC 报告无标准化 Word 导出（Q-4）
- **痛点**：质控报告需手动整理，无标准化 Word 导出格式
- **影响角色**：质控人员（报告输出效率）
- **技术根因**：Phase 3 附注 Word 导出已建立 python-docx 基础设施，但无 QC 报告专用模板（三线表格式：风险汇总+意见清单+整改状态）

### 2.6 VR 规则覆盖度不均（Q-5）
- **痛点**：11 个循环 VR 规则覆盖面不均（部分循环仅 2 条 blocking），质控无法量化评估覆盖度
- **影响角色**：质控人员（风险把控）
- **技术根因**：各循环 *_cycle_validation_rules.json 独立维护，无统一覆盖度标准（每循环至少 3 条 blocking + 2 条 warning）；无覆盖度仪表盘

### 2.7 工时填报粒度过粗（W-1）
- **痛点**：当前工时按"天"填报，无法精确到底稿/循环/程序级别
- **影响角色**：审计助理（填报者）、项目经理（审批者）
- **技术根因**：无 WorkHour 模型支持三级粒度（底稿/循环/程序）；当前无工时管理模块实现

### 2.8 工时预算与实际对比无可视化（W-2）
- **痛点**：budget_alert_worker 仅后台告警，项目经理无法直观看到预算 vs 实际的差异
- **影响角色**：项目经理（成本管控）
- **技术根因**：无 WorkHoursPage 可视化组件；无按循环/按人员两维度的柱状图

### 2.9 复核分派无智能推荐（M-2）
- **痛点**：手动分配复核人，不考虑工时负载和专业领域
- **影响角色**：项目经理（分派效率）
- **技术根因**：ProjectAssignment 有 role 字段但无"历史复核记录+当前工时余量+循环专长"的推荐算法

### 2.10 工时审批与底稿进度脱钩（M-5）
- **痛点**：审批工时时看不到对应底稿的完成度，无法判断工时合理性
- **影响角色**：项目经理（审批决策）
- **技术根因**：工时审批页面无"关联底稿进度"列；WorkingPaper 有 review_status 可计算完成百分比

### 2.11 复核进度无实时通知（RV-3）
- **痛点**：提交复核后助理不知道经理是否已开始看，需反复刷新页面
- **影响角色**：审计助理（等待反馈）
- **技术根因**：SSEEventType 已有 `review_record.created` 但无 `review.status_changed`（已接收/复核中/已完成）；SSE eventBus 基础设施完备，仅需扩展事件类型

### 2.12 多项目紧急度评分缺失（P-2）
- **痛点**：合伙人管 5-10 个项目，无法快速判断哪个项目最紧急
- **影响角色**：合伙人（决策优先级）
- **技术根因**：PartnerProjectDashboard 有 CycleProgressRing 但无跨项目紧急度排序；Phase 6 F7 ManagerDashboard 有 urgency_score 算法可复用

### 2.13 联动全景图无"仅显示 stale"过滤器（P-4）
- **痛点**：stale 传播后合伙人不知道影响范围，需在全量节点中肉眼找红色节点
- **影响角色**：合伙人（风险感知）
- **技术根因**：ForceGraph.vue 已有 stale 节点着色（红色），但无过滤器仅显示 stale 子图

---

## 三、范围边界

### A. 必做（In Scope）

| 编号 | 功能项 | 来源 |
|------|--------|------|
| F1 | EQCR 结构化判断模板（5 维度表单） | E-2 |
| F2 | EQCR 问题单独立模块（仅 EQCR↔项目团队可见） | E-3 |
| F3 | EQCR 历史趋势图（通过率/平均复核天数/常见问题 Top 5） | E-4 |
| F4 | 复核意见模板库（知识库子模块 + 一键插入） | Q-3 |
| F5 | QC 报告 Word 导出（三线表格式） | Q-4 |
| F6 | VR 规则覆盖度标准 + 仪表盘 | Q-5 |
| F7 | 工时填报粒度细化（底稿/循环/程序三级） | W-1 |
| F8 | 工时预算 vs 实际可视化（柱状图） | W-2 |
| F9 | 复核分派智能推荐 | M-2 |
| F10 | 工时审批与底稿进度关联 | M-5 |
| F11 | 复核进度实时通知（SSE 推送） | RV-3 |
| F12 | 多项目紧急度评分排序 | P-2 |
| F13 | 联动全景图"仅显示 stale"过滤器 | P-4 |

### B. 排除（Out of Scope）

- 不涉及 EQCR 快照机制改造（Phase 4 已完成，本 spec 仅扩展判断表单）
- 不涉及 IssueTicket 模型 schema 变更（复用现有 source 枚举，新增 `eqcr` 值即可）
- 不涉及工时移动端审批（仅 PC 端实现）
- 不涉及工时加班自动识别（W-4，延后）
- 不涉及 VR 规则内容编写（仅提供覆盖度标准和仪表盘，不新增 VR 规则条目）
- 不涉及 ForceGraph.vue 力模拟算法改造（仅新增过滤器 UI）
- 不涉及 PartnerProjectDashboard 整体重构（仅新增紧急度评分列）
- 不涉及 python-docx 模板引擎重写（复用 Phase 3 已有基础设施）
- 不涉及新 DB 表创建（大部分复用现有模型，仅需扩展字段或新增 JSONB 列）

### C. Sprint 0 基线变量（已实测）

| 基线变量 | 预估值 | 实测值 | 来源 |
|----------|--------|--------|------|
| N_eqcr_snapshots_columns | 7 | 7 | eqcr_snapshots 表字段数（id/project_id/year/created_by/created_at/snapshot_data/is_current） |
| N_issue_ticket_source_values | 11 | 11 | IssueTicket.source 枚举值数（L2/L3/Q/review_comment/consistency/ai/reminder/client_commitment/pbc/confirmation/qc_inspection） |
| N_sse_event_types | 32 | 32 | SSEEventType 联合类型值数（audit-platform/frontend/src/types/sse.ts） |
| N_vr_rules_per_cycle | 2~4 | 1~20 | 各循环 blocking 条数（d:20/bcas:11/efghijklmn:14/g:4/h:3/i:3/j:2/k:2/l:2/f:1/m:1/n:1） |
| N_vr_total_rules | 114 | 114 | 全仓 VR 规则总数（12 个 JSON 文件） |
| N_knowledge_base_categories | ~5 | 9 | knowledge_base router LIBRARY_DEFS 分类数（底稿模板/监管规定/会计准则/质控标准/审计程序/行业指引/提示词/报告模板/笔记） |
| N_partner_dashboard_modules | 6 | 6 | PartnerProjectDashboard 子组件数（CycleProgressRing/VRSummaryCard/ReviewOpinionList/QuickEntryPanel/ProjectTimeline/TrimmingOverview） |
| N_force_graph_filter_props | 0 | 0 | ForceGraph.vue 现有过滤器 prop 数（仅 nodes/links/width/height 四个 prop，无 filter 相关） |
| python_docx_installed | ✅/❌ | ❌ | requirements.txt 不含 python-docx（仅有 python-jose/python-multipart） |
| WorkHour_model_exists | ❌ | ✅ | staff_models.py 已有 class WorkHour（work_hours 表） |
| budget_alert_worker_exists | ❌ | ✅ | backend/app/workers/budget_alert_worker.py 已存在且在 main.py 注册 |
| ProjectAssignment_role_values | 6 | 6 | project_assignments.role 枚举值（manager/signing_partner/auditor/eqcr/qc/readonly） |

### D. Sprint 0 偏差分析

| 变量 | 起草假设 | 实测值 | 偏差影响 | 修正方案 |
|------|----------|--------|----------|----------|
| N_vr_rules_per_cycle | 2~4 | 1~20 | F6 覆盖度标准"每循环至少 3 条 blocking"对 d_cycle(20) 无意义，对 f/m/n(1) 有实际缺口 | F6 仪表盘按实测值展示，达标标准不变（≥3 blocking + ≥2 warning） |
| N_knowledge_base_categories | ~5 | 9 | F4 复核意见模板作为独立 review_templates 表实现（非 knowledge_base 子分类），不影响现有 9 分类 | F4 设计已独立建表，无需修改 knowledge_base router |
| python_docx_installed | ✅ | ❌ | F5 QC Word 导出需要 python-docx 依赖，当前未安装 | Sprint 2 F5 实施时需先 `pip install python-docx` 并追加到 requirements.txt |
| WorkHour_model_exists | ❌ | ✅ | F7 无需从零建模，已有 WorkHour（work_hours 表），但仅支持 staff_id/project_id/work_date/hours/status 粒度，缺少 cycle/wp_code/procedure 三级粒度 | F7 新建 work_hour_entries 表（三级粒度），与现有 work_hours 表并存（现有表用于简单工时统计，新表用于精细化填报） |
| budget_alert_worker_exists | ❌ | ✅ | F8 预算可视化可复用 budget_alert_worker 的预算阈值逻辑，无需重新实现告警机制 | F8 仅新增可视化端点，复用 worker 已有的预算配置读取逻辑 |

---

## 四、功能需求（EARS 范式）

### F1 EQCR 结构化判断模板

**User Story:** 作为 EQCR 独立复核合伙人，我希望对 5 个判断维度有结构化表单输入（结论+依据+引用底稿+风险等级），以便形成标准化、可追溯的独立复核意见。

#### 验收标准

1. THE EQCR 判断模块 SHALL 提供 5 个判断维度的结构化表单：重大错报风险、持续经营、关键审计事项、其他信息、审计报告
2. THE 每个判断维度表单 SHALL 包含 4 个字段：结论（通过/有保留/不通过）、依据（富文本）、引用底稿（多选 wp_code 列表）、风险等级（高/中/低）
3. WHEN EQCR 合伙人提交判断，THE 系统 SHALL 将结构化数据存储到 eqcr_snapshots.snapshot_data 的 `judgments` 字段（JSONB）
4. THE 系统 SHALL 校验所有 5 个维度均已填写结论后才允许提交最终 EQCR 意见
5. WHEN EQCR 合伙人查看历史快照，THE 系统 SHALL 以只读模式展示已提交的结构化判断
6. IF 任一维度结论为"不通过"，THE 系统 SHALL 在 EQCR 汇总面板高亮显示该维度并阻断签字流程

### F2 EQCR 问题单独立模块

**User Story:** 作为 EQCR 独立复核合伙人，我希望有独立的问题单模块与项目团队沟通，仅 EQCR↔项目团队可见，以便保持独立复核的审计轨迹。

#### 验收标准

1. THE 系统 SHALL 新增 EQCR 问题单列表视图（路由 `/projects/:id/eqcr-issues`），仅 EQCR 角色和项目团队（manager/signing_partner/auditor）可见
2. THE EQCR 问题单 SHALL 复用 IssueTicket 模型，source 字段值为 `eqcr`
3. WHEN EQCR 合伙人创建问题单，THE 系统 SHALL 自动设置 source='eqcr' 并限制可见性
4. THE 问题单列表 SHALL 按 severity 降序 + created_at 升序排列
5. THE 每条问题单 SHALL 支持对话线程（thread_id），EQCR 和项目团队可在线程中回复
6. WHEN 项目团队回复问题单，THE 系统 SHALL 通过 SSE 推送通知到 EQCR 合伙人
7. THE 系统 SHALL 在 EQCR 问题单列表显示统计摘要：open N / in_fix N / closed N
8. IF 用户角色非 EQCR 且非项目团队成员，THE 系统 SHALL 返回 403 禁止访问

### F3 EQCR 历史趋势图

**User Story:** 作为质控管理层，我希望看到 EQCR 年度趋势图（通过率/平均复核天数/常见问题 Top 5），以便评估独立复核质量趋势。

#### 验收标准

1. THE 后端 SHALL 新增 `GET /api/eqcr/metrics/trends` 端点，返回近 5 年 EQCR 趋势数据
2. THE 趋势数据 SHALL 包含：年度通过率（%）、平均复核天数、常见问题 Top 5（按出现频次）
3. THE 通过率 SHALL 基于 eqcr_snapshots 表中 judgments 字段的 5 维度结论统计（全部"通过"= 项目通过）
4. THE 平均复核天数 SHALL 基于 eqcr_snapshots.created_at 与项目提交 EQCR 复核时间的差值
5. THE 前端 SHALL 在 EqcrMetrics 页面新增"年度趋势"Tab，使用 ECharts 折线图展示通过率 + 柱状图展示复核天数
6. THE 常见问题 Top 5 SHALL 基于 EQCR 问题单（source='eqcr'）的 category 字段聚合统计

### F4 复核意见模板库

**User Story:** 作为质控人员/项目经理，我希望有复核意见模板库，支持一键插入常用复核意见，以便提升复核效率。

#### 验收标准

1. THE 系统 SHALL 在知识库模块新增"复核意见模板"分类（category='review_templates'）
2. THE 模板库 SHALL 支持 CRUD 操作：新增/编辑/删除/搜索模板
3. THE 每条模板 SHALL 包含：标题、内容（富文本）、适用循环（多选）、优先级标签（must_fix/suggest/info）、使用次数统计
4. WHEN 用户在 ReviewWorkbench 撰写复核意见时，THE 系统 SHALL 提供"插入模板"按钮
5. WHEN 用户点击"插入模板"，THE 系统 SHALL 弹出模板选择面板，支持按关键词搜索和按循环过滤
6. WHEN 用户选择模板，THE 系统 SHALL 将模板内容插入到当前复核意见输入框，并递增该模板使用次数
7. THE 模板库 SHALL 预置至少 10 条常用复核意见模板（如"请补充审计程序执行记录"/"请核实金额差异原因"等）

### F5 QC 报告 Word 导出

**User Story:** 作为质控人员，我希望一键导出标准化 QC 报告（Word 三线表格式），以便存档和分发。

#### 验收标准

1. THE 后端 SHALL 新增 `GET /api/projects/{id}/qc-report/export` 端点，返回 .docx 文件流
2. THE QC 报告 SHALL 包含三个标准化章节：风险汇总表、意见清单表、整改状态表
3. THE 风险汇总表 SHALL 按循环×风险等级（blocking/warning/info）展示 VR 规则触发统计
4. THE 意见清单表 SHALL 列出所有 QC 复核意见（来源 IssueTicket source='qc_inspection'），含底稿编号/问题描述/严重度/责任人
5. THE 整改状态表 SHALL 显示每条意见的当前状态（open/in_fix/closed）+ 整改截止日期 + 整改人
6. THE Word 文档 SHALL 使用三线表格式（仅顶线+表头底线+底线，无竖线），字体仿宋_GB2312 + Arial Narrow 数字
7. WHEN 项目无 QC 检查记录，THE 系统 SHALL 返回空报告模板（含表头但无数据行）

### F6 VR 规则覆盖度标准

**User Story:** 作为质控人员，我希望有 VR 规则覆盖度标准和仪表盘，以便量化评估各循环校验规则的完备性。

#### 验收标准

1. THE 系统 SHALL 定义 VR 覆盖度标准：每循环至少 3 条 blocking 规则 + 2 条 warning 规则
2. THE 后端 SHALL 新增 `GET /api/qc/vr-coverage` 端点，返回各循环 VR 规则覆盖度统计
3. THE 覆盖度统计 SHALL 包含：循环名称、blocking 条数、warning 条数、info 条数、是否达标（bool）、缺口数
4. THE 前端 SHALL 在 QCDashboard 新增"VR 覆盖度"Tab，以表格+进度条展示各循环达标情况
5. WHEN 某循环未达标（blocking < 3 或 warning < 2），THE 系统 SHALL 以红色高亮显示该循环行
6. THE 覆盖度数据 SHALL 基于运行时扫描各循环 *_cycle_validation_rules.json 文件统计

### F7 工时填报粒度细化

**User Story:** 作为审计助理，我希望按底稿/循环/程序三级粒度填报工时，以便精确记录时间分配。

#### 验收标准

1. THE 后端 SHALL 新增 WorkHourEntry 模型，支持三级粒度：project_id + cycle（循环）+ wp_code（底稿）+ procedure（程序）
2. THE WorkHourEntry SHALL 包含字段：user_id、project_id、date、hours（Decimal(5,2)）、cycle、wp_code（nullable）、procedure（nullable）、description、status（draft/submitted/approved/rejected）
3. THE 后端 SHALL 新增工时 CRUD 端点：POST/GET/PUT/DELETE `/api/projects/{id}/workhours`
4. THE 系统 SHALL 支持按日/周/月汇总工时（自动聚合三级粒度到上级）
5. THE 前端 SHALL 新增 WorkHoursPage 视图，包含日历视图 + 填报表单 + 汇总统计
6. WHEN 用户填报工时时选择底稿级别，THE 系统 SHALL 自动推断所属循环（基于 wp_code 前缀）
7. THE 系统 SHALL 校验单日工时合计不超过 24 小时

### F8 工时预算 vs 实际可视化

**User Story:** 作为项目经理，我希望看到工时预算与实际的柱状图对比（按循环/按人员），以便及时发现超支。

#### 验收标准

1. THE 后端 SHALL 新增 `GET /api/projects/{id}/workhours/budget-vs-actual` 端点
2. THE 端点 SHALL 返回两个维度的对比数据：按循环聚合 + 按人员聚合
3. THE 按循环数据 SHALL 包含：cycle_name、budget_hours、actual_hours、variance（%）
4. THE 按人员数据 SHALL 包含：user_name、budget_hours、actual_hours、variance（%）
5. THE 前端 SHALL 在 WorkHoursPage 新增"预算对比"Tab，使用 ECharts 分组柱状图展示
6. WHEN 实际工时超过预算 120%，THE 系统 SHALL 以红色标注该柱状图条目
7. THE 预算数据 SHALL 来源于项目配置（projects.budget_config JSONB 字段，按循环/按人员分配）

### F9 复核分派智能推荐

**User Story:** 作为项目经理，我希望系统基于历史复核记录+当前工时余量+循环专长推荐复核人，以便高效分派复核任务。

#### 验收标准

1. THE 后端 SHALL 新增 `GET /api/projects/{id}/review-recommend?cycle={cycle}&wp_code={wp_code}` 端点
2. THE 推荐算法 SHALL 基于三个维度加权评分：历史复核记录（40%）+ 当前工时余量（30%）+ 循环专长（30%）
3. THE 历史复核记录 SHALL 统计该人员在同循环底稿的复核次数（越多越专业）
4. THE 当前工时余量 SHALL 基于本周已填报工时 vs 标准工时（40h/周）的差值（余量越大越推荐）
5. THE 循环专长 SHALL 基于 ProjectAssignment 中该人员历史参与的循环类型匹配度
6. THE 端点 SHALL 返回 Top 3 推荐人选，每人附带评分明细（三维度分数）
7. THE 前端 SHALL 在复核分派弹窗中显示"推荐复核人"卡片，用户可一键选择或手动指定
8. IF 项目团队人数 < 3，THE 系统 SHALL 返回全部可用人员（不做排序过滤）

### F10 工时审批与底稿进度关联

**User Story:** 作为项目经理，我希望在工时审批页面看到"关联底稿进度"列，以便判断工时合理性。

#### 验收标准

1. THE 工时审批列表 SHALL 新增"关联底稿进度"列，显示该助理负责底稿的完成百分比
2. THE 完成百分比 SHALL 基于 WorkingPaper.review_status 计算：level2_passed 或更高 = 100%，level1_passed = 50%，其余 = 0%
3. WHEN 底稿进度 < 30% 但工时已超预算 80%，THE 系统 SHALL 以橙色警告标注该行
4. THE 关联底稿进度 SHALL 按该用户 assigned_to 的底稿聚合（加权平均）
5. THE 前端 SHALL 在工时审批表格中以进度条形式展示完成百分比
6. THE 进度数据 SHALL 与工时数据在同一 API 响应中返回（避免 N+1 查询）

### F11 复核进度实时通知

**User Story:** 作为审计助理，我希望提交复核后通过 SSE 实时收到状态变更通知（已接收/复核中/已完成），以便无需反复刷新页面。

#### 验收标准

1. THE SSEEventType SHALL 新增 2 个事件类型：`review.accepted`（复核人已接收）、`review.completed`（复核完成）
2. WHEN 复核人打开待复核底稿，THE 后端 SHALL 发送 `review.accepted` SSE 事件到提交者
3. WHEN 复核人提交复核结论（通过/退回），THE 后端 SHALL 发送 `review.completed` SSE 事件到提交者
5. THE SSE 事件 payload SHALL 包含：review_id、wp_code、reviewer_name、status、timestamp
6. THE 前端 SHALL 在 NotificationCenter 显示复核进度通知卡片（含底稿编号+复核人+状态）
7. THE 前端 SHALL 在 ReviewWorkbench 的"我提交的"列表中实时更新复核状态标签（灰色→蓝色→绿色/红色）
8. IF SSE 连接断开，THE 系统 SHALL 在重连后补发断连期间的状态变更（基于 last_event_id）

### F12 多项目紧急度评分排序

**User Story:** 作为合伙人，我希望在 PartnerDashboard 看到多项目按紧急度评分排序，以便快速判断哪个项目最需要关注。

#### 验收标准

1. THE 后端 SHALL 新增 `GET /api/partner/projects/urgency` 端点，返回当前合伙人负责的所有项目紧急度评分
2. THE 紧急度评分 SHALL 基于：SLA 剩余时间权重 40% + blocking VR 数权重 30% + 未完成底稿比例权重 30%（复用 Phase 6 F7 urgency_score 算法）
3. THE 项目列表 SHALL 按 urgency_score 降序排列（最紧急的排最前）
4. THE 每个项目 SHALL 显示：项目名称、客户名称、紧急度评分（0-100）、紧急度标签（红/橙/黄/绿）、关键指标摘要
5. THE 前端 SHALL 在 PartnerProjectDashboard 顶部新增"项目紧急度排行"卡片
6. WHEN 紧急度评分 ≥ 80，THE 系统 SHALL 以红色标签标注"紧急"
7. WHEN 紧急度评分 ≥ 60 且 < 80，THE 系统 SHALL 以橙色标签标注"关注"

### F13 联动全景图"仅显示 stale"过滤器

**User Story:** 作为合伙人，我希望在联动全景图中一键过滤仅显示 stale 节点及其关联边，以便快速评估 stale 传播影响范围。

#### 验收标准

1. THE ForceGraph 组件 SHALL 新增 `staleOnly` 过滤器 prop（boolean）
2. WHEN staleOnly=true，THE 图 SHALL 仅显示 is_stale=true 的节点 + 与 stale 节点直接相连的边 + 边的另一端节点（即 stale 子图 + 一跳邻居）
3. THE LinkagePanoramaView SHALL 在工具栏新增"仅显示 stale"切换按钮（el-switch）
4. WHEN 用户切换 staleOnly 过滤器，THE 图 SHALL 平滑过渡（非 stale 节点 fade out，stale 节点保持位置）
5. THE stale 子图 SHALL 保持原有力模拟布局（不重新计算位置，仅隐藏非相关节点）
6. WHEN staleOnly=true 且无 stale 节点，THE 系统 SHALL 显示"当前无 stale 底稿 ✓"空状态提示
7. THE 过滤器状态 SHALL 通过 URL query 参数持久化（`?stale_only=1`），刷新后保持

---

## 五、非功能需求

| 维度 | 要求 | 适用功能 |
|------|------|----------|
| 性能 | F1 判断表单提交 ≤ 500ms | F1 |
| 性能 | F3 趋势数据查询 ≤ 1s（5 年数据） | F3 |
| 性能 | F5 Word 导出 ≤ 3s（100 条意见规模） | F5 |
| 性能 | F7 工时 CRUD ≤ 200ms | F7 |
| 性能 | F8 预算对比查询 ≤ 500ms | F8 |
| 性能 | F9 推荐算法 ≤ 500ms（20 人团队规模） | F9 |
| 性能 | F11 SSE 事件延迟 ≤ 2s（从后端触发到前端收到） | F11 |
| 性能 | F12 紧急度评分查询 ≤ 1s（10 项目规模） | F12 |
| 性能 | F13 stale 过滤渲染 ≤ 500ms（128 节点规模） | F13 |
| 安全 | F2 EQCR 问题单仅 EQCR+项目团队可见（RBAC 隔离） | F2 |
| 安全 | F7 工时填报仅本人可操作（admin 除外） | F7 |
| 安全 | F10 工时审批仅 manager/partner/admin 可操作 | F10 |
| 兼容性 | F11 SSE 新增事件类型后 vue-tsc 零新增错误 | F11 |
| 兼容性 | F13 过滤器不影响 ForceGraph 现有交互（zoom/drag/hover） | F13 |
| 可观测性 | F1 EQCR 判断提交写入 audit_log | F1 |
| 可观测性 | F5 Word 导出操作写入 audit_log | F5 |
| 可观测性 | F7 工时状态变更写入 audit_log | F7 |
| 幂等性 | F11 同一复核状态变更 SSE 事件不重复推送 | F11 |
| 事务性 | F7 工时批量提交在单事务中执行 | F7 |
| 可测试性 | F9 推荐算法提供 property：工时余量越大 → 评分越高（单调性） | F9 |
| 可测试性 | F12 紧急度评分提供 property：SLA 剩余时间越少 → score 越高（单调性） | F12 |

---

## 六、测试矩阵

| 功能 | 单元测试 | PBT | 集成测试 | 前端 vitest | UAT |
|------|----------|-----|----------|-------------|-----|
| F1 EQCR 判断模板 | 5 维度校验逻辑 | — | API 端点 + JSONB 存储 | EqcrJudgmentForm | EQCR 提交判断 |
| F2 EQCR 问题单 | 可见性过滤逻辑 | — | API 端点 + RBAC | EqcrIssueList | EQCR 创建问题单 |
| F3 EQCR 趋势图 | 通过率计算 | — | 趋势聚合端点 | EqcrTrendChart | 趋势图展示 |
| F4 复核意见模板 | 搜索+过滤逻辑 | — | CRUD 端点 | ReviewTemplatePanel | 一键插入模板 |
| F5 QC Word 导出 | 三线表生成 | — | 导出端点 | — | 下载 Word 验证 |
| F6 VR 覆盖度 | 达标判断逻辑 | — | 覆盖度端点 | VRCoverageTab | 覆盖度仪表盘 |
| F7 工时填报 | 粒度校验+汇总 | 日合计 ≤ 24h | CRUD 端点 | WorkHoursPage | 三级粒度填报 |
| F8 预算对比 | 方差计算 | — | 对比端点 | BudgetCompareChart | 柱状图展示 |
| F9 智能推荐 | 三维度评分 | 单调性 property | 推荐端点 | ReviewRecommendCard | 推荐人选展示 |
| F10 进度关联 | 完成度计算 | — | 审批列表端点 | WorkHourApprovalTable | 进度列展示 |
| F11 复核通知 | SSE 事件发送 | — | SSE 推送集成 | NotificationCard | 实时收到通知 |
| F12 紧急度评分 | 评分算法 | 单调性 property | 评分端点 | UrgencyRankCard | 排序正确 |
| F13 stale 过滤 | 子图提取逻辑 | — | — | ForceGraph filter | 过滤效果正确 |

### 测试文件清单（预期）

| 文件 | 覆盖功能 |
|------|----------|
| `backend/tests/test_eqcr_judgment.py` | F1 |
| `backend/tests/test_eqcr_issues.py` | F2 |
| `backend/tests/test_eqcr_trends.py` | F3 |
| `backend/tests/test_review_templates.py` | F4 |
| `backend/tests/test_qc_word_export.py` | F5 |
| `backend/tests/test_vr_coverage.py` | F6 |
| `backend/tests/test_workhour_crud.py` | F7 |
| `backend/tests/test_workhour_budget_compare.py` | F8 |
| `backend/tests/test_review_recommend.py` | F9 |
| `backend/tests/test_workhour_approval.py` | F10 |
| `backend/tests/test_review_notification_sse.py` | F11 |
| `backend/tests/test_partner_urgency.py` | F12 |
| `frontend/src/__tests__/EqcrJudgmentForm.spec.ts` | F1 |
| `frontend/src/__tests__/EqcrIssueList.spec.ts` | F2 |
| `frontend/src/__tests__/EqcrTrendChart.spec.ts` | F3 |
| `frontend/src/__tests__/ReviewTemplatePanel.spec.ts` | F4 |
| `frontend/src/__tests__/VRCoverageTab.spec.ts` | F6 |
| `frontend/src/__tests__/WorkHoursPage.spec.ts` | F7 |
| `frontend/src/__tests__/BudgetCompareChart.spec.ts` | F8 |
| `frontend/src/__tests__/ReviewRecommendCard.spec.ts` | F9 |
| `frontend/src/__tests__/ForceGraphStaleFilter.spec.ts` | F13 |
| `backend/tests/test_phase7_pbt.py` | F7/F9/F12 PBT |

### PBT 正确性属性（预期）

| 编号 | 属性 | 适用功能 | 类型 |
|------|------|----------|------|
| P1 | 工时日合计不变量：同一用户同一天所有 entries 的 hours 合计 ≤ 24.0 | F7 | Invariant |
| P2 | 工时粒度汇总一致性：按底稿汇总 = 按循环汇总中该循环的子集 | F7 | Metamorphic |
| P3 | 推荐评分单调性：工时余量越大 → 推荐评分越高（其他维度固定） | F9 | Metamorphic |
| P4 | 推荐评分单调性：历史复核次数越多 → 推荐评分越高（其他维度固定） | F9 | Metamorphic |
| P5 | 紧急度评分单调性：SLA 剩余时间越少 → urgency_score 越高（其他维度固定） | F12 | Metamorphic |
| P6 | 紧急度评分范围不变量：0 ≤ urgency_score ≤ 100 | F12 | Invariant |
| P7 | stale 过滤幂等性：filter(filter(graph)) = filter(graph) | F13 | Idempotence |

---

## 七、成功判据 + 术语表

### 成功判据

| 指标 | 目标 |
|------|------|
| F1 EQCR 判断维度覆盖 | 5/5 维度结构化表单 |
| F2 EQCR 问题单可见性隔离 | 非 EQCR/非项目团队 403 |
| F3 趋势图年度覆盖 | ≥ 3 年数据展示 |
| F4 预置模板数 | ≥ 10 条常用复核意见 |
| F5 Word 导出章节 | 3 章（风险汇总+意见清单+整改状态） |
| F6 VR 覆盖度达标循环数 | 运行时统计（目标：识别短板循环） |
| F7 工时粒度级别 | 3 级（循环/底稿/程序） |
| F8 对比维度 | 2 维（按循环+按人员） |
| F9 推荐人选数 | Top 3 |
| F10 进度关联列 | 工时审批表格含进度条 |
| F11 SSE 新增事件类型 | 2 个（accepted/completed） |
| F12 紧急度评分维度 | 3 维加权（SLA+VR+底稿） |
| F13 stale 过滤器 | 一键切换 + 平滑过渡 |
| 现有测试回归 | 零新增失败 |
| vue-tsc 编译 | 零新增错误 |

### UAT 验收清单

| # | 验收项 | P | 角色 | 验证方式 |
|---|--------|---|------|----------|
| 1 | EQCR 5 维度结构化表单可填写提交 | P0 | EQCR | 登录 EQCR 角色填写 |
| 2 | EQCR 问题单仅 EQCR+项目团队可见 | P0 | EQCR/助理 | 不同角色访问验证 |
| 3 | EQCR 趋势图展示年度数据 | P1 | 质控 | EqcrMetrics 页面查看 |
| 4 | 复核意见模板一键插入 | P0 | 经理 | ReviewWorkbench 操作 |
| 5 | QC 报告 Word 下载成功 | P0 | 质控 | 下载并打开验证格式 |
| 6 | VR 覆盖度仪表盘展示 | P1 | 质控 | QCDashboard 查看 |
| 7 | 工时三级粒度填报 | P0 | 助理 | WorkHoursPage 填报 |
| 8 | 工时预算对比柱状图 | P1 | 经理 | WorkHoursPage 查看 |
| 9 | 复核分派推荐人选展示 | P1 | 经理 | 分派弹窗查看 |
| 10 | 工时审批含底稿进度列 | P1 | 经理 | 审批页面查看 |
| 11 | 复核状态 SSE 实时通知 | P0 | 助理 | 提交复核后等待通知 |
| 12 | 多项目紧急度排序正确 | P0 | 合伙人 | PartnerDashboard 查看 |
| 13 | 联动全景图 stale 过滤器 | P1 | 合伙人 | LinkagePanorama 操作 |
| 14 | Word 导出三线表格式正确 | P1 | 质控 | 打开 Word 验证样式 |

上线门槛：P0 全 ✓ + UAT 真实验收通过 + 关键回归零失败

---

### 术语表

| 术语 | 定义 |
|------|------|
| **EQCR** | Engagement Quality Control Review，项目质量控制复核（独立复核） |
| **判断维度** | EQCR 独立复核的 5 个标准化评估领域：重大错报风险/持续经营/关键审计事项/其他信息/审计报告 |
| **eqcr_snapshots** | EQCR 快照表（Phase 4 创建），存储冻结的项目数据供 EQCR 只读查看 |
| **IssueTicket** | 统一问题单模型（Phase 15），支持 11 种 source 类型 |
| **source='eqcr'** | 本 spec 新增的 IssueTicket source 值，标识 EQCR 专属问题单 |
| **三线表** | 学术/审计报告标准表格格式：仅顶线+表头底线+底线，无竖线 |
| **VR 覆盖度标准** | 每循环至少 3 条 blocking + 2 条 warning 规则 |
| **WorkHourEntry** | 本 spec 新增的工时填报模型，支持三级粒度 |
| **三级粒度** | 工时填报的三个精度级别：循环级 > 底稿级 > 程序级 |
| **budget_config** | 项目预算配置（JSONB），按循环/按人员分配工时预算 |
| **urgency_score** | 项目紧急度评分（0-100），基于 SLA+VR+底稿三维加权 |
| **SSEEventType** | 前端 SSE 事件类型联合类型，镜像后端 EventType 枚举 |
| **review.accepted** | 本 spec 新增 SSE 事件：复核人已接收待复核底稿 |
| **review.completed** | 本 spec 新增 SSE 事件：复核人已完成复核 |
| **stale 子图** | 联动全景图中 is_stale=true 节点 + 一跳邻居构成的子图 |
| **ForceGraph** | D3.js 力导向图组件（联动全景图 spec） |
| **LinkagePanoramaView** | 联动全景图视图（合伙人/质控使用） |
| **ReviewWorkbench** | 复核工作台视图（项目经理/合伙人使用） |
| **NotificationCenter** | 前端通知中心组件（DefaultLayout 顶栏） |
| **python-docx** | Python Word 文档生成库 |
| **knowledge_base** | 知识库模块（全局+项目级文档管理） |
| **ProjectAssignment** | 项目团队委派模型，含 project_id + staff_id + role |
| **WpReviewStatus** | 底稿复核状态枚举（Phase 6 扩展支持 2-4 级） |
| **DashboardAggregatorService** | 合伙人仪表盘聚合服务（asyncio.gather 5 子查询） |
| **QCDashboard** | 质控仪表盘视图 |
| **EqcrMetrics** | EQCR 指标仪表盘视图 |

---

## 八、附录

### A. Sprint 规划概览（~20 天 / 5 Sprint）

| Sprint | 天数 | 功能 | 说明 |
|--------|------|------|------|
| Sprint 0 | 1 | 基线实测 | 填充 §三.C 所有"待实测"变量 |
| Sprint 1 | 4 | F1 + F2 + F3 | EQCR 体验三件套 |
| Sprint 2 | 4 | F4 + F5 + F6 | QC 质控体验三件套 |
| Sprint 3 | 5 | F7 + F8 + F9 + F10 | 工时管理增强四件套 |
| Sprint 4 | 3 | F11 + F12 + F13 | 复核通知 + 合伙人视角 |
| Sprint 5 | 3 | PBT + 回归 + UAT | 正确性属性 + 全量回归 + 验收 |

### B. 迁移需求

| 迁移 | 内容 | 说明 |
|------|------|------|
| V009（或 max+1） | eqcr_snapshots 表新增 `judgments` JSONB 列 | F1 结构化判断存储 |
| V010（或 max+1） | 新增 work_hour_entries 表 | F7 工时填报 |
| V011（或 max+1） | projects 表新增 `budget_config` JSONB 列 | F8 预算配置 |
| V012（或 max+1） | 新增 review_templates 表 | F4 复核意见模板 |

注：迁移编号实施时需动态确定 max+1，此处为占位。

### C. 回归影响白名单

- `eqcr_snapshot_service.py` — F1 扩展 snapshot_data 结构（新增 judgments 字段）
- `IssueTicket.source` 枚举 — F2 新增 `eqcr` 值（需确认 source 字段是否为 DB 枚举或应用层字符串）
- `SSEEventType` 联合类型 — F11 新增 3 个事件类型
- `eventBus.ts` Events 类型 — F11 需同步更新
- `ForceGraph.vue` — F13 新增 staleOnly prop（需确保现有交互不受影响）
- `PartnerProjectDashboard.vue` — F12 新增紧急度排行卡片
- `knowledge_base.py` router — F4 新增 review_templates 分类端点

### D. 功能依赖注记

- **F1 depends on Phase 4 eqcr_snapshots**：结构化判断存储在 snapshot_data.judgments 中
- **F2 depends on Phase 15 IssueTicket**：复用问题单模型，新增 source='eqcr'
- **F2 depends on Phase 6 F4**：EQCR 问题单可见性判断需要项目级权限端点
- **F9 depends on F7**：推荐算法的"当前工时余量"维度依赖工时填报数据
- **F10 depends on F7**：工时审批页面依赖工时填报模块
- **F12 复用 Phase 6 F7 urgency_score 算法**：评分公式一致，仅聚合维度不同（合伙人看多项目）

---

*本文档基于《平台全局建议书》E-2/E-3/E-4 + Q-3/Q-4/Q-5 + W-1/W-2/M-2/M-5 + RV-3 + P-2/P-4 共 14 项需求编制。预计 ~20 天跨 5 Sprint 实施。*
