# R9 全局深度复盘 — 需求文档

> 版本：v1.0  
> 日期：2026-05-12  
> 视角：资深合伙人（系统负责人）  
> 定位：R1-R8 完成后的增量式全局复盘，聚焦"用户实际使用效果 + 前端一致性 + 联动穿透 + 维护便利性"

---

## 前言

### 业务痛点

经过 R1-R8 共 8 轮打磨，平台后端架构已趋于完善（151 路由 / 226 服务 / 160+ 张表 / 409 ledger_import 测试），但**前端用户体验层面存在系统性断层**：

1. **全局组件接入率极低**：GtPageHeader 19%、GtEditableTable 主业务 0%、GtAmountCell 仅 1 处、v-permission 14%
2. **联动穿透链路分散**：5 套穿透端点 + 3 种前端入口模式（右键/点击/双击），用户不知从哪穿透
3. **角色差异化体验缺失**：5 种角色看到几乎相同的界面，无"角色首页 → 核心动作 → 闭环"的引导
4. **数值显示不统一**：金额列折行、字体不一致、无千分位格式化标准
5. **AI 辅助入口碎片化**：3 套独立 AI 对话组件（AiAssistantSidebar / AIChatPanel / WorkpaperWorkbench 内联），无统一交互范式

### 技术根因

- 8 轮迭代聚焦后端正确性（gate_engine / event_handlers / dataset_service），前端改动多为"补按钮"而非"统一范式"
- 全局组件虽已建好（GtPageHeader / GtEditableTable / GtAmountCell / GtStatusTag），但无 CI 卡点强制接入
- 穿透 composable（usePenetrate）已封装但仅 TrialBalance / ReportView 接入

### 本 spec 边界

**本 spec 是"诊断 + 规划"文档**，产出为可执行的 Sprint 任务清单。不直接改代码，而是为后续 R9 Sprint 1-N 提供输入。

---

## §1 范围边界

### §1.1 本 spec 必做清单

| 编号 | 维度 | 简述 | 优先级 |
|------|------|------|--------|
| F1 | 全局组件 | GtPageHeader 强制接入剩余 50+ 视图 | P0 |
| F2 | 全局组件 | GtAmountCell 替代所有 `<span class="gt-amt">` 手写 | P0 |
| F3 | 数值显示 | 金额列统一 min-width + nowrap + 千分位 | P0 |
| F4 | 权限 | v-permission 全量盘点 + CI 卡点（危险操作必须有） | P0 |
| F5 | 联动穿透 | usePenetrate 统一接入所有金额可点击视图 | P0 |
| F6 | 联动穿透 | 四表→底稿→分录→附注 完整闭环路径可视化 | P1 |
| F7 | 角色体验 | 5 角色各自"首页 → 核心动作 → 闭环"引导 | P1 |
| F8 | AI/LLM | 统一 AI 对话入口（合并 3 套为 1 套 composable） | P1 |
| F9 | 编辑体验 | 底稿 Ctrl+Z 撤销 + operationHistory 扩展 | P1 |
| F10 | 编辑体验 | 粘贴数据结构化入库（usePasteImport 全量接入） | P1 |
| F11 | 全局组件 | GtEditableTable 接入试算表/错报/工时等核心表格 | P1 |
| F12 | 前后端联动 | /api/ 硬编码清零（剩余 30 处） | P1 |
| F13 | 枚举/年度 | statusEnum.ts 全量替代视图内硬编码状态字符串 | P1 |
| F14 | 复核 | ReviewWorkbench 中栏只读 Editor 落地 | P2 |
| F15 | 工时 | 经理"待审批工时"独立入口 + badge | P2 |
| F16 | 通知 | NotificationCenter 分类 Tab + 免打扰时段 | P2 |
| F17 | 知识库 | 知识库搜索结果与底稿上下文关联 | P2 |
| F18 | 维护性 | 前端 vitest 基建 + 关键 composable 单测 | P2 |
| F19 | 维护性 | Playwright E2E 骨架（登录→导入→查账→穿透） | P2 |
| F20 | 显示一致 | 全局字体/字号/间距 CSS 变量体系审计 | P2 |
| F21 | 错误处理 | handleApiError 统一接入所有含 API 调用的视图 | P1 |
| F22 | 编辑模式 | useEditMode 接入所有可编辑视图（当前仅 5 处） | P1 |
| F23 | 加载状态 | 统一 loading 规范：表格用 v-loading，页面级用 el-skeleton | P2 |
| F24 | 全屏模式 | useFullscreen 接入 LedgerPenetration/Adjustments/Misstatements | P2 |
| F25 | 死代码清理 | 删除 AI 死代码组件 + ReviewInbox.vue + 重复 AiContentConfirmDialog | P0 |

