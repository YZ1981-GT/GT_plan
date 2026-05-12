# 审计平台全局打磨建议 v2（深度续篇）

**编制人**：资深合伙人（平台治理方向）
**日期**：2026-05-07
**范围**：5 角色视角 + 21 个全局横切主题 + 联动穿透闭环 + 数值/字体/显示 3 条治理线
**前提**：v1 路线图 P0-P2 已基本落地（R7 Sprint 1-3），本文不再重复
**目标**：在 v1 基础上，**深化业务闭环 / 收敛视觉一致性 / 补齐长期维护性**

> v1 定位：盘点问题、列路线图
> v2 定位：针对"v1 落地后仍残留的结构性断层"给出**可直接进 Spec 三件套**的方案

---

## 0 v1 落地核查（先不吹牛，先盘家底）

v1 共提出 28 项路线图任务。按 grep 实测，截至 2026-05-07 状态：

| # | v1 任务 | v1 承诺 | 真实状态 | 证据 |
|---|---------|---------|---------|------|
| 1 | 删除 ReviewInbox.vue | P0 | ✅ 已删 | fileSearch 零命中 |
| 2 | 修复 PartnerDashboard/QCDashboard 硬编码 | P0 | ✅ | grep `/api/` 仅 1 处（QCDashboard:314），Partner 已迁 apiPaths |
| 3 | EqcrMetrics 对 eqcr 角色开放 | P0 | ✅ | DefaultLayout:131 已含 `eqcr` |
| 4 | 登录角色跳转 | P0 | ✅ | Login.vue 已按角色路由 |
| 5 | MobileXxx 整体删除 | P0 | ✅ | 5 个 mobile 视图零命中 |
| 6 | /confirmation 路由修复 | P0 | ⚠️ **未做** | 侧栏 `confirmation` 仍指 `/confirmation`，但 routes 未注册此路径 |
| 7 | 侧栏 navItems computed 化 | P1 | ✅ | `ThreeColumnLayout.vue:360` computed + roles 字段过滤 |
| 8 | confirm.ts 补齐 + 全局替换 ElMessageBox | P1 | ⚠️ **部分** | confirm.ts 已存在（5 函数），但 `.vue` 里仍有 **30+ 处** `ElMessageBox.confirm` 直接用 |
| 9 | useEditMode 全接入 | P1 | ⚠️ **4 处** | Materiality/AuditReportEditor/Adjustments 已接，其他编辑视图未覆盖 |
| 10 | WorkpaperEditor + DisclosureEditor 统一 useWorkpaperAutoSave | P1 | ✅ | 已统一 60s |
| 11 | 工时填报/审批 Tab 合并 | P1 | ✅ | WorkHourApprovalTab 已合并 |
| 12 | AI 死代码清理 | P1 | ✅ | ContractAnalysis/EvidenceChain 已删 |
| 13 | AiContentConfirmDialog 去重 | P1 | ✅ | 仅 `components/ai/` 一份 |
| 14 | GtPageHeader Sprint（6→73） | P2 | ⚠️ **12/86** | TrialBalance/ReportView/Disclosure/Consol/Eqcr/Knowledge/Miss/Projects/Materiality/AuditReport/Adjustments/WpList = 12 个，仍远未覆盖 |
| 15 | statusMaps → dictStore 收敛 | P2 | ✅ | statusMaps.ts 已删，GtStatusTag 唯一数据源 dictStore |
| 16 | QC 主工作台升级 + 项目级 QC Tab 化 | P2 | ❌ **未做** | QCDashboard.vue 仍独立路由，QcInspectionWorkbench 未升级为 Hub |
| 17 | EQCR 5 Tab 影子对比组件 + 备忘录版本 | P2 | ❌ **未做** | ShadowCompareRow 组件未见，memo history 未实装 |
| 18 | WorkpaperSidePanel 统一右栏 | P2 | ❌ **未做** | WorkpaperEditor 右栏仍内联 |
| 19 | 客户主数据 + 项目标签 | P2 | ❌ **未做** | ClientMaster 模型未建 |
| 20 | v-permission 全按钮铺设 | P2 | ⚠️ **5 处** | 仅 5 个 .vue 文件用，核心操作（签字/归档/审批/转错报）未加 |
| 21 | 附件预览抽屉组件化 | P2 | ❌ **未做** | AttachmentPreview 仍散落 |
| 22 | Ctrl+K 全局搜索 | P3 | ❌ 未做 | |
| 23 | vitest 基建 | P3 | ❌ 未做 | package.json 无 vitest |
| 24 | 暗色模式激活 | P3 | ❌ 未做 | displayPrefs 无 theme 字段 |
| 25 | 客户承诺结构化 | P3 | ✅ | 已升级为数组 + commitments/{id}/status PATCH |
| 26 | 员工热力图 + 跨项目成本 | P3 | ❌ 未做 | |

**P0：7/7 做完**；**P1：6/7 做完**（9 号只做一半）；**P2：2/8 做完**（15、25）；**P3：0/5**。

### v2 聚焦

v2 不重复上表已完成项，重点拣起：
- **P2 未完成块**（组件铺设、QC Hub、EQCR 对比、v-permission、客户主数据）
- **P1 做一半的**（confirm 替换、useEditMode 覆盖）
- **v1 完全没覆盖的维度**（见 §0.3）

### 0.3 v1 未覆盖或太浅的维度（v2 新增）

| 主题 | v1 深度 | v2 要做 |
|------|---------|---------|
| 数值处理（单位/精度/舍入/负数/零值/货币符号） | 薄 | 成体系 |
| 四表↔未审↔审定↔底稿↔分录↔附注 **完整联动闭环** | 只讲穿透入口 | 画全业务图 + 断点盘点 |
| 字体字号硬编码存量 | 已识别 | **量化清单 + 分阶段迁移** |
| 复制粘贴跨模块一致性 | 提到 | 具体规范 |
| 表单校验（FormRule 复用） | 未提 | 专章 |
| 错误提示三层（Message/Notification/Alert）边界 | 未提 | 专章 |
| 前端容灾（后端 5xx/断网/超时/幂等） | 未提 | 专章 |
| 操作历史 Ctrl+Z 范围扩展 | 一句话 | 实装方案 |
| 权限矩阵可视化（给 admin 看） | 未提 | 专章 |
| 日志/审计/追溯（审计师自己的操作留痕） | 弱 | 专章 |
| 业务术语一致性（"底稿" vs "工作底稿" vs "WP"） | 未提 | 建词表 |

---

## 1 当前系统量化快照（2026-05-07 实测，已 grep 核对，不靠记忆）

### 1.1 规模

| 维度 | 数值 | 备注 |
|------|------|------|
| 前端视图 | **86** 个 `.vue`（含子目录） | v1 记 73 已过时；根目录 68 + ai/ + eqcr/ + qc/ + independence/ + extension/ |
| 前端组件 | **194** 个 `.vue` | v1 记 186 已过时 |
| 后端路由 | **147** 个 `.py`（含 eqcr/ 子目录） | 服务/模型按 memory |
| GtPageHeader 接入 | **12/86** 视图 (14%) | KnowledgeBase/Misstatements/Projects/Materiality/TrialBalance/ReportView/DisclosureEditor/ConsolidationIndex/EqcrMetrics/AuditReportEditor/Adjustments/WorkpaperList |
| GtEditableTable 接入 | **0** | 组件存在但无任何视图用 |
| GtInfoBar 接入 | 9 视图 | Misstatements/Materiality/TrialBalance/ReportView/Disclosure/Adjust/Consol/... |
| v-permission 接入 | **5** `.vue` | WorkpaperEditor/UserManagement/TemplateManager/StaffManagement/Adjustments |
| useEditingLock 接入 | **3** 编辑器 | WorkpaperEditor（后端锁）/DisclosureEditor（前端检测）/AuditReportEditor（前端检测） |
| usePenetrate 接入 | **2** 视图 | TrialBalance/ReportView |
| ElMessageBox.confirm 直接用法 | **30+ 处** | 8 个合并工作表组件 + 7 个 view + 10+ 个 component |
| Vue 层 `/api/` 硬编码 | **17 处**（Vue 根目录） | 已接近尾声，触碰即修 |

### 1.2 显示一致性（本次 grep 新发现）

| 项 | 现状 |
|----|------|
| 内联 `font-size: Npx` | WorkpaperWorkbench **20+ 处** / WorkpaperList **10+ 处** / WorkpaperEditor 5 处 / TrialBalance 4 处 |
| 内联 `color: #xxxxxx` | WorkpaperList **20+ 处**（紫 #4b2d77、橙 #e6a23c、红 #FF5149、灰 #999/#666/#333 等混用） |
| 内联 `background: #f0f9eb/#fdf6ec` | WorkpaperList / TrialBalance，未用 `var(--gt-color-*-light)` |
| 混用 `var(--gt-*)` 和 `#xxx` | WorkpaperWorkbench 70% 已用 token，30% 仍硬编码 |

**判断**：v1 §2.13 定的"结构性字号用 CSS 变量"规则没有落地执行。`WorkpaperList.vue` 和 `WorkpaperWorkbench.vue` 是两个重灾区。

### 1.3 业务闭环断点（v1 没画全的）

下一段"联动穿透"会单独画。先给结论：**断点 4 处**

1. **AJE/RJE 被拒 → 错报表**：后端服务已通（`misstatement_service.create_from_rejected_aje`），GateRule 已注册，但**前端 Adjustments.vue 无"一键转错报"按钮**（grep 确认，只有"删除"+"查看"操作，没有 `convert_to_misstatement` 入口）。
2. **底稿改数 → 试算表 → 报表 → 附注**：事件链已在 `event_handlers.py:173` 订阅，但前端 `workpaper.is_stale` 三态（consistent/stale/inconsistent）**只在 TrialBalance 显示**，其他视图看不到。
3. **报表行 → 底稿映射**：`report_related_workpapers.py` 端点已建（R7），但 ReportView.vue 里只接了 2 个金额列点击，附注编辑器 DisclosureEditor 未接。
4. **重要性变更 → 错报阈值 → GateRule 阻断**：`materiality:changed` 事件已发布，但 Misstatements.vue 和 gate_readiness_panel 之间没有订阅链；重要性一改，错报显示立刻变但 GateRule 不一定立刻重跑。

---

## 2 五角色总览（v2 聚焦的断层）

这一轮不是"全角色全面铺开"，而是**每个角色挑 2-3 个 v1 未解决的结构性问题**深挖。

| 角色 | v1 已解决 | v2 本轮深挖 |
|------|-----------|-------------|
| 审计助理 | 登录跳转、Dashboard 待办、确认文案 | **底稿编制全流程连贯性** / **未保存提醒时机** / **AI 协作边界** |
| 项目经理 | 工时 Tab 合并、承诺结构化 | **跨项目成本/进度单一视图** / **团队健康度指标** |
| 质控人员 | 规则试运行、路由注册 | **QC Hub 真落地（v1 P2 未做）** / **抽查样本的自动化采集** |
| 合伙人 | 硬编码、签字落地 | **签字决策面板** / **合规溯源快速定位** |
| EQCR | 工作台、独立性阻断 | **影子对比（v1 P2 未做）** / **备忘录版本与导出** / **与项目组的非对称信息边界** |

每个角色一节。先出第二段（审计助理）。

---

## 3 审计助理（auditor）——深化底稿编制全流程

### 3.1 底稿编制的"七节车厢"目前是断的

一个助理从接任务到底稿归档，要走的节车厢：

```
① 接任务（委派） → ② 读程序要求 → ③ 看上年底稿 → ④ 预填充/OCR → ⑤ 编制 → ⑥ 自检 → ⑦ 提交复核
```

每节车厢的现状（grep 核对）：

| 节 | 组件/端点 | 现状问题 |
|---|----------|---------|
| ① 接任务 | `BatchAssignDialog.vue` | 助理收到委派没系统通知（无事件推送，只能被动刷 Dashboard） |
| ② 读程序要求 | `MyProcedureTasks.vue` + `ProcedureTrimming.vue` | 程序要求与底稿**分离成两个视图**，助理编制时看不到原始要求 |
| ③ 看上年底稿 | `PriorYearCompareDrawer.vue` | 只在 WorkpaperWorkbench 接入，WorkpaperEditor（Univer 编辑器）没有 |
| ④ 预填充 | `prefill_engine.py` + `WorkpaperWorkbench.vue` 编制卡片 | 预填充只在"工作台"触发，进入"编辑器"后看不到 provenance 来源标记 |
| ⑤ 编制 | `WorkpaperEditor.vue`（Univer） | 右栏 AI 助手 + 程序要求 + 上年对比 + 附件 + 知识库 + 批注 **共 6 个来源**，但**没有统一右栏面板**（v1 §2.7 P2 未做）|
| ⑥ 自检 | `wp_fine_rules.py` + WorkpaperList 里的 `fineCheckResults` | 自检结果只在 WorkpaperList 看得到，**WorkpaperEditor 里看不到**，助理改完直接提交，到复核阶段才发现 |
| ⑦ 提交复核 | `WorkpaperEditor.vue:478` | 直接 PUT status=pending_review，没有走 GateRule 的助理专属就绪检查 |