### §1.2 独立 Sprint 排除项

| 编号 | 简述 | 原因 |
|------|------|------|
| O1 | PBC 清单真实实现 | 业务逻辑未定义，需独立 spec |
| O2 | 函证管理真实实现 | 同上 |
| O3 | 暗色模式 | 美观但非核心业务 |
| O4 | Ctrl+K 全局搜索 | 需独立 UX 设计 |
| O5 | 移动端适配 | 当前 5 个 Mobile stub 已删，不再投入 |
| O6 | 多语言 i18n | 当前仅中文用户 |

---

## §2 功能需求

### §2.A 审计助理视角（F9, F10, F3, F5）

**核心诉求**：快速填写底稿、准确查账、高效粘贴数据

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| F9 | 底稿编辑器支持 Ctrl+Z/Y 撤销重做 | operationHistory 接入单元格编辑事件，≥20 步回退 |
| F10 | 从 Excel 粘贴到任意表格自动解析 | usePasteImport 接入 TrialBalance/Adjustments/WorkHours/Misstatements |
| F3 | 所有金额列不折行、等宽数字、千分位 | 全局 `.gt-amt` 规约 + GtAmountCell 组件化，LedgerPenetration 金额列 min-width=180 |
| F5 | 任意金额单元格点击即穿透 | usePenetrate 接入 LedgerPenetration/Adjustments/Misstatements/DisclosureEditor |

### §2.B 项目经理视角（F7, F15）

**核心诉求**：一眼看清进度、快速派单催办、工时审批不遗漏

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| F7-PM | ManagerDashboard 增加"我的待办"聚合卡片 | 待审批工时 + 待复核底稿 + 逾期承诺，一页纸 |
| F15 | 工时审批独立入口 + 顶栏 badge | WorkHoursPage 新增"待审批"Tab 默认展示 + 未审数量 badge |

### §2.C 质控人员视角（F7）

**核心诉求**：独立抽查、规则巡检、覆盖率可视

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| F7-QC | QCDashboard 增加"本年抽查覆盖率"卡片 | 已抽项目数/应抽项目数 + 进度条 |

### §2.D 合伙人视角（F7）

**核心诉求**：签字前一页纸看清风险、快速决策

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| F7-Partner | PartnerSignDecision 中栏升级为 PDF 预览 | 后端 /preview-pdf 端点 + 前端 iframe/embed 展示 |

### §2.E EQCR 视角（F7）

**核心诉求**：独立复核一页纸摘要、备忘录版本对比

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| F7-EQCR | EqcrProjectView 新增"关键发现摘要"Tab | 聚合 10 Tab 核心结论为 1 页 |

### §2.F 全局组件 & 设计一致性（F1, F2, F11, F20）

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| F1 | GtPageHeader 接入率从 19% → 95%+ | 除 Login/NotFound/DevelopingPage 外全部接入 |
| F2 | GtAmountCell 替代手写 gt-amt span | Drilldown/LedgerPenetration/LedgerImportHistory 等全部改用组件 |
| F11 | GtEditableTable 接入核心表格 | Adjustments/Misstatements/WorkHours 三个视图改造 |
| F20 | CSS 变量体系审计 | 确认 --gt-font-size-*/--gt-space-*/--gt-color-* 覆盖所有视图 |