### 3.2 核心建议

#### A. 统一 WorkpaperSidePanel（v1 P2 P19 升级，必须做）

**问题**：WorkpaperEditor.vue 右栏当前内嵌了 AiAssistantSidebar + smartTip 面板 + 版本列表，三者并列渲染，没有 Tab 切换，也看不到程序要求、上年对比、附件、知识库、批注。

**方案**：新建 `components/workpaper/WorkpaperSidePanel.vue`，Tab 式聚合右栏所有面板：

```
[🤖 AI] [📋 程序] [📜 上年] [📎 附件] [📚 知识库] [💬 批注] [🔍 自检] [📝 版本]
```

每个 Tab 是独立组件，懒加载（`v-if="active === 'xxx'"`），不是 `v-show`，避免初始化时拉 6 份数据。

锚点：
- `views/WorkpaperEditor.vue` 右栏（当前大概在 template 的 `.gt-wp-editor-side` 区块）
- 新建 `components/workpaper/WorkpaperSidePanel.vue`
- 新建 7 个子组件 `SideAiTab / SideProcedureTab / SidePriorYearTab / SideAttachmentTab / SideKnowledgeTab / SideCommentTab / SideFineCheckTab`（全部是轻封装，每个 80 行以内）

影响面：
- DisclosureEditor 和 AuditReportEditor 可复用同一 SidePanel（去掉 SideFineCheckTab），一处统一三个编辑器右栏。

#### B. 自检结果进 WorkpaperEditor（必须做）

当前 `wp_fine_rules.py` 的 `GET /api/projects/{pid}/fine-checks/workpaper/{wp_id}` 只在 `WorkpaperList.vue` 里被调用。

**改动**：
- 在 SidePanel 加"🔍 自检"Tab，进入 WorkpaperEditor 时自动调用
- 失败项可点击"定位"跳到具体单元格（Univer API 支持 `getActiveWorkbook().setActiveSheet(...).setActiveRange(...)`）
- 未通过的自检项数量显示在 Tab 标签上（badge）

#### C. 程序要求侧写（业务诉求更强）

**问题**：助理在 WorkpaperEditor 里编制，不知道这张底稿要回应哪些程序要求。打开 MyProcedureTasks 看又丢上下文。

**方案**：
- 后端新建 `GET /api/workpapers/{wp_id}/procedures`（按底稿映射的科目 + 循环取对应程序）
- 前端 SidePanel "📋 程序" Tab 展示：
  - 上方：该底稿关联的循环/科目要求
  - 中间：程序步骤清单（来自 `procedure_library`）
  - 下方：助理可打勾"已执行"，打勾写入 `ProcedureExecution`（表已存在）

这是 v1 §1.1 没提到的真实业务诉求。

#### D. "未保存提醒"的时机不对

**现状**：`useWorkpaperAutoSave` 60 秒静默保存，但助理关闭浏览器 / 切路由时没有拦截。

**证据**：`router/index.ts` 的 beforeEach 没有 "editor-dirty" 检查（grep 未见 `dirty` 相关守卫）。

**方案**：
1. `useWorkpaperAutoSave` 暴露 `isDirty` 标志
2. WorkpaperEditor 在 `onBeforeRouteLeave` 里调 `confirmLeave('底稿')`（v1 已有此函数）
3. 同时注册 `beforeunload` listener（浏览器关闭/刷新）
4. DisclosureEditor / AuditReportEditor 同样接入

#### E. 委派推送 & 反馈

**现状**：助理被委派底稿没有即时通知（NotificationCenter 只有审批/复核/系统类）。

**方案**：
- 后端 `assignment_service.batch_assign` 完成时发事件 `WORKPAPER_ASSIGNED`
- `notification_dispatch` 订阅此事件，给被委派者发 app notification（type='assignment'）
- NotificationCenter 新增"委派"类型 Tab
- 频率控制：同一人同一项目 5 分钟内合并推送（不要刷屏）

#### F. AI 协作边界（助理视角）

**问题**：v1 §2.17 只讲了组件清理，没讲**"AI 能帮助理干什么，不能干什么"**。

**边界**（合规角度，不能让 AI 代替审计师判断）：

| 能做 | 不能做 |
|------|--------|
| 根据试算表数据生成**叙述性说明**草稿（助理必须复核） | 直接写"审定数"（必须助理输入）|
| 从附件 OCR 提取关键字段 | 把 OCR 结果直接写入底稿（必须 confirm）|
| 解释准则/政策（知识库引用）| 直接做"是否舞弊"的判断 |
| 计算公式结果 | 代替实质性程序的结论 |
| 纠错/提示风险点 | 自动修改数据 |

**落地**：
- 所有 AI 生成的内容进 `wrap_ai_output`（已有）+ `confirmation_status='pending'`
- 助理在 WorkpaperEditor 内看到的 AI 内容必须带 **"AI 草稿 · 待确认"** 水印（`AiContentConfirmDialog` 已有）
- 水印样式统一：黄底虚线框，右上角 🤖 + "AI 草稿"
- **签字 Gate 增加**：底稿所有 AI 内容必须 `confirmation_status='confirmed'` 或 `rejected` 才能提交复核（目前 `AIContentMustBeConfirmedRule` 已注册到 sign_off，但未注册到 wp_submit_review；本 spec 新增注册）

### 3.3 不做

- 不给助理加"编辑其他人底稿"的权限（即使同项目）
- 不做"AI 一键填完整张底稿"（已在 v1 负面清单）
- 不在 WorkpaperEditor 里做"强制引导式"流程（助理可以跳步、可以并行）

### 3.4 验收点（UAT）

- [ ] 助理打开 WorkpaperEditor，右栏 Tab 切换顺畅，每个 Tab 初次点击才加载数据
- [ ] 自检失败项点击"定位"可跳到 Univer 指定单元格
- [ ] AI 生成内容有 "🤖 AI 草稿 · 待确认" 水印
- [ ] 底稿有未确认 AI 内容时，"提交复核"按钮 disabled + tooltip 提示原因
- [ ] 关闭浏览器/切路由时，有未保存修改会弹 confirmLeave

---

## 4 项目经理（manager）——跨项目成本/进度单一视图

### 4.1 现状断层（v1 未深挖）

v1 §1.2 提了"人员×项目矩阵"和"催办台"，但没讲**项目经理最核心的两件事**：

1. **跨项目统一 overview**：一个 manager 可能管 10 个项目，现在要点进每个项目的 ProjectDashboard 才看得到进度，manager_dashboard 路由有但**只聚合了"我负责项目的 TOP 指标"**，没有单项目钻取。
2. **预算管控**：`WorkHoursApproval.vue:314` 做了"超支警告"（v1 备忘），但那是**单人单项目**；manager 想看"这个季度我管的 10 个项目总预算使用进度"没地方。

### 4.2 建议

#### A. ManagerDashboard 升级为"经理驾驶舱"（而不是只显示进度条）

现状（readFile 核对）：`ManagerDashboard.vue` 是单表 overview + 承诺事项 Tab（R7 刚加）。

建议升级为 4 Tab：

```
[📊 项目矩阵] [⏱️ 团队成本] [💬 客户承诺] [🚨 异常告警]
```

- **📊 项目矩阵**：
  - 行：我管辖的项目
  - 列：进度% / 底稿数(完成/总) / 逾期底稿数 / 工时(已用/预算) / 风险事项数 / 签字阶段 / 下一节点
  - 每行可点击钻取到 ProjectDashboard
  - 后端端点 `GET /api/manager/projects/matrix`（聚合 `Project + WorkingPaper + WorkHour + IssueTicket`）

- **⏱️ 团队成本**：
  - 上方：年度/季度/月度切换
  - 中部：人员 × 项目 工时 heatmap（v1 §2.6 已提）
  - 下方：单人汇总表（姓名/已用工时/挂时率/所属项目数）
  - 后端端点 `GET /api/manager/team/cost-heatmap?period=quarter`

- **💬 客户承诺**：已落地，保留

- **🚨 异常告警**：
  - 聚合展示：预算超支项目 / 逾期底稿 / 卡住导入任务 / 签字阻塞项目 / 质控发现未整改
  - 每项带"处理"按钮跳转到对应页面
  - 端点 `GET /api/manager/alerts`

锚点：`views/ManagerDashboard.vue`（已有，改造），新建 `services/managerApi.ts`。

#### B. 预算管控（项目经理最关心的一条线）

**现状**：
- `Project.budget_hours` 字段存在（需 grep 确认，可能在 `wizard_state` 里）
- `WorkHour.hours` 累计已用工时
- 没有**预算 vs 实际**的统一展示

**方案**：
1. `Project` 增加 `budget_hours_config` JSONB（按循环/阶段分预算）
2. 新建端点 `GET /api/projects/{pid}/budget/overview` 返回 `{by_cycle: [...], by_stage: [...], by_member: [...], total_used: X, total_budget: Y}`
3. ProjectDashboard 增加"预算"Tab，双环图（外环总进度，内环当前阶段）
4. ManagerDashboard "团队成本" Tab 每行显示超支比例
5. GateRule 可选增加 `BudgetOverrunWarningRule`（超 120% 时**警告**不**阻断**）——manager 自决

#### C. 委派前的"人员容量检查"

**现状**：`BatchAssignDialog.vue` 选人就委派，没提示"该人手上已有多少底稿"。

**改动**：
- BatchAssignDialog 在人员下拉选项旁显示 badge "已持有 8 张待办底稿"
- 选超过 15 张时弹警告：`"[name] 手上已有 X 张未完成底稿，是否继续委派？"`
- 阈值可配置：`settings.max_concurrent_workpapers_per_staff` 默认 15

锚点：`components/assignment/BatchAssignDialog.vue`，后端端点 `GET /api/staff/{id}/current-load`。

### 4.3 不做

- 不给 manager 直接修改其他 manager 项目的权限
- 不做"AI 自动委派底稿"（审计师必须判断人选）
- 不做"按成本自动分配"（违反审计师独立裁量）

### 4.4 验收点

- [ ] manager 登录进 /dashboard/manager（已验证）
- [ ] 项目矩阵可直接看到每个项目的"下一节点"和"签字阶段"
- [ ] 团队成本 heatmap 可切换周期
- [ ] 委派前看得到人员已持有底稿数
- [ ] 预算 vs 实际可视化

---

## 5 质控（qc）——QC Hub 真落地 + 抽查样本自动化

### 5.1 v1 P2 P16 未做的事

v1 建议过"QC Hub"和"项目级 QC Tab 化"，R7 没做。本 spec 必须落地。

### 5.2 建议

#### A. QcHub.vue（新建）—— v1 方案升级

路由 `/qc` 默认命中 `QcHub.vue`（admin/qc/partner 可见）。布局：

```
┌── 今日关注（卡片组）────────────────────┐
│ [本月应抽查项目: N]  [逾期整改: M]        │
│ [高风险客户: K]       [规则预警: L]        │
└────────────────────────────────────────┘
┌── 主工作区（4 Tab）──────────────────────┐
│ [待抽查 | 抽查中 | 整改中 | 已完结]       │
└────────────────────────────────────────┘
┌── 侧边（快捷入口）──────────────────────┐
│ → 规则管理 → 案例库 → 年报                │
│ → 客户趋势 → 批次执行报告                  │
└────────────────────────────────────────┘
```

实现：
- 复用 `QcInspectionWorkbench` 的批次执行逻辑
- 复用 `ClientQualityTrend` 的图表组件
- 新建 `QcHub.vue` 作为外壳 + router 添加

#### B. 项目级 QC 下沉为 Tab

`views/QCDashboard.vue` 是独立路由 `/projects/:id/qc-dashboard`。问题：
- 路径和 `/qc/*` 分成两套
- manager/partner 进项目主页要再点"质控"按钮才到

**改**：
- QCDashboard.vue 降级为 `ProjectDashboard.vue` 内的一个 Tab "质控"
- 删除独立路由 `/projects/:id/qc-dashboard`
- router.push 保留别名重定向避免旧链接失效

#### C. 抽查样本的自动化采集

**现状（重点问题）**：`QcInspectionWorkbench.vue` 抽查时 "选项目→执行规则"，但**规则执行完之后**，发现"这个底稿有问题"，怎么拿到底稿原文件看？当前流程：人工去 WorkpaperList 搜。

**改**：
- 抽查批次执行完成后，`QCInspectionFinding` 自动填入 `evidence_refs: [{wp_id, cell_ref, snapshot_path}]`
- 前端 finding 详情支持"查看底稿原文件"一键跳转（打开 WorkpaperEditor 只读模式 + 高亮单元格）
- 若底稿已被后续修改，跳转时提示"当前为最新版本，v3 是抽查时版本"

锚点：
- `backend/app/services/qc_engine.py` 执行每条规则时记录 `evidence_refs`
- `QcInspectionWorkbench.vue` 发现项行添加"查看"按钮

#### D. 规则试运行后的"影响面"预览

**现状**：v1 提了"规则保存前必须试运行"，已落地（`hasRunDryRun` flag）。

**增强**：试运行结果增加**影响面预览**：
- 命中项目数 X、命中底稿数 Y、命中具体清单（前 100 条可展开）
- 预估执行时间（基于上次批次的采样）
- **若命中数 > 某阈值（如项目 30%），弹红色警告**：规则可能过严

锚点：`views/qc/QcRuleEditor.vue` 试运行结果展示区。

#### E. 规则版本 + 灰度开关

**现状**：`QcRuleDefinition` 表有 `enabled` 字段，但修改规则没版本记录。

**改**：
- `QcRuleDefinition` 增加 `version` int + `version_history` JSONB
- 每次保存前打 snapshot
- "启用"分两档：`enabled=False` / `enabled=staging`（只生成 findings 不阻断）/ `enabled=production`
- 前端 QcRuleEditor 加 "灰度"按钮

### 5.3 不做

- 不给 QC "一键整改所有 finding"（每条要人判断）
- 不做"AI 自动写 QC 报告"（合规敏感）
- 不把 QC Rule 写回 Git 源码库（数据即配置）

### 5.4 验收点

- [ ] qc 登录默认进 /qc（QcHub）
- [ ] 项目级 QC 作为 ProjectDashboard Tab，不再有独立路由
- [ ] 规则试运行显示影响面
- [ ] 规则可设 staging 灰度
- [ ] Finding 可直接跳原底稿高亮

---

## 6 项目合伙人（partner）——签字决策面板 & 合规溯源

### 6.1 现状断层（v1 未深挖）

v1 §1.4 已提硬编码修复、签字全景 Tab、私库分区、轮换状态。本轮深挖：

1. **签字决策链路长**：合伙人签一个字要看 → GateReadinessPanel 全绿 → 打开 AuditReportEditor 核对意见段 → 打开 PDF 预览 → 进 ArchiveWizard 流程。**4 个页面切换**。
2. **合规溯源"我签过什么"**：合伙人一年签 100+ 个报告，想查"3 月 15 日 A 客户报告签字时我看过哪些资料"——现在查不到。
3. **签字前的 AI 辅助风险提示**：合伙人不会去读每张底稿，但**需要系统告诉他"这个项目有 3 个高风险事项未解决"**。

### 6.2 建议

#### A. 签字决策面板（新建独立视图）

路由 `/partner/sign-decision/:projectId/:year`（partner/admin 可见）。单页聚合：

```
┌── 项目基础信息 ──────────────────────────┐
│ 客户名/审计意见/EQCR 结论/签字阶段        │
└────────────────────────────────────────┘
┌── 左栏 (40%) ─── 中栏 (40%) ── 右栏 (20%)┐
│ 就绪检查        │ 报告预览    │ 风险摘要 │
│ GateReadiness   │ (PDF)      │ AI 生成  │
│ Panel（互动式） │             │ 10 条   │
│                 │             │ 顶级风险 │
└────────────────────────────────────────┘
┌── 底栏操作 ──────────────────────────────┐
│ [回退到复核] [签字] [查看历史] [打印]      │
└────────────────────────────────────────┘
```

关键点：
- 就绪检查失败项点击可跳对应修复页（复用 `GateReadinessPanel`）
- PDF 实时预览（iframe 嵌入 LibreOffice 渲染结果）
- 风险摘要用 `GET /api/projects/{pid}/risk-summary`（聚合：未解决复核意见 + 高风险 finding + 重要错报 + AI 洞察 top-5）
- "签字"按钮走 `SignatureService.sign`，成功后 Toast 大提示 "✍️ 已签字 · A 客户 2024 年度"

锚点：新建 `views/PartnerSignDecision.vue`，`router/index.ts` 加 `/partner/sign-decision/:projectId/:year`。

#### B. 我的签字历史（合规溯源）

**新视图** `/partner/sign-history`：
- 纵轴：时间
- 横轴：客户 × 签字级别
- 每条签字记录可展开看"签字时的就绪检查快照 + 报告 PDF hash + 看过的资料清单"
- **关键**：要有"签字时点快照"——而不是"现在的项目状态"

实现：
- `SignatureRecord` 表新增字段 `context_snapshot` JSONB（签字时的 gate_readiness_result + ai_risk_summary + final_report_pdf_hash）
- `SignatureService.sign()` 在写 SignatureRecord 时一并 snapshot
- 前端支持按客户/日期筛选，导出 CSV 用于事务所合规存档

#### C. 风险摘要（签字前必读）

合伙人不想看完所有底稿，但**一定要看"这个项目有什么我不知道的"**。

`GET /api/projects/{pid}/risk-summary` 返回：
```json
{
  "high_findings": [...],         // 未解决的高风险发现
  "unresolved_comments": [...],   // 未解决的复核意见
  "material_misstatements": [...], // 超过重要性的错报
  "unconverted_rejected_aje": [...],// 被拒 AJE 未转错报
  "ai_flags": [...],              // AI 模型识别的异常（如序时账异常）
  "budget_overrun": true,         // 预算超支
  "sla_breached": [...],          // Q 整改单超期
  "going_concern_flag": false     // 持续经营问题
}
```

前端 `PartnerSignDecision` 右栏展示。若任一 `high_findings / material_misstatements / unconverted_rejected_aje / going_concern_flag` 非空，**签字按钮 disabled + tooltip**。

这些检查**有的**已经是 GateRule，但**集中摘要展示**是新的。

#### D. 签字前 / 签字后的"确认对话框"规范

**问题**：当前签字流程没有"最终确认对话框"，点击"签字"直接写 DB。

**改**：
- 点击"签字"弹二次确认框：
  ```
  您即将以 [partner] 身份签字 [A 客户 2024 年度审计报告]。
  签字一旦完成将：
  1. 不可撤销（只能通过撤回流程）
  2. 触发 AuditReport.status = final
  3. 锁定底稿、报表、附注编辑
  
  请输入 [A客户] 确认：______
  [取消] [确认签字]
  ```
- 文案要求输入客户名全称（不能打勾了事，防止误点）
- 签字后大 Toast + 跳 `/partner/sign-history`

### 6.3 不做

- 不做"partner 越权编辑底稿"（即使自己项目）
- 不做"签字后自动发邮件给客户"（走人工发信）
- 不做"一键签字所有待签项目"（合规零容忍）

### 6.4 验收点

- [ ] 签字决策面板单页可完成判断
- [ ] 风险摘要若有红项，签字按钮 disabled
- [ ] 签字二次确认必须输入客户名
- [ ] 签字历史可查到"当时看到的数据"

---

## 7 项目独立复核合伙人（EQCR）——影子对比真落地

### 7.1 v1 P2 P17 未做的事

v1 承诺的两个关键组件没做：
- **ShadowCompareRow.vue**（项目组值 vs 影子值并排对比）
- **EQCR 备忘录版本历史 + 独立 Word 导出**

### 7.2 建议

#### A. ShadowCompareRow 组件（v1 方案 + 补充）

新建 `components/eqcr/ShadowCompareRow.vue`，3 列布局：

```vue
<!-- 使用示例 -->
<ShadowCompareRow
  label="整体重要性"
  :team-value="800000"
  :shadow-value="750000"
  unit="元"
  :threshold-pct="10"
  :verdict="currentVerdict"
  @verdict-change="onVerdictChange"
/>
```

展现：
```
整体重要性:
  项目组值: 800,000 元         影子值: 750,000 元
  差异: -50,000 元 (-6.3%)    [✓ 在阈值内] 或 [⚠ 超出 10% 阈值]
  我的判断: [○通过] [●标记异常] [○需要讨论]  [备注: ____]
```

- `team-value` / `shadow-value` 为空时显示 "—"
- 差异超过 `threshold-pct` 高亮红色
- 判断写入 `EqcrVerdict`（表已存在，R5 落地）
- 备注 200 字内，onBlur 自动保存

**应用到 5 Tab**：materiality / estimate / related_party / going_concern / opinion_type，每 Tab 顶部放 1-3 个 ShadowCompareRow。

#### B. 备忘录版本历史

`Project.wizard_state.eqcr_memo` 扩展为：
```json
{
  "sections": { "background": "...", "scope": "...", ... },
  "status": "draft|finalized",
  "history": [
    {
      "version": 1,
      "saved_at": "2026-05-01T10:00:00Z",
      "saved_by": "uuid",
      "saved_by_name": "张某某",
      "sections_snapshot": { /* 完整 sections 快照 */ },
      "change_note": "补充独立性考虑"
    },
    // ... 最多 10 条
  ]
}
```

前端 `EqcrMemoTab.vue`（或 panels/memo）：
- 顶部增加"版本"下拉，选择后右侧以只读视图显示历史版本
- 下拉默认"当前（draft/finalized）"
- 超过 10 版时 FIFO 丢弃最老
- 每次保存前弹小对话框可选填"本次变更说明"（非必填）

后端：`eqcr_memo_service.save_memo(pid, sections, change_note)` 处理 history 追加。

#### C. 独立 Word 导出

后端新建 `GET /api/eqcr/projects/{pid}/memo/export?format=docx`：
- 复用 phase13 `note_word_exporter` 同款 python-docx 模板
- 模板结构：封面 + 项目基本信息 + 各 section + 影子对比结果表 + 我的判断汇总 + 签名日期
- 文件名 `EQCR备忘录_{客户名}_{年度}_{saved_at}.docx`

前端 `EqcrMemoTab` 增加"📄 导出 Word"按钮，调 `downloadFileAsBlob`。

#### D. EQCR 与项目组的"非对称信息"规范

**问题（合规敏感）**：EQCR 可以看项目组全部底稿/报表/附件，但反过来，EQCR 的独立笔记和影子计算**不应该默认对项目组可见**。

现状（readFile EqcrReviewNotesPanel）：
- EqcrReviewNote 有"分享给项目组"按钮（手动，好）
- 影子计算结果 `EqcrShadowCompute` 默认**只 EQCR 可读**（需确认后端 ACL）

**必须**：
- EqcrShadowCompute 的后端端点 ACL 只允许 `role in ['eqcr', 'admin']`
- EqcrReviewNote 未分享时同样 ACL
- 审计日志记录"谁看过 EQCR 数据"（字段 `last_accessed_by` + `last_accessed_at`）

#### E. EQCR Tab 切换状态保留

v1 §1.5 E 已提到用 keep-alive。本轮**确认落地**：
- `EqcrProjectView.vue` 的 `<el-tabs>` 外层包 `<keep-alive>`
- 或每个 Tab 子组件内部使用 `defineExpose` 把状态存 Pinia（防止 keep-alive 导致内存膨胀）

### 7.3 不做

- 不给 EQCR 修改项目组底稿的权限（只读 + 独立判断）
- 不做"EQCR 备忘录直接进最终报告"（备忘录归档包里独立章节，不流入报告）
- 不做"EQCR 多人协作"（单人负责制）

### 7.4 验收点

- [ ] 5 Tab 每个都有 ShadowCompareRow
- [ ] 备忘录可切换历史版本查看
- [ ] 备忘录可独立导出 Word
- [ ] 影子数据非 EQCR 角色访问返回 403
- [ ] 切 Tab 不丢状态

---

## 8 横切主题（v2 版）

本章 21 个主题，每个主题都有**当前状态证据 + 方案 + 锚点 + 不做**。

### 8.1 全局组件铺设（深化 v1 §2.1）

#### 8.1.1 量化现状（本次 grep 实测）

| 全局组件 | views/ 接入数 | 总 .vue 数 | 渗透率 |
|---------|-------------|-----------|-------|
| GtPageHeader | 12 | 86 | 14% |
| GtInfoBar | 9 | 86 | 10% |
| GtToolbar | ~10 | 86 | 12% |
| GtStatusTag | ~15 | 86 | 17% |
| GtAmountCell | ~6 | 86 | 7% |
| GtEditableTable | 0 | 86 | 0% |
| GtEmpty | 2 | 86 | 2% |
| CellContextMenu | 4 | 86 | 5% |
| SelectionBar | 2 | 86 | 2% |
| SyncStatusIndicator | 3 | 86 | 3% |

**结论**：v1 P2 的组件铺设 Sprint **未真正完成**。只有少数几个"标杆页"做了。

#### 8.1.2 分批计划（一次做不完，分 3 批）

**批次 A：高频交易页（1 周）**
| 视图 | 缺什么 |
|------|--------|
| WorkpaperWorkbench.vue | 自写 banner + toolbar + 右栏全部硬编码，改造最重 |
| WorkpaperEditor.vue | 无 GtPageHeader（用原生 header）+ 右栏未 SidePanel 化 |
| AttachmentHub.vue + AttachmentManagement.vue | 未接任何 Gt 组件，且两者重复 |
| ReviewWorkbench.vue | 无 GtPageHeader，收件箱风格与他页不一致 |