### §2.G 联动穿透（F5, F6）

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| F5 | usePenetrate 统一接入 | 所有含金额列的视图（≥8 个）右键/点击可穿透 |
| F6 | 穿透闭环路径可视化 | 用户从报表→试算表→序时账→凭证→底稿→附注 全链路可达 |

### §2.H LLM / 知识库 / 对话（F8, F17）

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| F8 | 统一 AI 对话 composable | 合并 AiAssistantSidebar + AIChatPanel + WorkpaperWorkbench 内联为 useAiChat |
| F17 | 知识库搜索关联底稿上下文 | 搜索时自动带入当前科目/底稿编码作为上下文 |

### §2.I 权限 & 枚举（F4, F13）

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| F4 | v-permission 全量盘点 | 所有"删除/签字/导出/归档/审批"按钮必须有 v-permission |
| F13 | statusEnum.ts 全量替代 | 视图内 `=== 'draft'` 等硬编码字符串改为常量引用 |

### §2.J 维护性 & 可观测性（F12, F18, F19）

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| F12 | /api/ 硬编码清零 | grep 统计 = 0（当前 ~30 处） |
| F18 | vitest 基建 | 安装 vitest + 关键 composable（usePenetrate/useEditingLock/useProjectEvents）单测 |
| F19 | Playwright E2E 骨架 | 登录→创建项目→导入账套→查账穿透 4 步 happy path |

### §2.K 错误处理 & 编辑模式 & 加载状态（F21, F22, F23, F24, F25）

**代码锚定实测**：
- `handleApiError` 当前接入 **7 个视图**（ReportView/PartnerSignDecision/DisclosureEditor/Adjustments/EqcrProjectView/TrialBalance/WorkpaperEditor），剩余 60+ 视图的 catch 块用 `ElMessage.error` 或 `console.error` 各自处理
- `useEditMode` 当前接入 **5 处**（AuditReportEditor/Materiality/ReportConfigEditor/TemplateManager/DisclosureEditor），其余可编辑视图（Adjustments/WorkHoursPage/StaffManagement/SubsequentEvents 等）用自定义 ref 管理编辑状态
- `useFullscreen` 当前接入 **3 个主视图**（TrialBalance/ReportView/DisclosureEditor）+ 12 个合并子组件，LedgerPenetration 已有全屏但未用 composable
- AI 死代码：`ai/ContractAnalysis` / `ContractAnalysisPanel` / `EvidenceChainPanel` / `EvidenceChainView` 4 组件 grep 零引用；`ReviewInbox.vue` 无路由引用；`components/workpaper/AiContentConfirmDialog.vue` 与 `components/ai/AiContentConfirmDialog.vue` 同名重复

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| F21 | handleApiError 统一接入 | 所有含 try/catch + API 调用的视图统一用 handleApiError，消除裸 ElMessage.error |
| F22 | useEditMode 统一接入 | 所有含"编辑/保存/取消"交互的视图接入 useEditMode（≥10 处） |
| F23 | 加载状态规范化 | 表格统一 v-loading，页面级首屏统一 el-skeleton；消除混用 |
| F24 | useFullscreen 补齐 | LedgerPenetration/Adjustments/Misstatements 接入 useFullscreen composable |
| F25 | 死代码清理 | 删除 4 个 AI 零引用组件 + ReviewInbox.vue + 重复 AiContentConfirmDialog（共 6 文件） |

---

## §3 非功能需求

| 维度 | 指标 | 当前 | 目标 |
|------|------|------|------|
| 性能 | 查账页首屏 | 未测 | <2s（1000 科目） |
| 性能 | 穿透响应 | 17ms（有索引） | <200ms（含前端渲染） |
| 可靠性 | vue-tsc 错误 | 0 | 保持 0 |
| 可靠性 | CI 通过率 | 未统计 | >95% |
| 安全 | v-permission 覆盖 | 14% | >90% 危险操作 |
| 兼容 | 浏览器 | Chrome 最新 | Chrome/Edge/Firefox 最新 3 版本 |

---

## §4 测试矩阵