**批次 B：数据编辑类（1 周）**
| 视图 | 缺什么 |
|------|--------|
| CFSWorksheet.vue | 无 GtPageHeader |
| SubsequentEvents.vue / SamplingEnhanced.vue | 同上 |
| ConsolSnapshots.vue / ConsolidationHub.vue | 同上 |
| KnowledgeBase.vue 子页 | 主页有 Gt，子页无 |

**批次 C：看板/设置类（1 周）**
| 视图 | 缺什么 |
|------|--------|
| Dashboard.vue / PersonalDashboard.vue / ManagementDashboard.vue | 都没 GtPageHeader（用自己的 banner） |
| SystemSettings.vue / TemplateManager.vue / AIModelConfig.vue | 同上 |
| PerformanceMonitor.vue / ReportFormatManager.vue / ReportConfigEditor.vue | 同上 |

#### 8.1.3 GtEditableTable 必须用起来

现状：该组件存在但**没有一个视图使用**（v1 已点名但没推）。

候选试用场景（低风险）：
- `Materiality.vue` 的重要性参数表（5-10 行，属性简单）
- `AuxSummaryPanel.vue` 的辅助表
- `ConsolScope.vue` 的合并范围表

先让 1-2 个视图成功接入，沉淀最佳实践，再推到 Adjustments / Misstatements 这种复杂编辑表。

#### 8.1.4 CI 卡点

- 新增 lint 规则：统计每个新 PR 的"GtPageHeader 接入率"，低于基线（如 14%）阻塞
- 新增 script `scripts/check-component-adoption.mjs`，纳入 pre-commit

#### 8.1.5 不做

- 不搞"一次性全量迁移"（风险巨大）
- 不强制所有视图必须用 Gt 组件（列表/弹窗内嵌可保留自写）
- 不改 Gt 组件的 API（已稳定，破坏式变更代价高）

---

### 8.2 弹窗/消息/Toast 的三层规范（v1 未成体系）

#### 8.2.1 现状

前端有 4 种提示方式并存：
- `ElMessage`（顶部横幅 Toast，2 秒自动消失）
- `ElMessageBox.confirm/alert/prompt`（模态确认）
- `ElNotification`（右上角悬浮卡，4 秒）
- `utils/confirm.ts`（封装的 5 个语义化函数）

**问题**：开发者按自己喜好用，用户体验不一致。例如删除走 `confirmDelete` 弹层，但"切换操作"走 `ElMessageBox.confirm`，两种弹窗视觉风格不同。

#### 8.2.2 分层规范

**第一层：轻量反馈（ElMessage）—— 2 秒自动消失**
- 成功：保存成功、导入成功、复制成功
- 普通信息：已跳转、已复制 N 条

**第二层：持续反馈（ElNotification）—— 5 秒+ 可关闭**
- 后台任务完成：导入完成、归档完成、PDF 生成完成
- 异步通知：新复核意见、新委派
- 警告：预算超支、SLA 即将超期

**第三层：中断性确认（ElMessageBox → 必须通过 utils/confirm.ts）—— 用户必答**
- 删除：`confirmDelete(name, type)`
- 批量操作：`confirmBatch(action, count)`
- 危险操作：`confirmDangerous(action, consequence)`
- 离开页面：`confirmLeave(moduleLabel)`
- 版本冲突：`confirmVersionConflict(serverVer, localVer)`（新增）
- 签字确认：`confirmSignature(clientName, reportType)`（新增）

#### 8.2.3 消灭直接 ElMessageBox.confirm 调用

当前 grep 结果：**30+ 处直接 `ElMessageBox.confirm`**，分布：

| 类别 | 文件 | 处 |
|------|------|----|
| 合并工作表组件 | 8 个 *Sheet.vue | 16 |
| 底稿/编辑器 | WorkpaperList/WorkpaperEditor | 2 |
| 合并面板 | ConsolNoteTab/ReportLineMappingStep | 2 |
| 导入向导 | AccountImportStep/DataImportPanel | 4 |
| 布局 | MiddleProjectList/DetailProjectPanel | 4 |
| EQCR | EqcrReviewNotesPanel/EqcrRelatedParties | 4 |
| 独立性 | IndependenceDeclarationForm | 1 |
| 公式 | StructureEditor | 1 |
| 上年对比 | PriorYearCompareDrawer | 1 |
| 其他 | Adjustments | 2 |

**方案**：扩展 `utils/confirm.ts`：

```ts
// 新增 7 个函数
confirmDelete(name, type?)           // 已有
confirmBatch(action, count)          // 已有
confirmDangerous(action, consequence)// 已有
confirmLeave(moduleLabel)            // 已有
confirmRestore(target)               // 已有

// 新增
confirmVersionConflict(server, local): Promise<'refresh' | 'override' | 'cancel'>
confirmSignature(clientName, reportType): Promise<boolean>
confirmForceReset(context): Promise<boolean>
confirmRollback(version): Promise<boolean>
confirmShare(target, audience): Promise<boolean>
confirmDuplicateAction(prevResult): Promise<boolean>
confirmForcePass(reason): Promise<{confirmed: boolean, note: string}>
```

每个语义化函数内部**视觉风格 + 按钮文案 + 图标**统一。

**CI 卡点**：grep `ElMessageBox\.confirm` 直接调用数，设基线 30，只减不增。

#### 8.2.4 Message/Notification 使用规范

`utils/feedback.ts`（新建）：

```ts
export const feedback = {
  success(msg: string) { ElMessage.success(msg) },
  info(msg: string) { ElMessage.info(msg) },
  warning(msg: string) { ElMessage.warning(msg) },
  error(msg: string, detail?: string) {
    ElMessage.error({
      message: msg,
      duration: 4000,
      showClose: true,
    })
    if (detail) console.warn('[feedback.error]', detail)
  },

  // 持续性通知（后台任务、长时提醒）
  notify(opts: {
    title: string
    message: string
    type?: 'success' | 'warning' | 'info' | 'error'
    duration?: number
    onClick?: () => void
  }) {
    ElNotification(opts)
  },
}
```

所有新代码走 `feedback`；`ElMessage.xxx` 直接调用在 CI 里 warn（不阻断，逐步迁）。

#### 8.2.5 不做

- 不替换 Element Plus 的底层 API（仅封装）
- 不加音效（合规/干扰）
- 不把 Toast 改成右上角（与产品设计不符）

---

### 8.3 数值处理（v1 未展开的重点）

#### 8.3.1 当前现状（grep 核对）

| 工具 | 位置 | 用途 |
|------|------|------|
| `utils/formatters.ts::fmtAmount` | ✅ 已存在 | 带单位、千分位、小数位 |
| `stores/displayPrefs.ts::fmt(v)` | ✅ 已存在 | 跟单位/小数位/零值/负数红 设置 |
| `stores/displayPrefs.ts::unitFactor` | ✅ 已存在 | 元/千元/万元/百万转换 |
| `GtAmountCell.vue` | ✅ 已存在 | 接入率 7% |
| 各视图里的 `fmt(v)` 本地函数 | ⚠️ 大量存在 | TrialBalance/ReportView/Consol 都有本地 `fmt` |

#### 8.3.2 问题

- **"元转千元"的单位切换**在不同视图行为不一致：
  - TrialBalance 切单位后**重新渲染**（刷新数据）
  - Adjustments 切单位后**只改显示**（原始数据不变）
  - Materiality 的阈值输入框**永远以"元"为单位**（不跟单位切换）
  - Misstatements 的错报金额**显示跟单位，输入时弹框用元**

这种不一致源于"没有全局规范"。

#### 8.3.3 规范

**NumberHandling.md**（新规范文档，放 `.kiro/conventions/`）：

**R1: 存储统一用"元"**
- DB 所有金额字段：以"元"存储，float/numeric
- 后端 API 返回值：以"元"返回
- 前端 `displayPrefs.unit` 只影响**展示**，不影响**输入和传输**

**R2: 展示走 GtAmountCell 或 displayPrefs.fmt**
- 禁止本地 `fmt(v)` 函数（grep 找出现存 15+ 个，统一删除）
- 表格内金额列必须 `<GtAmountCell :value="..." />`
- 卡片/统计数字用 `{{ displayPrefs.fmt(amount) }}`

**R3: 输入始终以"元"为单位**
- 输入框的数字**永远是元**
- 如果显示单位是"万元"，输入框旁边用灰字提示 "× 10000 = 元"
- `@blur` 时校验
- 决策：**不做"万元输入"**（容易错，1.23 万元变 1.23 元的误操作不值得）

**R4: 精度和舍入**
- 后端精度：保留 2 位小数（元到分）
- 展示精度：跟 `displayPrefs.decimalPlaces`（0/1/2/3）
- 舍入：**四舍五入**（不是银行家舍入）
- 合并/汇总：后端先算后端显示层取整，避免"行加起来不等于合计"的舍入误差

**R5: 负数和零值**
- 负数：跟 `displayPrefs.negativeRed`（红色）和 `displayPrefs.negativeStyle`（`(123)` 括号 / `-123` 减号）
- 零值：跟 `displayPrefs.showZero`（true=显示"0"，false=显示"—"）
- `<GtAmountCell>` 已支持这些，**但大量视图没用它**

**R6: 货币符号**
- 默认无符号（财务表纯数字）
- `displayPrefs.showCurrencySymbol` 可开 "¥"
- 多币种：项目级 `Project.currency` 字段（本位币），外币交易用 `ExchangeRate` 转换（已有 `forex.py` router）

**R7: 百分比**
- 统一保留 2 位小数 + "%"
- `formatPercent(v, decimals=2)` 工具函数（新增到 formatters.ts）
- 进度条/完成率展示用

#### 8.3.4 迁移清单

| 视图 | 现状 | 要做 |
|------|------|------|
| TrialBalance / ReportView / ConsolidationIndex | 本地 fmt | 改用 GtAmountCell |
| Adjustments / Misstatements | 本地 fmt | 改用 GtAmountCell |
| Materiality | 输入框乱 | 统一元输入 |
| Dashboard 顶部卡片 | 本地 fmt | 改 displayPrefs.fmt |
| EqcrShadowCompareRow | 新组件 | 用 GtAmountCell |

#### 8.3.5 不做

- 不做"每个字段自定义单位"（复杂度爆炸）
- 不做"万/亿 自动切换"（审计师习惯统一单位）
- 不做"中文数字"（壹拾贰万）

---

### 8.4 字体字号一致性（量化清单）

#### 8.4.1 现状（本次 grep 实测）

| 指标 | 数值 |
|------|------|
| `font-size: Npx` 在 views/ 内联/样式块 | **约 90+ 处** |
| 硬编码 `#xxxxxx` 颜色在 views/ | **约 70+ 处** |
| `var(--gt-font-size-*)` 变量覆盖 | 大量用了但不彻底 |

最糟糕 3 个文件：
1. `WorkpaperWorkbench.vue`（banner + AI 右栏 + 检查清单）约 25 处硬编码
2. `WorkpaperList.vue`（内联 style 拼接风险评估、复核意见、审计检查）约 20 处
3. `WorkpaperEditor.vue` 约 5 处

#### 8.4.2 规范（升级 v1 §2.13）

**Tier 1: 允许硬编码的场景**
- banner 里的 title（`h2 / h3`）：纯结构，可直接 `font-size: 18px` 或用 `var(--gt-font-size-lg)`
- emoji 图标：`font-size: 16-20px`
- ErrorBoundary 大字：OK

**Tier 2: 必须用 CSS 变量**
- 表格内字号：`var(--gt-font-size-table)` 绑定 displayPrefs
- 导航字号：`var(--gt-font-size-nav)`
- 正文：`var(--gt-font-size-base)`
- 说明性小字：`var(--gt-font-size-xs)`

**Tier 3: 必须禁止**
- 内联 `style="font-size:11px;color:#666"` 这种连体硬编码
- `style` 属性里的十六进制颜色

#### 8.4.3 CI 卡点

新建 `scripts/check-hardcoded-styles.mjs`：

```js
// 扫描 views/**/*.vue
// 匹配 style="..." 或 <style scoped> 块内
//   - font-size:\s*\d+px（除 TITLE_ALLOWED 白名单）
//   - color:\s*#[0-9a-fA-F]{3,6}（非 token）
//   - background:\s*#[0-9a-fA-F]{3,6}（非 token）
// 输出：总违规数 + Top 10 文件 + Top 10 视图
// 基线模式：超过上次则 fail
```

纳入 `ci.yml` frontend-build job。基线值：当前约 160 处，目标每周减 20 处。

#### 8.4.4 字体降级链（v1 已提但要写死）

`styles/gt-tokens.css` 的 `--gt-font-family` 当前：

```
'GT Walsheim', 'FZYueHei', 'Microsoft YaHei', 'PingFang SC', 'Helvetica Neue', Arial, sans-serif
```

建议扩展：
```
'GT Walsheim', 'FZYueHei',
'Microsoft YaHei', 'PingFang SC', 'Noto Sans CJK SC',
'Helvetica Neue', 'Segoe UI', Arial, sans-serif;
```

理由：
- `Noto Sans CJK SC`：Linux/Docker 环境兜底
- `Segoe UI`：Windows 10/11 默认英文字体