| 层级 | 范围 | 工具 | 状态 |
|------|------|------|------|
| 单测 | composables（usePenetrate/useEditingLock/useProjectEvents） | vitest | 待建 |
| 组件测试 | GtAmountCell/GtEditableTable/GtPageHeader | vitest + @vue/test-utils | 待建 |
| E2E | 登录→导入→查账→穿透→签字 | Playwright | 骨架已建 |
| 后端 | 已有 409+ ledger_import 测试 | pytest | 已有 |

---

## §5 成功判据汇总

| 指标 | 当前值 | R9 目标 | 对应需求 |
|------|--------|---------|----------|
| GtPageHeader 接入率 | 19% | ≥95% | F1 |
| GtAmountCell 接入 | 1 处 | ≥8 处 | F2 |
| v-permission 覆盖 | 14% | ≥90% 危险操作 | F4 |
| /api/ 硬编码 | ~30 处 | 0 | F12 |
| usePenetrate 接入 | 2 视图 | ≥8 视图 | F5 |
| 金额列折行 | 存在 | 0 处折行 | F3 |
| AI 对话组件 | 3 套 | 1 套 useAiChat | F8 |
| 前端单测 | 0 | ≥20 个 composable 测试 | F18 |
| handleApiError 接入 | 7 视图 | ≥30 视图（所有含 API 调用的） | F21 |
| useEditMode 接入 | 5 处 | ≥10 处 | F22 |
| useFullscreen 主视图 | 3 个 | ≥6 个 | F24 |
| 死代码文件 | 6 个零引用 | 0 | F25 |

---

## §6 术语表

| 术语 | 含义 |
|------|------|
| 穿透 | 从汇总数字点击下钻到明细凭证的操作 |
| 四表 | 余额表(tb_balance) + 辅助余额(tb_aux_balance) + 序时账(tb_ledger) + 辅助序时(tb_aux_ledger) |
| GtPageHeader | 全局页面标题栏组件，含返回/操作按钮/同步状态 |
| GtAmountCell | 全局金额单元格组件，含格式化+穿透+条件格式 |
| usePenetrate | 穿透导航 composable，封装路由跳转逻辑 |

---

---

## §7 Sprint 拆分建议 & 详细实现锚定

### Sprint 1（P0，预计 3-4 天）—— 金额显示 + 权限 + 穿透统一

#### F3 金额列统一（1 天）

**当前问题**：LedgerPenetration 金额列 width=150/130 导致大金额折行；`.gt-amt` 仅 3 视图手写。

**实现位置**：
- `audit-platform/frontend/src/views/LedgerPenetration.vue` 第 163-176 行：width 从 170 改为 200，加 `min-width="180"`
- `audit-platform/frontend/src/views/Drilldown.vue` 第 82-93 行：同上
- `audit-platform/frontend/src/App.vue` 或 `assets/main.css`：`.gt-amt` 全局样式确认 `font-variant-numeric: tabular-nums`
- **新增**：`utils/formatAmount.ts` 统一千分位格式化函数（当前各视图各自 `fmtAmt`）

**验收**：所有金额列在 12 位数字（如 210,301,834.96）时不折行。

#### F4 v-permission 全量盘点（1 天）

**当前问题**：69 个视图仅 10 个有 v-permission（14%），大量"删除/导出/签字/归档"按钮裸奔。

**实现位置**（需补 v-permission 的视图，grep 确认）：
- `ArchiveWizard.vue`：归档按钮无权限
- `RecycleBin.vue`：恢复/永久删除无权限
- `SamplingEnhanced.vue`：抽样执行无权限
- `ReportConfigEditor.vue`：保存配置无权限
- `WorkpaperWorkbench.vue`：AI 聊天/附件上传无权限
- `IssueTicketList.vue`：关闭工单无权限
- `Adjustments.vue`：已有 2 处，但"新增 AJE"按钮无权限
- `ManagerDashboard.vue`：派单按钮无权限
- `QCDashboard.vue`：发起抽查无权限

**验收**：`scripts/find-missing-v-permission.mjs` 输出 ≤ 2 个非危险操作遗漏。

#### F5 usePenetrate 统一接入（1 天）