**数字用 tabular-nums**（已在金额单元格用，推广到所有表格列）：
```css
.gt-tabular { font-variant-numeric: tabular-nums; }
```

#### 8.4.5 字号大小档位

当前：11/12/13/14 四档。

**补充**：加"舒适/紧凑/大字"三档预设：

| 预设 | 表格 | 正文 | 标题 |
|------|------|------|------|
| 紧凑 | 11 | 13 | 16 |
| 标准（默认）| 12 | 14 | 18 |
| 舒适 | 13 | 15 | 20 |
| 大字（老花眼）| 14 | 16 | 22 |

`displayPrefs.sizePreset = 'compact' | 'standard' | 'comfortable' | 'large'`

顶栏"Aa"面板一键切换预设，而不是逐项调。

#### 8.4.6 不做

- 不支持无障碍模式（另立主题）
- 不做用户自定义字体（只改 family）
- 不做"按内容动态字号"（如数字大自动小字，太复杂）

---

### 8.5 四表-未审-审定-底稿-调整分录-附注 联动穿透闭环（业务核心）

这是用户在需求里明确点名要的一块，v1 只讲了穿透入口，没画全链路。**这是审计平台的心脏**。

#### 8.5.1 完整闭环图

```
                                                                    
          ┌───────────────────────────────────────────────┐          
          │          ① 序时账（ledger_entries）             │          
          │   LedgerImport 后生效，客户原始数据               │          
          └───────────────┬───────────────────────────────┘          
                          │ aggregate                                
                          ▼                                          
          ┌───────────────────────────────────────────────┐          
          │        ② 试算表-未审数（trial_balance）          │          
          │   LedgerDataset → TB（标准科目映射）              │          
          └───────────────┬───────────────────────────────┘          
                          │                                           
         ┌────────────────┼─────────────────────┐                    
         │                │                     │                    
         ▼                ▼                     ▼                    
 ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐           
 │ ③ 底稿编制   │  │④ 调整分录     │  │⑤ 重分类分录       │           
 │ WorkingPaper │  │ Adjustment   │  │ (Reclassification)│           
 │（按科目/循环）│  │ (AJE/RJE)    │  │                  │           
 └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘           
        │                 │                   │                       
        │                 │被拒 → ⑥ 错报       │                       
        │                 │                   │                       
        │                 ▼                   │                       
        │      ┌─────────────────────┐       │                       
        │      │ ⑥ 未更正错报        │       │                       
        │      │ UnadjustedMisstate  │       │                       
        │      └─────────────────────┘       │                       
        │                                    │                       
        └────────────────┬───────────────────┘                       
                         │ 合并计算                                   
                         ▼                                           
          ┌───────────────────────────────────────────────┐          
          │       ⑦ 试算表-审定数（TB summary）             │          
          │ 审定=未审+AJE借-贷+RJE借-贷                    │          
          └───────────────┬───────────────────────────────┘          
                          │                                           
         ┌────────────────┼─────────────────────┐                    
         ▼                ▼                     ▼                    
 ┌──────────────┐ ┌──────────────┐  ┌──────────────────┐            
 │⑧ 资产负债表  │ │⑨ 利润表      │  │⑩ 现金流量表        │            
 │  BS report   │ │ IS report    │  │ CFS worksheet    │            
 └──────┬───────┘ └──────┬───────┘  └────────┬─────────┘            
        │                │                   │                       
        └────────────────┼───────────────────┘                       
                         │                                           
                         ▼                                           
          ┌───────────────────────────────────────────────┐          
          │        ⑪ 附注（disclosure_notes）              │          
          │ 29 section，引用报表行+底稿数据                  │          
          └───────────────┬───────────────────────────────┘          
                          │                                           
                          ▼                                           
          ┌───────────────────────────────────────────────┐          
          │        ⑫ 审计报告（audit_report）              │          
          │ 意见段、强调事项段、责任段引用附注章节           │          
          └───────────────────────────────────────────────┘          
                                                                    
```

#### 8.5.2 穿透入口全量清单（当前实现 grep 核对）

| 从 | 到 | 端点 / 组件 | 前端入口 | 状态 |
|----|-----|------------|---------|------|
| 报表行 | 底稿 | `GET /api/reports/{pid}/{year}/{type}/{row}/related-workpapers` | ReportView 右键菜单 | ✅ R7 |
| 报表行 | 科目明细（公式展开） | `GET /api/reports/{pid}/{year}/{type}/drilldown/{row}` | ReportView 点金额单元格 | ✅ |
| TB 科目 | 序时账 | `GET /api/ledger/penetrate` + Drilldown.vue | TrialBalance 点科目名 | ✅ |
| TB 审定数 | 底稿 | TrialBalance wp_consistency 列的小图标 | 双击打开 WorkpaperEditor | ✅ |
| 按金额穿透 | 序时账 | `GET /api/projects/{pid}/ledger/penetrate-by-amount` | 右键"按金额查询" | ⚠️ 后端有，前端入口未统一 |
| AJE 被拒 | 错报 | `POST /api/projects/{pid}/adjustments/{id}/convert-to-misstatement` | Adjustments 行操作按钮 | ✅ R6 后端，R7 前端入口 |
| 错报 | 原分录 | `GET /api/misstatements/{id}/source-aje` | Misstatements 行操作 | ❓ 需确认 |
| 附注行 | 报表行 | DisclosureEditor 点引用 | ⚠️ R7 落地 | |
| 附注行 | 底稿 | `GET /api/notes/{note_code}/related-workpapers` | DisclosureEditor 右键 | ❌ 未实现 |
| 序时账 | 凭证/附件 | `GET /api/ledger/entries/{id}/voucher` | LedgerPenetration 行操作 | ⚠️ 部分 |
| 底稿 | 附件 | WorkpaperEditor SidePanel 附件 Tab | ✅ |

#### 8.5.3 4 个关键断点（影响业务闭环）

**断点 1：AJE 被拒 → 错报表没"一键转"入口**

**证据**：
- 后端 `misstatement_service.create_from_rejected_aje` 存在
- 后端 `UnconvertedRejectedAJERule` GateRule 注册到 sign_off
- 前端 `Adjustments.vue` grep **没找到 `convert_to_misstatement` 相关按钮**

**方案**：
- Adjustments.vue 行操作区，对 `review_status === 'rejected'` 的行显示"转为错报"按钮
- 点击调 `POST /api/projects/{pid}/adjustments/{id}/convert-to-misstatement`
- 成功后弹 confirm 询问"是否立即查看未更正错报表"

**断点 2：Stale 三态不跨视图显示**

**证据**：
- `WorkingPaper.is_stale` 字段 + event_handlers 级联更新
- `stale-summary` 端点已建（R7-S2）
- **但只有 TrialBalance 显示 `wp_consistency.status === 'stale'` 图标**
- ReportView / DisclosureEditor / AuditReportEditor 没显示

**方案**：
- 新建全局 composable `useStaleStatus(projectId, resourceType, resourceId)`
- 返回 `{isStale, upstreamChangedAt, refetch}`
- ReportView 顶部加 stale 提示横幅："上游数据已变更，建议点击重算 →"
- DisclosureEditor / AuditReportEditor 同理

**断点 3：附注行 → 底稿 的穿透未实现**

**证据**：
- DisclosureEditor 的 `<DisclosureTableEditor>` grep 无 `related-workpapers` 或 `penetrate` 调用
- 附注表格单元格点击不跳底稿

**方案**：
- 新端点 `GET /api/notes/{project_id}/{year}/{note_section}/row/{row_code}/related-workpapers`
- 前端 DisclosureEditor 右键菜单加"查看相关底稿"

**断点 4：重要性变更 → 错报阈值即时重算**

**证据**：
- `materiality:changed` eventBus 事件已发布
- Misstatements.vue grep **没订阅此事件**（未验证 `.on('materiality:changed', ...)`）
- GateRule 的 `MisstatementThresholdRule` 读 DB，不重跑

**方案**：
- Misstatements.vue `onMounted` 订阅 `materiality:changed`，刷新阈值
- 重算按钮：`POST /api/projects/{pid}/misstatements/recheck-threshold`
- GateReadinessPanel 订阅事件并自动 revalidate

#### 8.5.4 全局"数据血缘"快速追溯

**需求**：打开一张底稿，想知道"这张底稿的数据来自哪？我改了它会影响什么？"

**实现**：
- 后端维护 `data_lineage` 表：`{upstream_type, upstream_id, downstream_type, downstream_id, relation_type}`
- 事件处理器每次级联时写入 lineage
- 前端 `DataLineageDialog.vue`（新组件）显示血缘图（用 `gt-chart` 或简单树）
- WorkpaperEditor / TrialBalance / ReportView 右键可调出"查看数据血缘"

**不做**：
- 不做全图谱（复杂度爆炸）
- 只显示 3 层内的上下游

#### 8.5.5 验收点（闭环测试）

- [ ] 改一条底稿 → TB stale 标 → TB 重算 → BS/IS 数字更新 → 附注引用更新 → 审计报告签字提示"底稿变更，需重新复核"
- [ ] 拒一条 AJE → 转错报 → 未更正错报表出现此项 → 超重要性阈值 → GateRule 阻断签字
- [ ] 改重要性 → Misstatements 阈值线即时移动 → GateRule 重新评估
- [ ] 报表行右键查看底稿 → 单底稿跳转，多底稿列表

---

### 8.6 权限铺设（v1 §2.14 继续落地）

#### 8.6.1 现状

- `usePermission.ROLE_PERMISSIONS` 5 角色硬编码 + 后端 `user.permissions` 覆盖
- `v-permission` 指令 **只在 5 个 .vue 文件使用**（WorkpaperEditor/UserManagement/TemplateManager/StaffManagement/Adjustments）
- router meta `roles` / `permission` 已支持

#### 8.6.2 按钮级 v-permission 必须铺设的位置

根据业务影响，**必须加 v-permission 的按钮清单**（grep 核对当前未加的）：

| 动作 | 涉及视图 | 权限码建议 |
|------|---------|-----------|
| 删除项目 | MiddleProjectList / Projects | `project:delete` |
| 编辑底稿 | WorkpaperList / WorkpaperEditor | `workpaper:edit` |
| 提交复核 | WorkpaperEditor / WorkpaperList | `workpaper:submit_review` |
| 复核通过 | WorkpaperList / ReviewWorkbench | `workpaper:review_approve` |
| 复核退回 | 同上 | `workpaper:review_reject` |
| 转错报 | Adjustments | `adjustment:convert_to_misstatement` |
| 签字 | AuditReportEditor / PartnerSignDecision | `sign:execute` |
| 归档 | ArchiveWizard | `archive:execute` |
| 归档解锁 | ArchiveWizard | `archive:unlock` |
| 发布年报 | QcAnnualReports | `qc:publish_report` |
| 撤销签字 | SignatureManagement | `sign:revoke`（高危）|
| 导出最终报告 | AuditReportEditor | `report:export_final` |
| 编辑独立性声明 | IndependenceDeclarationForm | `independence:edit` |
| EQCR 审批 | EqcrWorkbench | `eqcr:approve` |
| 批量委派 | BatchAssignDialog | `assignment:batch` |
| 催办升级合伙人 | ProjectDashboard | `workpaper:escalate` |

脚本 `scripts/find-missing-v-permission.mjs`：grep 所有 `@click="on(Delete|Submit|Approve|Reject|Sign|Archive|Publish|Export|Convert|Escalate)"` 未加 `v-permission` 的行，输出报告。

#### 8.6.3 权限矩阵可视化（给 admin 看）

新建 `/admin/permission-matrix` 视图：

- 行：所有权限码（从 `usePermission.ROLE_PERMISSIONS` 抽取）
- 列：6 个角色
- 单元格：✓ / ✗ / 自定义 覆盖

admin 可编辑此矩阵（写入 User.permissions 或 Role.permissions）。

#### 8.6.4 后端权限自省端点

`GET /api/permissions/self` 返回当前用户：
- `permissions: ['workpaper:edit', ...]`
- `accessible_routes: ['/projects', '/my/dashboard', ...]`
- `role: 'auditor'`
- `effective_role: 'auditor'`

前端 `stores/permission.ts` 启动时调用，缓存。

#### 8.6.5 不做

- 不做多级角色继承（5 角色够用）
- 不做"权限代理"（partner 临时把权限给助理）
- 不做"按项目维度权限"（已有 ProjectAssignment.role，不要加第二层）

---

### 8.7 枚举/字典（v1 §2.10 已落地但补充）

#### 8.7.1 现状（已从 v1 前进）

- ✅ `statusMaps.ts` 删除
- ✅ GtStatusTag 唯一数据源 `dictStore`
- ✅ 后端 9 套字典

#### 8.7.2 v2 新发现问题

**问题 1：前端硬编码状态判断散在各处**

grep 示例：
- `WorkpaperList.vue` 里 `workflow_stage === 'reviewing'` 判断
- `ReportView.vue` 里 `status === 'final'` 判断
- 这些字符串没有全局常量对象，打字容易错

**方案**：`constants/statusEnum.ts`