**当前问题**：usePenetrate composable 仅 TrialBalance + ReportView 接入；LedgerPenetration/Adjustments/Misstatements/DisclosureEditor 各自手写路由跳转。

**实现位置**：
- `composables/usePenetrate.ts`：确认已有 `toLedger/toReportRow/toWorkpaperEditor/toAdjustment` 方法
- `LedgerPenetration.vue`：`drillToLedger` 函数（第 ~1100 行）改为调 `penetrate.toLedger()`
- `Adjustments.vue`：金额列点击穿透到序时账
- `Misstatements.vue`：错报金额穿透到对应科目
- `DisclosureEditor.vue`：附注行右键"查看相关底稿"已有，补"穿透到序时账"

**验收**：8 个含金额列的视图均可右键/点击穿透。

#### F1 GtPageHeader 强制接入（1-2 天）

**当前问题**：50+ 视图自写 `<h2 class="gt-page-title">` 或 `<div class="gt-page-banner">`。

**实现策略**：
- 批量替换模式 A（简单标题）：`AnnotationsPanel/AttachmentManagement/AuxSummaryPanel/CheckInsPage/CollaborationIndex/ConsistencyDashboard/ConsolSnapshots/ForumPage/PersonalDashboard/ProcedureTrimming/ProjectDashboard/RecycleBin/ReportFormatManager/ReportTracePanel/StaffManagement/SubsequentEvents/UserManagement/WorkHoursPage` = **18 个视图**
- 批量替换模式 B（带 banner 的 Dashboard）：`AuditCheckDashboard/ManagementDashboard/ManagerDashboard/PartnerDashboard/QCDashboard/MyProcedureTasks/ProjectProgressBoard` = **7 个视图**（需 GtPageHeader 支持 banner 模式或保留自定义 slot）
- 排除：Login/Register/NotFound/DevelopingPage = 4 个

**验收**：`grep -c "GtPageHeader" views/*.vue` ≥ 55。

---

### Sprint 2（P1，预计 4-5 天）—— 角色体验 + AI 统一 + 编辑增强

#### F7 角色首页引导（2 天）

**实现位置**：
- `views/Dashboard.vue`：当前是通用首页，需按 `authStore.user.role` 分流展示不同卡片
- `views/ManagerDashboard.vue`：补"待审批工时"卡片（调 `/api/workhours/summary`）
- `views/QCDashboard.vue`：补"本年抽查覆盖率"卡片
- `views/PartnerDashboard.vue`：补"待签字项目"一键跳转 PartnerSignDecision
- `views/eqcr/EqcrProjectView.vue`：新增"关键发现摘要"Tab（聚合 10 Tab 结论）

#### F8 AI 对话统一（1 天）

**当前 3 套**：
1. `components/workpaper/AiAssistantSidebar.vue`（fetch `/api/workpapers/{wpId}/ai/chat`）
2. `components/ai/AIChatPanel.vue`（fetch `/api/ai/chat`）
3. `views/WorkpaperWorkbench.vue` 内联（api.post `/api/workpapers/${wpId}/ai/chat`）

**实现策略**：
- 新建 `composables/useAiChat.ts`：统一 SSE 流式响应 + 消息历史 + 上下文注入
- AiAssistantSidebar 改为调 useAiChat（保留 UI 壳）
- AIChatPanel 改为调 useAiChat
- WorkpaperWorkbench 内联代码删除，改用 WorkpaperSidePanel 的 AI Tab

#### F9 Ctrl+Z 撤销（1 天）

**实现位置**：
- `WorkpaperEditor.vue`：Univer 实例已有 `undo/redo` API（`univerInstance.executeCommand('undo')`）
- 需要把 shortcutManager 的 `shortcut:undo/redo` 事件连接到 Univer 命令
- operationHistory 扩展：记录单元格编辑事件（Univer 的 `onCommandExecuted` hook）

#### F10 粘贴结构化入库（1 天）

**当前状态**：`usePasteImport` 仅 Misstatements 接入。

**扩展到**：
- `TrialBalance.vue`：粘贴 AJE 数据到调整列
- `Adjustments.vue`：粘贴多行分录
- `WorkHoursPage.vue`：粘贴批量工时