```ts
export const WP_STATUS = {
  DRAFT: 'draft',
  PENDING_REVIEW: 'pending_review',
  REVIEWING: 'reviewing',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  ARCHIVED: 'archived',
} as const

export const REPORT_STATUS = {
  DRAFT: 'draft',
  REVIEW: 'review',
  EQCR_APPROVED: 'eqcr_approved',
  FINAL: 'final',
} as const

// ... 18 套状态常量
```

所有 `.vue` 里 `=== 'draft'` 等字符串比较**禁止硬编码**，必须用常量对象。CI lint 规则。

**问题 2：字典热更新**

后端 `system_dicts.py` 的 `/api/system/dicts` 返回字典。前端 dictStore 首次加载后**不再刷新**。

问题：admin 改了字典标签，前端看不到。

**方案**：
- 管理后台 "系统字典" 页增加"推送更新"按钮
- 后端 SSE 广播 `dict:updated` 事件
- 前端 dictStore 收到事件后重新拉取

#### 8.7.3 不做

- 不把枚举迁到 DB 可配置（影响代码强类型）
- 不做"多语言枚举"（中文 only）

---

### 8.8 年度（year context）—— v1 §2.11 深化

#### 8.8.1 现状

- URL query `?year=2024` 作为传递参数
- `stores/projectYear.ts`（需确认存在与否）
- 不同视图的默认年度不一致：有的取 currentYear、有的取 currentYear-1、有的取 project.financial_year

#### 8.8.2 问题

**grep 证据**：
- `TrialBalance.vue`：`year = Number(route.query.year) || new Date().getFullYear() - 1`（默认去年）
- `ReportView.vue`：同上
- `DisclosureEditor.vue`：`year.value || new Date().getFullYear() - 1`
- `Materiality.vue`：直接 route.query.year（无默认）

**问题**：审计师在 TB 看的是 2024，点 Materiality 可能切回 undefined，数据乱。

#### 8.8.3 规范

**R1: 全局 projectYear store**（新建，如果不存在）

```ts
// stores/projectYear.ts
export const useProjectYearStore = defineStore('projectYear', () => {
  const currentProjectId = ref('')
  const currentYear = ref(new Date().getFullYear() - 1)
  
  watch(currentYear, (y) => {
    eventBus.emit('year:changed', { projectId: currentProjectId.value, year: y })
  })
  
  return { currentProjectId, currentYear, setYear, setProject }
})
```

**R2: 所有视图从 store 读，不从 URL 读**

URL query 只作为"**进入时的初始值**"，之后以 store 为准。

**R3: 顶栏 GtInfoBar 是唯一年度切换入口**

`GtInfoBar :show-year="true"` 组件绑定 store。用户切年度 → store 更新 → 所有订阅视图 reload。

**R4: 跨视图导航保留年度**

`router.push` 时自动带 `?year=` query（用 router guard 统一注入）。

**R5: 某些视图"锁定年度"**

- ArchiveWizard 归档后，年度字段只读，不允许切
- 历史签字记录查看时，年度跟记录，不跟 store

#### 8.8.4 不做

- 不做"双年度并排对比"（用上年对比组件即可）
- 不做"跨会计期间"（只支持年度）

---

### 8.9 编辑模式（v1 §2.12 继续深化）

#### 8.9.1 现状

`useEditMode` composable 已存在，接入视图：
- Materiality.vue（已接）
- AuditReportEditor.vue（已接）
- Adjustments.vue（已接）
- DisclosureEditor.vue（已接，但用 useEditingLock 联动）

未接入（grep）：
- WorkpaperEditor.vue（Univer 天然编辑态，不适合 toggle）
- TrialBalance.vue（编辑审定数没有 toggle）
- ReportView.vue（某些场景下可编辑，未 toggle）
- CFSWorksheet.vue
- TemplateManager.vue
- ConsolNoteTab / 合并工作表系列

#### 8.9.2 规范

**分两类视图**：

**A: 编辑为主（WorkpaperEditor / Univer 类）**
- 进入即编辑
- 不用 useEditMode
- 用 useEditingLock 管锁（已落地）

**B: 查看为主，编辑为辅（TrialBalance / ReportView / 其他）**
- 默认查看
- 用 useEditMode toggle
- 切换到编辑时调用 `useEditingLock.acquire()`
- 关闭编辑时 `release()`

#### 8.9.3 视觉一致性

编辑中黄色横条（已有 .gt-edit-mode-ribbon）必须所有编辑视图统一。
- 浅黄底 `var(--gt-color-warning-light)`
- 左侧 ✏️ 图标
- 文案统一 "编辑中 · 请记得保存"

#### 8.9.4 不做

- 不做"逐单元格编辑"（太碎）
- 不做"自动退出编辑"（可能丢未保存数据）

---

### 8.10 复制粘贴（v1 §2.18 规范化）

#### 8.10.1 现状

- `useCellSelection` 单元格选择 composable
- `useCopyPaste` HTML+制表符双格式
- `CellContextMenu` 右键菜单
- `GtToolbar` "复制整表" 按钮
- `usePasteImport` 粘贴导入（Misstatements 已用）

**散落问题**：
- 不同视图复制按钮文案：「复制整表 / 复制全表 / 导出表格 / 复制」混用
- 右键菜单有的有「复制选中区域」，有的没有
- 粘贴板格式不统一（HTML/CSV/TSV）

#### 8.10.2 规范

**命名统一**：
- 工具栏按钮：「📋 复制整表」（复制所有行到剪贴板）
- 右键菜单：「📋 复制选中」（复制当前选中单元格/行）
- 导出按钮：「📥 导出 Excel」 / 「📥 导出 CSV」

**格式统一**：
- 复制到剪贴板：HTML（富文本表格，粘贴到 Excel/Word 保留格式） + TSV（制表符分隔纯文本）双格式
- 导出下载：Excel（.xlsx，后端生成）或 CSV（前端生成）

**粘贴导入规范**：
- 支持 Excel 复制的 HTML 格式和 TSV 纯文本
- 自动识别表头（第一行含中文名）
- 字段映射弹窗（用户确认哪列对应哪字段）
- 预览前 5 行 + 校验结果
- 批量写入前弹 `confirmBatch`

#### 8.10.3 需要接入 useCellSelection 的视图

当前 4 个（TrialBalance / ReportView / DisclosureEditor / ConsolidationIndex）。
建议扩展到：
- WorkpaperList（批量选行做批量委派/催办，已有但不统一）
- Misstatements / Adjustments（批量删除/审批）
- ConsolSnapshots（对比切换）

---

### 8.11 查询（v1 §2.15 深化）

#### 8.11.1 现状

- 顶栏"自定义查询"CustomQueryDialog 已有
- TableSearchBar 部分视图接入
- 无全局 Ctrl+K 搜索（v1 P3 未做）

#### 8.11.2 建议

**A. Ctrl+K 全局搜索** —— v1 P3 未做，本轮做

新建 `components/common/GlobalSearchDialog.vue`：
- 顶栏加 🔎 图标，Ctrl+K 唤起
- 搜索范围（可选 Tab）：项目 / 底稿 / 附注章节 / 附件名 / 知识库文档 / 最近操作
- 后端 `GET /api/search?q=xxx&scope=all&limit=20`
- 键盘导航（↑↓ Enter）
- 项目联想：模糊匹配客户名/项目编号
- 底稿联想：模糊匹配 wp_code / wp_name / 科目名

**B. URL query 驱动的筛选持久化**

所有列表视图的筛选条件存 URL：
```
/workpapers?status=draft&cycle=D&assignee=me
```

好处：
- 分享链接即分享筛选状态
- 浏览器前进后退可恢复
- 刷新不丢筛选

实现：
- Vue 3 `useUrlSearchParams` 或自封装 composable
- `WorkpaperList.vue` / `Misstatements.vue` / `Adjustments.vue` / `Projects.vue` 接入

**C. 保存视图（我的视图）**

- 筛选 + 列顺序 + 列显示 保存为命名视图
- 侧栏显示"我的视图"列表
- 表 `saved_views(user_id, scope, name, config)`
- 前端视图选择器下拉

---

### 8.12 知识库（v1 §2.16 继续）

#### 8.12.1 问题补充

**现状**：
- KnowledgeBase.vue 主页已 GtPageHeader 化（R7-S3-01 已做）
- WorkpaperEditor **无知识库入口**（v1 已提，仍未接）
- useKnowledge composable 只在 DisclosureEditor / AuditReportEditor 用

#### 8.12.2 建议

**A. WorkpaperEditor 接入 KnowledgePickerDialog**

右栏 SidePanel "📚 知识库" Tab：
- 首页显示按循环（D/E/F/...）聚合的知识文档列表
- 顶部搜索框（搜文档名/标签）
- 点击文档 → 右侧展示内容（Markdown 或富文本）
- 底部"插入到底稿"按钮 → 调 Univer API 写入当前活动单元格

**B. 按循环分类**

当前知识库目录结构灵活但审计员不习惯。建议预置一级：
- A 完成阶段
- B 风险评估
- C 控制测试  
- D 货币资金
- E 存货
- F 应收应付
- ... K/M/N 各循环
- S 特殊项目
- 通用

配合 `KnowledgeDocument.cycle_code` 字段。

**C. 引用追踪**

`KnowledgeReference` 表记录"谁在哪张底稿引用了哪篇知识文档"。
- 知识文档详情页显示"被 N 张底稿引用"
- 知识文档更新时通知引用者

---

### 8.13 对话聊天与 LLM 辅助（v1 §2.17 扩展）

#### 8.13.1 问题补充

v1 已清死代码。本轮聚焦**AI 协作的业务规范**。

#### 8.13.2 建议

**A. AI 上下文边界（合规必须做）**

每次 AI 调用的 prompt 构建**必须经过 `export_mask_service.mask_context`**（R4 已有），屏蔽：
- 客户名（替换为 `[client_N]`）
- 金额（> 10 万）替换为 `[amount_N]`
- 身份证/银行卡替换

**grep 核实**：
- `wp_chat_service.py` 已集成 mask_context
- `note_ai.py` / `wp_ai.py` 未确认，需补

**B. AI 水印强化**

所有 AI 生成的文本进底稿/附注/报告，必须：
- 内容前后加零宽字符标记
- 元数据记录 `ai_model / ai_confidence / generated_at`
- 最终报告 PDF 末尾附"AI 贡献声明"（R3 已有 `build_ai_contribution_statement`）

**C. AI 会话持久化（v1 P3 未做）**

- 新表 `ai_chat_sessions(id, user_id, project_id, wp_id, messages JSONB, created_at)`
- 端点 `GET /api/ai/sessions?project_id=xxx&wp_id=yyy`
- WorkpaperEditor SidePanel "🤖 AI" Tab 打开时加载历史 + 续聊
- 只保留最近 90 天

**D. AI 待确认聚合**

新建 `views/ai/AiContentInbox.vue`（v1 P3 未做）：
- 跨项目列出所有 `confirmation_status='pending'` 的 AI 内容
- 挂到 PersonalDashboard 一个 Tab
- 按"紧迫度"排序：签字阻塞的优先

**E. 角色差异化 AI 能力**

根据 `ROLE_AI_FEATURES`（已有）：
- auditor：助手 + 知识库 + OCR + 预填充
- manager：+ 风险预测 + 进度摘要
- qc：+ 规则撰写辅助 + 发现总结
- partner：+ 签字前风险摘要
- eqcr：+ 独立判断辅助（带严格水印）

前端 WorkpaperEditor 的 AI Tab 根据角色裁剪可用功能。

---

### 8.14 附件（v1 §2.8 深化）

#### 8.14.1 问题补充

当前附件入口 5 处：
- AttachmentHub.vue（全局）
- AttachmentManagement.vue（项目级）
- WorkpaperEditor 右栏（底稿附件）
- WorkpaperWorkbench 右栏（底稿附件 v2）
- AttachmentDropZone（拖拽组件）

**重复度高**。

#### 8.14.2 建议

**A. AttachmentHub / AttachmentManagement 合并**

现状（grep）：两者字段几乎一样，功能重叠。

**方案**：
- 保留 `AttachmentHub.vue`（路由 `/attachments`）
- 顶部加 Tab "全部 / 我上传的 / 未关联 / 回收站"
- 项目筛选、OCR 筛选、类型筛选全部可用
- 删除 `AttachmentManagement.vue`
- `/projects/:id/attachments` 路由重定向到 `/attachments?project_id=xxx`

**B. 附件预览抽屉组件（v1 P2 P21 未做）**

新建 `components/common/AttachmentPreviewDrawer.vue`：
- 支持 Office 三件套（docx/xlsx/pptx，调 LibreOffice PDF）
- 支持 PDF（内嵌 iframe 或 PDF.js）
- 支持图片/HTML
- 支持 OCR 结果展示（右侧抽屉）

所有"查看附件"按钮（4+ 处）统一调此抽屉。

**C. 附件与底稿的智能关联**

- 上传附件时，如果 OCR 识别到科目名/金额，提示"此附件可能属于底稿 D.XXX"
- 接受后自动写入 `workpaper_attachment_link`