---

### Sprint 3（P1 续，预计 3 天）—— 组件接入 + 硬编码清零

#### F2 GtAmountCell 替代手写（1 天）

**当前手写位置**（需改为 GtAmountCell）：
- `Drilldown.vue`：12 处 `<span class="gt-amt">{{ fmt(...) }}</span>`
- `LedgerPenetration.vue`：20+ 处
- `LedgerImportHistory.vue`：6 处

**GtAmountCell 已有功能**：格式化 + 穿透点击 + hover 高亮 + CommentTooltip

#### F11 GtEditableTable 接入（1 天）

**目标视图**：Adjustments（当前 el-table + 内联编辑）→ GtEditableTable

#### F12 /api/ 硬编码清零（1 天）

**剩余 30 处分布**（阶段 A 已扫描）：
- TrialBalance 4 处 / PartnerSignDecision 5 处 / ProjectDashboard 3 处 / DisclosureEditor 4 处 / LedgerPenetration 5 处 / 其他散落 9 处
- 全部迁移到 `apiPaths.ts` 对应路径对象

---

### Sprint 4（P2，预计 3-4 天）—— 维护性 + 通知 + 显示一致

#### F18 vitest 基建（1 天）
- 安装 vitest + @vue/test-utils
- 为 usePenetrate / useEditingLock / useProjectEvents / useAiChat 写单测

#### F19 Playwright E2E（1 天）
- 安装 @playwright/test
- 4 个 happy path：登录 → 创建项目 → 导入账套 → 查账穿透

#### F16 NotificationCenter 分类（0.5 天）
- 新增 Tab：全部 / 复核 / 导入 / 系统
- 免打扰时段：22:00-08:00 不弹 toast

#### F20 CSS 变量审计（0.5 天）
- 确认所有视图使用 `--gt-font-size-*` / `--gt-space-*` / `--gt-color-*`
- 消除内联 `style="font-size: 13px"` 等硬编码

---

## 附录 A：当前平台关键指标快照（2026-05-12 代码锚定）

| 指标 | 数值 | 来源 |
|------|------|------|
| Vue 视图文件 | 69（根）+ 6 子目录 | `ls views/` |
| 组件目录 | 23 子目录 + 5 根级 | `ls components/` |
| GtPageHeader 接入 | 13/69 = 19% | `grep GtPageHeader **/*.vue` |
| GtEditableTable 主业务接入 | 0（仅合并模块 2 处） | `grep GtEditableTable **/*.vue` |
| GtAmountCell 接入 | 1 处（ReportView） | `grep GtAmountCell **/*.vue` |
| v-permission | 13 处 / 10 文件 | `grep v-permission **/*.vue` |
| useEditingLock | 3 编辑器 | `grep useEditingLock **/*.vue` |
| useWorkpaperAutoSave | 2 编辑器 | `grep useWorkpaperAutoSave **/*.vue` |
| useEditMode | 5 处（AuditReportEditor/Materiality/ReportConfigEditor/TemplateManager/DisclosureEditor） | `grep useEditMode **/*.vue` |
| useFullscreen 主视图 | 3 个（TrialBalance/ReportView/DisclosureEditor）+ 12 合并子组件 | `grep useFullscreen **/*.vue` |
| handleApiError | 7 视图接入 | `grep handleApiError views/**/*.vue` |
| .gt-amt 使用 | 3 视图 | `grep gt-amt **/*.vue` |
| /api/ 硬编码 | ~30 处 / 15 视图 | `grep /api/ views/**/*.vue` |
| AI 对话入口 | 3 套独立组件 | AiAssistantSidebar + AIChatPanel + WW 内联 |
| AI 死代码 | 4 组件零引用 + 1 重复 + 1 无路由引用 = 6 文件 | grep 零命中 |
| 穿透入口 | 5 套后端端点 / 前端 usePenetrate 仅 2 视图接入 | grep drill/penetrat |
| 加载状态 | v-loading 约 35 处 / el-skeleton 约 4 处 / 混用无规范 | grep v-loading/el-skeleton |