**D. 附件空间/配额提示**

当前无配额概念。建议：
- 项目级配额 `Project.attachment_quota_mb`（默认 500MB）
- 顶部进度条提示使用率
- 超过 80% 警告，超过 100% 阻断上传（走回收站释放）

---

### 8.15 复核（v1 §2.9 深化）

#### 8.15.1 问题补充

v1 已清 ReviewInbox 死代码。本轮补充业务规范。

#### 8.15.2 建议

**A. 复核批注的两套机制边界**

**现状**：
- `ReviewRecord`：单元格级批注，绑定 `wp_id + cell_reference`
- `review_conversations`：跨对象多轮讨论

**业务规范**（要文档化）：
- **底稿单元格级**：用 ReviewRecord，支持针对单元格的红蓝笔标注
- **跨对象/整体讨论**：用 review_conversations，支持 @人 和 长文讨论
- 两者可通过 `conversation_id` 外键关联

**B. 复核工单的生命周期**

当前状态：open → in_progress → resolved → closed
问题：审计业务里"已回复但未解决"是常态，当前机制不区分。

**扩展**：
- `open` (新建未响应)
- `acknowledged` (被复核人已看)
- `replied` (已回复但未确认解决)
- `resolved` (复核人确认解决)
- `escalated` (升级到合伙人)
- `closed` (关闭不做)

**C. 复核意见的"转工单"**

`ReviewConversations.vue` 已有（根据 v1 §2.9），但"转工单"按钮当前状态**需确认**（grep 未见）。

**方案**：
- ReviewConversations / ReviewRecord 未解决项有"转工单"按钮
- 点击后转为 `IssueTicket(source='review_comment')`，走标准工单流程

**D. 复核逐条反馈 vs 批量驳回**

WorkpaperList 批量驳回已支持（R6），但**每条原因可不同**的需求：
- 批量驳回弹窗内每行独立填原因输入框
- 或"全部一个原因" + "逐条编辑"二选一

---

### 8.16 表单校验（v1 未提）

#### 8.16.1 现状

各视图用 `el-form` + `rules` prop 各写各的校验规则：
- 客户名长度 / 非空
- 金额正数 / 小数位数
- 日期范围
- 科目编码格式

grep 结果：同一种"客户名非空"的 rule 在 10+ 个视图里写了 10 份。

#### 8.16.2 方案

新建 `utils/formRules.ts`：

```ts
export const rules = {
  required: (label: string) => ({ required: true, message: `${label}不能为空`, trigger: 'blur' }),
  amount: { pattern: /^-?\d+(\.\d{1,2})?$/, message: '请输入有效金额（最多2位小数）', trigger: 'blur' },
  clientName: [
    { required: true, message: '客户名不能为空', trigger: 'blur' },
    { min: 2, max: 100, message: '长度 2-100 字符', trigger: 'blur' },
  ],
  accountCode: { pattern: /^\d{4,10}$/, message: '科目编码 4-10 位数字', trigger: 'blur' },
  email: { type: 'email', message: '邮箱格式错误', trigger: 'blur' },
  phone: { pattern: /^1\d{10}$/, message: '手机号格式错误', trigger: 'blur' },
  ratio: { pattern: /^(0|0\.\d+|1|1\.0+|[1-9]\d*|[1-9]\d*\.\d+)%?$/, message: '比例 0-100% 或 0-1', trigger: 'blur' },
}
```

所有 el-form 用 `:rules="{...}"` 组合引用。

---

### 8.17 错误处理与容灾（v1 未提）

#### 8.17.1 现状

- `utils/errorHandler.ts` 已有 `handleApiError`
- http interceptor 处理 401/403
- 5xx 没有统一用户提示
- 断网/超时无友好提示

#### 8.17.2 方案

**A. http interceptor 统一 5xx 处理**

`utils/http.ts` response interceptor：
```ts
// 5xx 统一提示
if (status >= 500) {
  feedback.notify({
    type: 'error',
    title: '服务器错误',
    message: '系统暂时无法响应，请稍后重试。错误 ID: ' + errorId,
    duration: 8000,
    onClick: () => copyToClipboard(errorId),
  })
}

// 网络超时
if (error.code === 'ECONNABORTED') {
  feedback.notify({
    type: 'warning',
    title: '请求超时',
    message: '网络连接缓慢，已停止等待。建议检查网络或稍后重试',
  })
}

// 断网
if (!navigator.onLine) {
  feedback.notify({
    type: 'warning',
    title: '网络已断开',
    message: '当前离线，保存将暂存本地，恢复后自动同步',
  })
}
```

**B. 幂等操作识别**

高危操作（删除、签字、归档）请求头带 `X-Idempotency-Key: <uuid>`：
- 后端识别重复请求，返回上次结果
- 防止用户双击按钮导致重复签字

**C. 前端操作重试队列**

对于保存、工时、复核意见等非关键操作，失败时：
- 存到 localStorage 队列
- 网络恢复时自动重试
- 顶栏显示"有 N 条未同步操作"

---

### 8.18 操作历史 Ctrl+Z（v1 §2.9 末尾略带）

#### 8.18.1 现状

`operationHistory` 单例已有，但**只对"删除"操作接入**：
- Adjustments 删除
- RecycleBin 操作

单元格编辑、数值修改、状态切换**不可撤销**。

#### 8.18.2 方案

**A. WorkpaperEditor Ctrl+Z**

Univer 自带 undo/redo（API：`getActiveWorkbook().undoRedoController.undo()`）。当前 shortcuts 已注册 `shortcut:undo` 但未连 Univer 的 undo，需要：

```ts
shortcutManager.on('shortcut:undo', () => {
  if (isFocusOnUniver()) univerApi.executeCommand('sheet.command.undo')
  else operationHistory.undo()
})
```

**B. 全局 operationHistory 扩展**

记录：删除、批量操作、状态切换、批量委派、批量催办。

数据结构：
```ts
{ type: 'delete', target: 'adjustment', id: 'uuid', snapshot: {...}, undoFn: () => {}, ts: Date }
```

撤销时调 `undoFn`（每种操作自带反函数）。

**C. 历史面板**

顶栏加"🕐 最近操作"，显示最近 10 条可撤销操作。

---

### 8.19 路由规范（v1 §3.1 深化）

#### 8.19.1 `/confirmation` 路由修复（v1 P0-07 未做）

**现状**：
- 侧栏 `confirmation` 指 `/confirmation`
- router 无此路径
- 点击会 404（非预期）

**方案**：
- 新建 `views/ConfirmationHub.vue`（stub）
- router 添加 `/confirmation` route with `meta.developing: true`
- 守卫触发跳转到 `/developing`

#### 8.19.2 路由 meta 完整性

脚本 `scripts/audit-routes.mjs` 扫描每条 route，输出：
```
路径 | name | component | requireAuth | developing | permission | roles | requiresAnnualDeclaration
```

CI 卡点：检查关键路由 meta 不缺。

#### 8.19.3 死路由清理

历次迭代残留的废弃路由 grep 扫描：
- `/review-workstation` 是否仍在？
- `/monitoring`？
- `/wopi/*` WOPI 兼容路由是否仍需要？

统一一次性清理。

---

### 8.20 测试基础设施（v1 §3.3 具体化）

#### 8.20.1 前端 vitest（v1 P3 未做）

装依赖：
```bash
npm install -D vitest @vue/test-utils jsdom @pinia/testing
```

`vite.config.ts` 添加 test 配置。

**最小单元测试清单**：
- `utils/formatters.ts`（fmtAmount/formatDate/parseExcelFormula）
- `utils/confirm.ts`（mock ElMessageBox，验证调用参数）
- `stores/displayPrefs.ts`（fmt / unitFactor 计算）
- `stores/dict.ts`（label / type / options 查询）
- `composables/usePermission.ts`（can / hasRole 判断）
- `composables/useEditMode.ts`（toggle 状态转移）

**目标**：一周内铺出 50 个单元测试，CI 加 `npm run test:unit` job。

#### 8.20.2 E2E（Playwright）

长期目标。至少跑 5 条关键路径：
- 登录 → 助理看板
- 新建项目 → 导入账套 → 看试算表
- 编辑底稿 → 提交复核 → 复核通过
- 签字 → 归档
- EQCR 独立性声明 → EQCR 工作台

---

### 8.21 术语/文案一致性（v1 未提）

#### 8.21.1 现状

同一对象多种叫法：
- "底稿" / "工作底稿" / "WP" / "审计底稿"
- "复核" / "审阅" / "检查"
- "客户" / "被审计单位" / "被审单位"
- "项目" / "客户项目" / "审计项目"
- "附注" / "报表附注" / "财务附注"
- "科目" / "会计科目"

#### 8.21.2 规范

新建 `docs/GLOSSARY.md`（术语表）：

| 标准词 | 同义词（禁用）| 场景说明 |
|--------|-------------|---------|
| 底稿 | 工作底稿、WP | 正式文档统一"底稿" |
| 复核 | 审阅、检查 | audit 场景统一"复核" |
| 客户 | 被审计单位、被审单位 | 正式场合可用"被审计单位"，UI 用"客户" |
| 项目 | 客户项目、审计项目 | UI 统一"项目" |
| 附注 | 财务附注、报表附注 | UI 统一"附注" |
| 科目 | 会计科目 | UI 统一"科目" |

所有新 UI 文案必须过术语表。CI 可选加 lint。

---

### 8.22 文档治理（v1 §3.4 具体化）

#### 8.22.1 memory.md 拆分

v1 已点出 memory.md 超 200 行问题。当前 **仍 350+ 行**。

**自动化**：
- 新建 hook `memory-split.json`（`eventType: promptSubmit`，当 memory.md 行数 > 200 时触发）
- 提示"建议将已完成项迁移到 dev-history.md"

**人工操作**：
- 每轮打磨结束立即迁移到对应子文档
- memory.md 保留"最近 3 轮状态 + 活跃待办"

---

### 8.23 项目（project）主数据（v1 §2.3 深化）

#### 8.23.1 客户主数据

**现状**：每个 Project 都有 `client_name` 字符串，重复输入易错。

**方案**：
- 新表 `clients(id, name, short_name, industry, entity_type, ...)`
- `Project.client_id` 外键
- 项目创建向导优先"选客户"，没有则"新建客户"

#### 8.23.2 项目标签

- 新表 `project_tags(id, name, color)`
- 多对多 `project_tag_links`
- 筛选/搜索支持

#### 8.23.3 项目克隆

`POST /api/projects/{id}/clone-from/{prev_id}`
- 继承科目映射、人员委派、重要性配置、试算表 template
- 不继承数据

---

### 8.24 人员（staff）与工时（v1 §2.4/2.5 深化）

#### 8.24.1 履历

- StaffMember 增加 JSONB `resume`（教育/经历/证书/技能）
- StaffManagement "简历"按钮打开 Drawer 展示
- 支持编辑和上传 PDF

#### 8.24.2 能力评价

- 复用 `CompetenceRating` 表
- 每项目结束后由 manager/partner 评价
- StaffManagement 显示综合评价趋势

#### 8.24.3 工时挂时率

- `挂时率 = 总计费工时 / (总计费工时 + 非计费工时)`
- Dashboard 顶部卡片显示
- 按周/月统计

#### 8.24.4 工时模式切换

- 手动填报：现状
- 计时模式：`WorkHour.status='tracking'`，start/stop 按钮
- 自动记录：基于 WorkpaperEditor 停留时长（焦点追踪隐私保护，只本地存储）

---

---

## 9 优先级与落地路线图（v2 版）

### 9.1 按"业务价值 × 实施成本"排序

> 格式：价值 H/M/L × 成本 H/M/L ，H×L = 必做
> 所有 v1 未完成或 v2 新加的点

#### P0（1 周内做，零风险高收益）

| # | 任务 | 章节 | 工作量 |
|---|------|------|--------|
| 1 | `/confirmation` 路由修复 | §8.19.1 | 30 分钟 |
| 2 | confirm.ts 补齐 7 个函数 + 替换所有 ElMessageBox.confirm | §8.2 | 半天 |
| 3 | Adjustments 增加"转错报"按钮 | §8.5.3 断点 1 | 2 小时 |
| 4 | stores/projectYear.ts + 顶栏 GtInfoBar 统一年度 | §8.8 | 1 天 |
| 5 | http interceptor 5xx / 超时 / 断网统一提示 | §8.17 | 半天 |
| 6 | AI 输入 mask_context 全路径审计（note_ai/wp_ai 补齐） | §8.13.2 A | 半天 |

**合计**：3 天

#### P1（2-4 周，中风险）

| # | 任务 | 章节 |
|---|------|------|
| 7 | WorkpaperSidePanel 统一 7 Tab 右栏 | §3.2 A |
| 8 | 自检结果进 WorkpaperEditor | §3.2 B |
| 9 | 程序要求进 WorkpaperEditor | §3.2 C |
| 10 | Stale 三态跨视图显示 + useStaleStatus | §8.5.3 断点 2 |
| 11 | ShadowCompareRow 组件 + 5 Tab 接入 | §7.2 A |
| 12 | EQCR 备忘录版本历史 + Word 导出 | §7.2 B/C |
| 13 | 合伙人签字决策面板 PartnerSignDecision | §6.2 A |
| 14 | 风险摘要端点 + 右栏展示 | §6.2 C |
| 15 | ManagerDashboard 四 Tab 升级 | §4.2 A |
| 16 | QcHub.vue + 项目级 QC 下沉 Tab | §5.2 A/B |
| 17 | v-permission 关键按钮铺设（15+ 处） | §8.6.2 |
| 18 | 常量 statusEnum.ts 替换硬编码状态字符串 | §8.7.2 |
| 19 | utils/formRules.ts 统一表单校验 | §8.16 |
| 20 | utils/feedback.ts 封装 Message/Notify | §8.2.4 |

#### P2（1-2 月，需 spec 三件套）

| # | 任务 | 章节 |
|---|------|------|
| 21 | Gt 组件全量铺设批次 A/B/C（86 视图） | §8.1 |
| 22 | 金额处理全量迁 GtAmountCell | §8.3.4 |
| 23 | 硬编码字体字号/颜色 CI 卡点 + 逐步清理 | §8.4 |
| 24 | Ctrl+K 全局搜索 | §8.11 A |
| 25 | URL query 驱动筛选持久化 | §8.11 B |
| 26 | 附件 Hub/Management 合并 + 预览抽屉 | §8.14 |
| 27 | 客户主数据 + 项目标签 | §8.23 |
| 28 | 跨项目预算 overview | §4.2 B |
| 29 | 签字历史 context_snapshot | §6.2 B |
| 30 | 数据血缘可视化 | §8.5.4 |
| 31 | 风险摘要 AI flags 数据血缘 | §8.5.4 |
| 32 | QC 规则灰度机制 + 影响面预览 | §5.2 D/E |

#### P3（半年内，长期投入）

| # | 任务 | 章节 |
|---|------|------|
| 33 | vitest 单元测试基建 + 50 个测试 | §8.20.1 |
| 34 | Playwright E2E 5 条关键路径 | §8.20.2 |
| 35 | 暗色模式激活 | v1 §2.13 D |
| 36 | 操作历史全范围 Ctrl+Z | §8.18 |
| 37 | AI 会话持久化 + 待确认聚合 | §8.13.2 C/D |
| 38 | 权限矩阵可视化 admin 页 | §8.6.3 |
| 39 | 术语表 + CI lint | §8.21 |
| 40 | 知识库引用追踪 | §8.12.2 C |
| 41 | memory.md 自动拆分 hook | §8.22.1 |

---

## 10 分角色 UAT 穿刺清单（v2 版）

### 审计助理

- [ ] WorkpaperEditor 右栏 SidePanel 7 Tab 切换流畅
- [ ] 自检失败项点击"定位"跳 Univer 单元格
- [ ] 程序要求进底稿编辑器可见
- [ ] 上年数据对比可调
- [ ] AI 内容全部带 "AI 草稿 · 待确认" 水印
- [ ] 未确认 AI 内容时"提交复核"按钮 disabled + tooltip
- [ ] 关闭浏览器有未保存时弹 confirmLeave
- [ ] 顶栏"批注未读 badge" + "委派推送" 可见

### 项目经理

- [ ] ManagerDashboard 4 Tab：项目矩阵 / 团队成本 / 客户承诺 / 异常告警
- [ ] 项目矩阵可钻取到 ProjectDashboard
- [ ] 团队成本 heatmap 可切周期
- [ ] 委派前可见人员已持有底稿数
- [ ] 预算 vs 实际可视化
- [ ] 异常告警可直接跳处理页

### 质控

- [ ] qc 登录默认 /qc（QcHub）
- [ ] QcHub 4 Tab（待抽查 / 抽查中 / 整改中 / 已完结）
- [ ] 项目级 QC 作为 ProjectDashboard Tab
- [ ] 规则试运行显示影响面
- [ ] 规则可设 staging 灰度
- [ ] Finding 可直接跳原底稿高亮
- [ ] 顶栏"质控"badge 显示应抽查数

### 合伙人

- [ ] PartnerSignDecision 单页完成签字判断
- [ ] 风险摘要 10 条有红项时签字按钮 disabled
- [ ] 签字二次确认必须输入客户名
- [ ] 签字历史 context_snapshot 可查
- [ ] 合伙人私库分区独立可见

### EQCR

- [ ] 5 Tab 每个都有 ShadowCompareRow 组件
- [ ] 差异超阈值标红
- [ ] 备忘录版本历史可切换查看
- [ ] 备忘录可独立导出 Word
- [ ] EqcrShadowCompute 非 EQCR 角色 403
- [ ] 切 Tab 不丢状态（keep-alive）

### 跨角色联动

- [ ] 改一条底稿数据 → TB stale 标 → TB 重算 → BS/IS 数字更新 → 附注引用刷新
- [ ] 拒 AJE → 转错报 → 错报表出现 → 超阈值 → GateRule 阻断签字
- [ ] 改重要性 → Misstatements 阈值线即时移动 → GateReadiness 重评估
- [ ] 报表行 → 右键查看底稿 → 单底稿跳转/多底稿列表
- [ ] EQCR 签字 → 报告状态 → eqcr_approved → 合伙人可最终签字

---

## 11 负面清单（v2 追加）

### 架构层面

- ❌ 不做"插件化"（Element Plus + 当前组件库已稳定）
- ❌ 不做"动态路由"（后端下发路由配置，增加心智负担）
- ❌ 不加状态管理框架（Pinia 够用）
- ❌ 不做 SSR / Nuxt（SPA 已满足）
- ❌ 不做"离线优先"架构（审计必须连网）

### 业务层面

- ❌ 不允许"AI 自动做审计判断"
- ❌ 不做"审计助理跳过复核直接签字"
- ❌ 不做"自动关闭未解决复核意见"
- ❌ 不做"历史签字可撤销重签"（除非专门走撤回流程）
- ❌ 不做"归档后可编辑"
- ❌ 不做"EQCR 代签"
- ❌ 不做"partner 批量签字多项目"

### 数据层面

- ❌ 不删除任何历史数据（仅软删 + 回收站）
- ❌ 不做"DROP TABLE" 迁移
- ❌ 不做"重建索引导致长锁"的迁移（用 CONCURRENTLY）
- ❌ 不在 AI prompt 里传未脱敏的客户名/金额

### UX 层面

- ❌ 不加悬浮球/广告弹窗
- ❌ 不加"引导式教程气泡"（用户不想被打扰）
- ❌ 不做"智能推荐"改动用户习惯
- ❌ 不把关键按钮藏在"更多"里

---

## 12 附录

### 附录 A：新建文件清单（v2 涉及）

**前端**
- `views/PartnerSignDecision.vue`
- `views/qc/QcHub.vue`
- `views/ai/AiContentInbox.vue`
- `views/ConfirmationHub.vue`（stub）
- `components/workpaper/WorkpaperSidePanel.vue` + 7 个 Tab 子组件
- `components/eqcr/ShadowCompareRow.vue`
- `components/common/GlobalSearchDialog.vue`
- `components/common/AttachmentPreviewDrawer.vue`
- `components/common/DataLineageDialog.vue`
- `utils/formRules.ts`
- `utils/feedback.ts`
- `constants/statusEnum.ts`
- `stores/projectYear.ts`
- `composables/useStaleStatus.ts`
- `scripts/check-hardcoded-styles.mjs`
- `scripts/check-component-adoption.mjs`
- `scripts/find-missing-v-permission.mjs`
- `scripts/audit-routes.mjs`

**后端**
- `routers/manager_matrix.py`（manager 驾驶舱端点）
- `routers/partner_sign_decision.py`
- `routers/risk_summary.py`
- `routers/data_lineage.py`
- `routers/saved_views.py`
- `routers/ai_sessions.py`
- `services/risk_summary_service.py`
- `services/data_lineage_service.py`
- `services/eqcr_memo_exporter.py`（独立 Word 导出）

**文档**
- `docs/GLOSSARY.md`（术语表）
- `docs/NumberHandling.md`（数值规范）
- `.kiro/conventions/form-rules.md`
- `.kiro/conventions/feedback-guideline.md`

### 附录 B：Alembic 迁移清单

- `round8_client_master_20260510.py`：clients 表
- `round8_project_tags_20260510.py`：project_tags + links
- `round8_ai_sessions_20260511.py`：ai_chat_sessions 表
- `round8_data_lineage_20260511.py`：data_lineage 表
- `round8_saved_views_20260512.py`：saved_views 表
- `round8_knowledge_reference_20260513.py`：knowledge_reference 表
- `round8_signature_snapshot_20260514.py`：SignatureRecord.context_snapshot JSONB
- `round8_project_budget_20260515.py`：Project.budget_hours_config JSONB
- `round8_attachment_quota_20260515.py`：Project.attachment_quota_mb

### 附录 C：代码锚点索引

| 章节 | 锚点 | 行/定位 |
|------|------|---------|
| §3.2 A | `views/WorkpaperEditor.vue` | 右栏区块 |
| §3.2 D | `composables/useWorkpaperAutoSave.ts` | isDirty |
| §5.2 B | `views/QCDashboard.vue` | 独立路由降级 |
| §6.2 A | `router/index.ts` | 新加 partner/sign-decision |
| §7.2 A | `components/eqcr/` | 新建 ShadowCompareRow |
| §7.2 B | `services/eqcr_memo_service.py` | history JSONB |
| §8.2.3 | 30+ 文件 | ElMessageBox.confirm |
| §8.3 | `utils/formatters.ts` / `stores/displayPrefs.ts` | 金额 |
| §8.4 | `views/WorkpaperWorkbench.vue` / `WorkpaperList.vue` | 硬编码 |
| §8.5.3 | `views/Adjustments.vue` | 转错报按钮 |
| §8.6.2 | 15+ 视图 | v-permission 铺设 |
| §8.8 | `stores/projectYear.ts` | 新建 |
| §8.11 | `components/common/GlobalSearchDialog.vue` | 新建 |
| §8.17 | `utils/http.ts` interceptor | 5xx 处理 |
| §8.19.1 | `router/index.ts` | /confirmation 路由 |

### 附录 D：grep 核实的断言（v2 版）

| 断言 | 方式 | 结果 |
|------|------|------|
| GtPageHeader 接入 12 视图 | grep `GtPageHeader` in views | 12 个 .vue 文件 |
| GtEditableTable 接入 0 | grep `GtEditableTable` in views | 无匹配 |
| ElMessageBox.confirm 直接用 30+ | grep in .vue | 30 条，分布 20+ 文件 |
| v-permission 仅 5 .vue | grep | WorkpaperEditor/UserManagement/TemplateManager/StaffManagement/Adjustments |
| navItems 已 computed | grep ThreeColumnLayout.vue:360 | ✅ |
| useEditingLock 接入 3 编辑器 | grep | WorkpaperEditor/DisclosureEditor/AuditReportEditor |
| usePenetrate 接入 2 视图 | grep | TrialBalance/ReportView |
| statusMaps.ts 已删 | fileSearch | 零命中 |
| Vue 层 /api/ 硬编码 17 处 | grep `['"]/api/` | 约 17 处剩余 |
| views 根目录 68 + 子目录 = 86 | ls count | 86 |
| 前端组件 194 | ls count | 194 |
| 内联 font-size Npx | grep | 约 90+ 处 |
| 内联 #color | grep | 约 70+ 处 |

---

## 13 结语

v2 的定位是"v1 落地后的**下半场**"。

**v1 做完后，平台已经从"工程可用"走到了"业务基本连贯"**。但离"审计师真正顺手、合伙人能独立决策"还有差距，核心差在 3 个方向：

1. **一致性（visual/interaction/term）**：组件铺设不彻底、硬编码未清理、术语不统一
2. **闭环深度**：穿透入口建了但前端散、AJE→错报→GateRule 链没完整跑通
3. **角色穿透**：5 角色各自工作台深度不够，签字决策/QC Hub/EQCR 对比组件都是"半成品"

v2 路线图的执行节奏建议：
- **P0 一周内清掉**（3 天工作量，零风险）
- **P1 两周内推进关键角色功能**（签字面板 / SidePanel / ShadowCompareRow 这三项定胜负）
- **P2 开 spec 做"全量铺设 Sprint"**（组件 / 硬编码 / 数值 三条线并行）
- **P3 作为长期治理投入**（测试 / 文档 / 术语）

**衡量指标**：
- GtPageHeader 接入率从 14% → 80%（P2 目标）
- ElMessageBox.confirm 直接用从 30+ → 5 以内（P1）
- 硬编码字体/颜色违规数从 160+ → 50 以下（P2）
- v-permission 接入视图从 5 → 20（P1）
- 5 角色登录到"第一屏有用"时间从 10 秒 → 3 秒（改善）
- 新人上手平均耗时目标 < 2 天（目前靠口头教）

（v2 完）
