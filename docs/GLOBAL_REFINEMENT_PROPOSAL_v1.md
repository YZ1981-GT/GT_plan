# 审计平台全局打磨建议 v1（深度版）

**编制人**：资深合伙人（平台治理方向）
**日期**：2026-05-07
**范围**：5 角色视角 + 17 个全局横切主题
**目标**：在不加新功能的前提下，解决"工程可用但业务不顺手"的断层

---

## 0 评估结论与量化指标

### 技术完成度 vs 业务连贯度

| 维度 | 得分 | 说明 |
|------|------|------|
| 后端覆盖 | 95% | 151 路由 / 226 服务 / 51 模型 / 2830 pytest 0 error |
| 前端覆盖 | 90% | 73 views / 186 components / 16 composables / vue-tsc 0 error |
| 全局组件铺设 | **30%** | 73 个 views 里只有 **6 个**接入 GtPageHeader，**0 个**用 GtEditableTable |
| 业务流闭环 | 75% | 5 轮打磨已闭环核心流，仍有 3 处死角（见下） |
| 角色感知 | 40% | 侧栏 10 项对所有角色一视同仁，后端 `get_nav_items` 有但前端没接 |
| API 规范 | 75% | apiPaths.ts 260+ 端点，Vue 层仍有 ~173 处硬编码（CI 基线） |
| 枚举/状态规范 | 50% | `statusMaps.ts`（9 套）+ `dictStore`（运行时）并存，GtStatusTag 内部做兜底 |
| 弹窗/确认规范 | 55% | `utils/confirm.ts` 存在，但 ElMessageBox.confirm 直接用法仍 15+ 处 |

### 三个最值得立刻解决的结构性问题

1. **全局组件接入率只有 30%**：组件库建好了，存量视图没迁。这是所有"一致性"问题的根因。
2. **角色感知只到侧栏导航第一层**：后端按角色返回 navItems，前端没接，所有角色都看同一套一级菜单。
3. **枚举/状态/路径三条线未打通**：`statusMaps` / `dictStore` / `apiPaths` 各有职责但没形成闭环，新加一个状态需要三处同步。

---

## 一、五角色视角（逐角色穿刺）

### 1.1 审计助理（auditor）

#### 1.1.1 现状证据链

| 场景 | 证据 | 评估 |
|------|------|------|
| 登录落地 | `router/index.ts:30` Dashboard 为根路径，无角色判断 | 助理登录落到通用页，不是个人待办 |
| "我的"系 | `PersonalDashboard.vue` + `MyProcedureTasks.vue` 并存，各自独立路由 | 职责重复，助理不确定进哪 |
| 待办底稿 | `Dashboard.vue:52-57` 用 `myWorkpapers.slice(0, 6)` 硬截断 | 超过 6 张看不到，无"查看全部"入口 |
| 提交复核 | `WorkpaperEditor.vue:445` 用 `ElMessageBox.confirm`，非 `utils/confirm.ts` | 文案风格与删除不统一 |
| 版本冲突 | `WorkpaperEditor.vue:384` 用 `ElMessageBox.confirm`（"底稿已被他人修改"） | 同上 |
| 批注未读 | 顶部只有"复核收件箱"badge，无"我的批注未读" | 助理需进每张底稿才看得到 |
| 附件上传 | `AttachmentDropZone.vue` 只在 WorkpaperWorkbench 引用，其他底稿页无拖拽 | 体验不统一 |
| 工时填报 | `WorkHoursPage.vue:22` 状态标签 `row.status === 'confirmed' ? 'success' : ...` 硬编码三元 | 未用 GtStatusTag |

#### 1.1.2 建议（按影响面从大到小）

**A. 登录角色路由表（一处改全系统生效）**

在 `stores/auth.ts:login()` 成功后追加：

```ts
// 伪代码
const ROLE_HOME: Record<string, string> = {
  auditor: '/my/dashboard',
  manager: '/dashboard/manager',
  partner: '/dashboard/partner',
  qc:      '/qc/inspections',
  eqcr:    '/eqcr/workbench',
  admin:   '/',  // 保持通用
}
router.replace(ROLE_HOME[user.role] ?? '/')
```

风险：改动 1 个文件；助理首次登录体感直接提升。若 `redirect` query 存在（登录守卫 `/login?redirect=xxx`），优先 redirect，覆盖 ROLE_HOME。

**B. 合并"我的"系入口**

- 方案：保留 `PersonalDashboard.vue` 作为唯一"我的"入口，内部用 Tab 区分"待办底稿 / 我的程序任务 / 我的工时 / 我的批注"。
- `MyProcedureTasks.vue` 内容迁移成 `PersonalDashboard.vue` 的一个 Tab，删除独立路由。
- 侧栏"我的"导航默认指向 `/my/dashboard`，只对非 admin 角色显示。

**C. Dashboard 待办底稿扩展**

`Dashboard.vue:48-62` 改为：
- 默认显示 6 张；
- 若 `myWorkpapers.length > 6`，底部加"查看全部（共 X 张）→"链接到 `/my/dashboard?tab=workpapers`。

**D. 批注未读 Badge**

- 后端新增 `GET /api/my/unread-annotations/count` 返回 `{total, by_project}`。
- 前端 `DefaultLayout.vue` 在 `#nav-review-inbox` slot 后新增一个类似的 badge 按钮，点击到 `/my/dashboard?tab=annotations`。
- 轮询 5 分钟一次，或 SSE 事件 `annotation:new` 即时更新。

**E. 确认文案统一**

- `utils/confirm.ts` 新增 3 个包装：
  - `confirmSubmitReview(wpCode, wpName)` → "提交后底稿将进入复核流程..."
  - `confirmVersionConflict(serverVer, localVer)` → "底稿已被他人修改..."
  - `confirmLeave(moduleLabel)` → "当前 XX 有未保存的变更..."
- `WorkpaperEditor.vue` 第 384、445、563 行全部替换。

#### 1.1.3 不做

- 不给助理加"可执行程序裁剪"权限（质控职责）
- 不再给助理加新的顶部导航入口（顶栏已满）

### 1.2 项目经理（manager）

#### 1.2.1 现状证据链

| 场景 | 证据 | 评估 |
|------|------|------|
| 看板入口 | `ThreeColumnLayout.vue:329` 侧栏"看板"硬编码 `/dashboard/management`（通用） | manager 需手动改 URL 到 `/dashboard/manager` |
| 工时审批 | `router:232` `/work-hours/approve` 有 `permission: 'approve_workhours'`；但侧栏"工时"指 `/work-hours`（填报） | 需手动改 URL |
| 项目进度 | `ProjectProgressBoard.vue`（单项目）+ `ManagerDashboard.vue`（跨项目）并存 | 标题不区分，易混 |
| 委派 | `BatchAssignDialog.vue` 只在底稿列表里弹出，无"人员×项目"矩阵视图 | 想看"小李手头 8 张底稿进度"需穿透多项目 |
| 催办 | `WorkpaperList.vue`、`ProjectDashboard.vue:193` 内都有催办入口，散 | manager 无"我发出的催办"聚合 |
| 客户沟通 | `ProjectProgressBoard.vue` 有沟通记录 Tab，但承诺事项是字符串，不结构化 | R2 已识别但未升级 |
| 预算对比 | `WorkHoursApproval.vue:314` 已实现预算超支警告，但只在审批弹窗里 | manager 没有跨项目成本全景 |

#### 1.2.2 建议

**A. 侧栏路径角色化（这是"角色感知"的必要基础）**

`ThreeColumnLayout.vue:322` `navItems` 改为 `computed`：

```ts
const navItems = computed<NavItem[]>(() => {
  const baseNav = [ /* 硬编码 10 项作为兜底 */ ]
  // 优先用后端下发
  if (roleStore.navItems?.length) return roleStore.navItems
  // 根据 effectiveRole 覆盖部分路径
  const role = roleStore.effectiveRole
  return baseNav.map(item => {
    if (item.key === 'mgmt-dashboard') {
      if (role === 'manager') return { ...item, path: '/dashboard/manager' }
      if (role === 'partner') return { ...item, path: '/dashboard/partner' }
    }
    if (item.key === 'workhours' && ['manager','partner','admin'].includes(role)) {
      return { ...item, path: '/work-hours?tab=approve' }
    }
    return item
  })
})
```

**B. 工时单视图 Tab 化**

- 合并 `/work-hours` 和 `/work-hours/approve` 到同一页面，Tab 切换"填报 / 审批 / 统计"。
- 审批 Tab 用 `v-if="can('approve_workhours')"` 控制显隐。
- 删除 `WorkHoursApproval.vue` 独立路由，迁移其内容为 `WorkHoursPage.vue` 的子 Tab。

**C. 看板双层标题**

- `ManagerDashboard.vue` 顶部 banner 标题固定 "跨项目经理看板"
- `ProjectProgressBoard.vue` 顶部 banner 标题固定 "项目进度看板：{projectName}"
- 用 GtPageHeader（详见 §2.1）

**D. 人员×项目矩阵视图**

新增 `StaffProjectMatrix.vue`（放在 `StaffManagement.vue` 的一个 Tab）：
- 纵轴：该 manager 管辖的所有人员
- 横轴：进行中项目
- 单元格：该人在该项目上的底稿数 + 完成率 + 工时
- 后端端点 `GET /api/staff/{manager_id}/matrix`

**E. 催办台**

- 新增 `/my/reminders` 路由，挂到 `PersonalDashboard.vue` 的一个 Tab。
- 后端端点 `GET /api/my/reminders`（我发出的 + 我需要回复的，两个 Tab）。
- 复用 `Reminder` 模型（memory 未记录是否存在，需 grep 确认，没有则新建表）。

**F. 客户承诺结构化**

- `Project.wizard_state.communications[].commitments` 从 `string` → `Array<{id, desc, due_date, status, resolved_at}>`（R2 已识别）。
- 迁移脚本 `scripts/migrate_commitments.py`：把旧字符串 split by 换行/分号，填入 `desc`，`status='pending'`。
- 前端 `ProjectProgressBoard.vue` 改用 `el-table` 展示，支持勾选"已完成"。

#### 1.2.3 不做

- 不新加"项目经理"一级导航（用现有"看板"即可）
- 不给 manager 上"查看其他项目 partner 私信"权限

### 1.3 质控人员（qc）

#### 1.3.1 现状证据链

| 场景 | 证据 | 评估 |
|------|------|------|
| QC 主入口 | 一级导航无"质控" | QC 登录只能记 URL |
| QC 页面散 | `/qc/rules`、`/qc/rules/:id/edit`、`/qc/inspections`、`/qc/clients/:c/trend`、`/qc/cases`、`/qc/annual-reports` 6 个独立路由 | 无 Hub 聚合 |
| 项目 QC | `QCDashboard.vue` 放在 `/projects/:id/qc-dashboard`；`QcInspectionWorkbench.vue` 跨项目 | 两个"QC Dashboard"概念重叠 |
| 规则编辑 | `QcRuleEditor.vue` 要求 `hasRunDryRun` 才能保存（好设计） | OK |
| 导航动态 | `role_context_service.get_nav_items` 返回含 QC 专属 3 项，但前端 `ThreeColumnLayout.vue` 硬编码 | 后端努力白费 |
| 抽查流程 | `QcInspectionWorkbench.vue` 工作流是：选项目→执行规则→查看发现→导出报告；但"选项目"要点多次 | 可一键"本月应抽查" |
| 规则执行器 | `qc_rule_executor.py` 支持 python + jsonpath，SQL/regex 未实装 | 已 memory 记录，低优 |

#### 1.3.2 建议

**A. 新建 QcHub 或升级 QcInspectionWorkbench**

方案一（推荐）：把 `QcInspectionWorkbench.vue` 升级为"QC 主工作台"，路由改为 `/qc`（默认），内部 Tab：
- 「待抽查项目」（本月按轮动规则应抽查的项目清单，后端端点已有 `qc_rotation_service`）
- 「抽查执行」（当前工作流）
- 「规则库」（嵌入 QcRuleList 只读视图 + "前往编辑"按钮）
- 「案例库」（嵌入 QcCaseLibrary）
- 「年报」（嵌入 QcAnnualReports）
- 「客户质量趋势」（嵌入 ClientQualityTrend，选客户后加载）

保留原有 6 个子路由作为直达入口，但 Hub 作为默认。

方案二（保守）：新建 `QcHub.vue` 作为 `/qc` 根页，提供 6 个卡片跳转到现有页面。落地更快但体验差。

**B. 项目级 QC Tab 化**

- `QCDashboard.vue` 从独立路由降级为 `ProjectDashboard.vue` 的一个 Tab "质控"。
- 重命名为 `ProjectQCTab.vue`，`QCDashboard.vue` 删除。
- 保持 API 不变。

**C. 侧栏导航接入后端**

见 §2.2 通用方案。QC 角色登录后侧栏应自动包含：仪表盘 / 项目 / 质控（新增）/ 人员 / 用户。不应该看到"工时/函证/归档"（非 QC 职责）。

**D. 本月应抽查 Badge**

顶栏 QC 角色可见的"质控"入口加 badge：待抽查项目数。
- 端点 `GET /api/qc/rotation/due-this-month`
- 每 30 分钟刷新

#### 1.3.3 不做

- 不扩展 QC 规则 DSL 的 SQL/regex 分支（R6 已决定延后）
- 不给 QC 加"直接编辑底稿"权限（只读复核）

### 1.4 项目合伙人（partner）

#### 1.4.1 现状证据链

| 场景 | 证据 | 评估 |
|------|------|------|
| 看板默认路径 | 侧栏"看板"指 `/dashboard/management`（通用） | partner 需手动 |
| 签字视图 | `AuditReportEditor.vue` + `ArchiveWizard.vue` + `SignatureManagement.vue` 三处显示签字状态 | 无统一 |
| 门禁 | `GateReadinessPanel.vue` 组件存在，但 partner 默认进入 `Dashboard.vue` 看不到 | 要进项目才看得到 |
| 独立性声明 | `PartnerDashboard.vue:561, 582` 硬编码 `/api/my/pending-independence?limit=...` | 违反 apiPaths 规范 |
| 两个 limit 按钮 | 同一端点 limit=50 和 limit=200 各一按钮 | UX 冗余 |
| 签字门禁跳过 | 没有"紧急签字"的例外路径 | OK（合规要求） |
| 合伙人私域 | PrivateStorage 所有角色可见 | partner 无专属"合伙人私库" |
| 合伙人轮换 | `rotationApi.ts` 存在，但 partner 看不到自己的轮换状态 | 无 UI |

#### 1.4.2 建议

**A. 修复硬编码（P0，最快）**

`services/apiPaths.ts` 新增 `my` 域：

```ts
export const my = {
  pendingIndependence: (limit = 50) => `/api/my/pending-independence?limit=${limit}`,
  reminders: '/api/my/reminders',
  unreadAnnotations: '/api/my/unread-annotations/count',
  focusStats: '/api/my/focus-stats',
} as const
```

`PartnerDashboard.vue:561, 582` 替换。

**B. 签字全景 Tab**

`PartnerDashboard.vue` 新增"签字全景"Tab：
- 跨项目列表：`[{project, report_status, my_sign_status, gate_blockers_count, next_action}]`
- 每行可展开，内嵌 `GateReadinessPanel.vue`（props 传入该项目的 readiness data）
- 后端端点：`GET /api/my/sign-overview`（聚合 SignatureRecord + AuditReport.status + gate_engine.evaluate）

**C. 合并 limit 按钮**

`PartnerDashboard.vue` 的两个按钮合并为一个"加载更多"分页控件（默认 50，点击+50，最多 500）。

**D. 合伙人私库强化**

- `PrivateStorage.vue` 支持按角色分区：auditor 看自己的，partner 可额外看"合伙人共享"分区。
- 分区用 `PrivateFile.scope` 字段（`personal | partner_shared | admin_shared`）。需 Alembic 迁移加列。

**E. 轮换状态显示**

- `PartnerDashboard.vue` 新增"我的轮换状态"卡片：显示本人在哪些客户被轮换锁定（到年）、哪些客户今年首次接单（冷却期结束）
- `rotationApi.ts` 已有 `getMyRotation()` 端点，直接用

#### 1.4.3 不做

- 不给 partner 跳过 GateRule 的"紧急例外"通道（合规）
- 不做"多重签字并行"（目前串行签字设计合理）

### 1.5 项目独立复核合伙人（eqcr）

#### 1.5.1 现状证据链

| 场景 | 证据 | 评估 |
|------|------|------|
| 工作台 | `EqcrWorkbench.vue` + `EqcrProjectView.vue`（10 Tab）+ `EqcrMetrics.vue` 三级完备 | OK |
| 独立性阻断 | router 守卫 `requiresAnnualDeclaration` 已落地 | OK |
| 角色权限 | `ROLE_PERMISSIONS.eqcr` 包含 7 项（见 usePermission.ts:40-48）| OK |
| 影子计算 | 5 判断 Tab 可影子计算，但"项目组值 vs 影子值"并排对比缺失 | 复核合伙人要切 Tab 对比 |
| 备忘录 | `Project.wizard_state.eqcr_memo` JSONB，无版本历史 | 覆盖式保存，想回溯难 |
| 指标入口 | `DefaultLayout.vue:131-134` 的 `isEqcrEligible` 只允许 partner/admin | eqcr 自己看不到 EqcrMetrics |
| 备忘录导出 | 只进归档包 02 章节，无独立导出 Word | EQCR 要发备忘录给合伙人必须走归档 |
| 5 Tab 切换 | EqcrProjectView 是 Tab 布局，切换时状态不保留 | 回到原 Tab 要重载 |

#### 1.5.2 建议

**A. EqcrMetrics 对 eqcr 角色开放（P0）**

`DefaultLayout.vue:131-134` 改：
```ts
const isEqcrEligible = computed(() => {
  const role = roleStore.effectiveRole
  return ['partner', 'admin', 'eqcr'].includes(role) || roleStore.isPartner
})
```

`router/index.ts:465` 的 `meta: { roles: ['admin', 'partner'] }` 改为 `['admin', 'partner', 'eqcr']`。

**B. 项目组值 vs 影子值 并排对比组件**

新建 `components/eqcr/ShadowCompareRow.vue`（3 列表格行）：

```
| 维度 | 项目组值 | 影子值 | 差异 | 我的判断 |
| 整体重要性 | 800,000 | 750,000 | -50,000 (-6.3%) | [通过] [标记异常] |
```

- 5 判断 Tab 全部改为"左栏项目组值一览 + 右栏 ShadowCompareRow 列表"
- 点击"我的判断"实时写 `EqcrVerdict` 表（已有）

**C. 备忘录版本历史**

`Project.wizard_state.eqcr_memo` 字段结构扩展：
```json
{
  "sections": {...},
  "status": "draft|finalized",
  "history": [
    {"version": 1, "saved_at": "...", "saved_by": "uuid", "sections_snapshot": {...}}
  ]
}
```

- 前端每次保存前，把旧 `sections` 压入 `history`，最多保留 5 版
- EqcrProjectView 的 memo Tab 新增"版本"下拉，可切换查看历史

**D. 独立导出备忘录 Word**

- 后端端点 `GET /api/eqcr/projects/{pid}/memo/export?format=docx`（复用 phase13 note_word_exporter 模式）
- EqcrProjectView 的 memo Tab 顶部加"导出 Word"按钮

**E. Tab 切换状态保留**

EqcrProjectView.vue 的 `el-tabs` 加 `:lazy="false"`（当前是默认懒加载，切换就卸载）。注意会增加内存占用，只对"已访问过的 Tab"缓存，用 `keep-alive` 包 `el-tab-pane` 的内容。

#### 1.5.3 不做

- 不让 EQCR 直接对外联络客户（坚持"项目组单一对外入口"边界）
- 不给 EQCR 独立修改项目组已发报告的权限
- 不做"EQCR 多人并行"（单 EQCR 人负责制）

---

## 二、17 个全局横切主题

### 2.1 全局组件铺设（最大的架构债）

#### 2.1.1 量化现状（本次 grep 核实）

- `views/` 根目录 73 个 `.vue`
- 引入 `GtPageHeader` 的只有 **6 个**（TrialBalance / ReportView / DisclosureEditor / ConsolidationIndex / EqcrMetrics / + 1）
- 引入 `GtEditableTable` 的是 **0 个**
- 大量视图自写 banner/toolbar/tablet，样式散乱

#### 2.1.2 问题清单

- `WorkpaperWorkbench.vue` 自写 banner（`.gt-wpb-banner`）和 toolbar，与 TrialBalance 的 GtPageHeader 风格不一致
- `Materiality / Misstatements / Adjustments / WorkpaperList / Projects / KnowledgeBase` 等高频页都没用 GtPageHeader
- `WorkpaperList.vue:77-84` 用硬编码 `#7c5cbf / #6a4fa0 / #e6553a / #1a8a5c / #7f8c8d` 五种颜色做"审计循环标签"，既不是品牌色也不是 design token
- `WorkpaperEditor.vue` 第 50-56 行连续多个 `style="font-size: 12px; color: #666"` 等硬编码
- `TrialBalance.vue` 内部有 `color: #28a745 / #FF5149 / #ccc` 硬编码（第 188/191/193 行）

#### 2.1.3 分三步治理

**Step 1：盘点（1 天）**

新建脚本 `scripts/audit-component-adoption.mjs`（Node）：

```js
// 输出矩阵：每个 view 是否接入 Gt* 组件
// 列：view 文件 / GtPageHeader / GtToolbar / GtInfoBar / GtAmountCell / GtStatusTag / GtEditableTable
// 用 PowerShell 的 Select-String 无差别 grep
```

输出 `docs/COMPONENT_ADOPTION_MATRIX.md`。一次性脚本，用完删除。

**Step 2：高频页标杆（3 天）**

6 个高频页作为标杆迁移：
1. `WorkpaperList.vue`（最复杂，优先做）
2. `Adjustments.vue`
3. `Misstatements.vue`
4. `Materiality.vue`
5. `KnowledgeBase.vue`
6. `Projects.vue`

每个页面改造内容：
- 顶部 banner 换成 `<GtPageHeader>`
- 工具栏（搜索/筛选/导出）换成 `<GtToolbar>`
- 单位/年度切换换成 `<GtInfoBar>`
- 金额列换成 `<GtAmountCell>`
- 状态 el-tag 换成 `<GtStatusTag>`
- 若有编辑表格，尝试用 `GtEditableTable`

**Step 3：硬编码颜色/字号清零（2 天）**

CI 新增 lint 规则：禁止在 `.vue` 的 `style="..."` 里写十六进制颜色（`#RRGGBB`）和 `font-size: Npx`。允许清单：`var(--gt-*)`、`inherit`、`transparent`、`currentColor`。

CI 基线数：统计当前违规数，设为基线，触碰即修。

#### 2.1.4 长期规则

- 新 PR 不得直接写 `el-tag`，必须 `GtStatusTag`
- 新 PR 不得写 inline hex color，必须用 token
- 代码 review 卡点：组件接入率不降

### 2.2 角色感知导航（唯一要改动 ThreeColumnLayout 的点）

#### 2.2.1 现状

- `ThreeColumnLayout.vue:324-335` 是硬编码 10 项（dashboard/projects/team/workhours/mgmt-dashboard/consolidation/confirmation/archive/attachments/users）
- `stores/roleContext.ts:37` 有 `navItems: NavItem[]` 字段
- 后端 `role_context_service.get_nav_items` 已按角色返回（memory 已记录 QC 3 项、manager 工作台项已加）
- **前端没用**

#### 2.2.2 方案

`ThreeColumnLayout.vue` 的 `navItems` 改为 `computed`：

```ts
const FALLBACK_NAV: NavItem[] = [ /* 当前硬编码 10 项 */ ]

const navItems = computed<NavItem[]>(() => {
  // 后端下发优先
  const backendNav = roleStore.navItems
  if (Array.isArray(backendNav) && backendNav.length > 0) {
    return backendNav
  }
  // 兜底：按 role 对 FALLBACK_NAV 做路径覆盖（见 §1.2 方案 A）
  return patchNavByRole(FALLBACK_NAV, roleStore.effectiveRole)
})
```

#### 2.2.3 后端适配

确认 `role_context_service.get_nav_items` 的 NavItem 字段与前端 `NavItem` 类型兼容：
- `key: string`
- `label: string`
- `icon: string`（前端映射到 @element-plus/icons-vue，需 importmap 或 switch）
- `path: string`
- `maturity?: 'production' | 'pilot' | 'experimental' | 'developing'`

后端返回 icon 字符串（不返回 Vue 组件），前端用 `ICON_MAP: Record<string, Component>` 映射。

#### 2.2.4 灰度

- 新增 `.env` 开关 `VITE_DYNAMIC_NAV=false`（默认关）
- 用 feature flag 控制是否启用动态导航
- 灰度 1-2 周后移除 flag

### 2.3 项目（project）

#### 2.3.1 现状

| 项 | 说明 |
|----|------|
| 项目列表 | `Projects.vue` 清单展示 |
| 项目向导 | `ProjectWizard.vue` 7-8 步建项 |
| 项目入口 | `DefaultLayout.vue` 通过中间栏 `MiddleProjectList.vue` + `DetailProjectPanel.vue` 实现"三栏浏览" |
| 项目状态 | `ProjectStatus` 枚举：created/planning/execution/completion/reporting/archived |
| 项目维度 | 需支持"客户"维度聚合，用于 R7 客户质量趋势（已有 ClientQualityTrend.vue） |

#### 2.3.2 发现的问题

- 项目**没有标签系统**（tag/category）。想查"所有上市公司审计"需靠 `applicable_standard` 过滤
- 项目归档后仍出现在列表，只靠 status=archived 过滤，默认 UI 没有"归档/活跃"切换
- 项目和"客户"的关联是 `client_name: string`，不是 FK，导致同客户不同项目的聚合靠模糊匹配

#### 2.3.3 建议

**A. 客户主数据**

- 新建 `clients` 表：`id, name, normalized_name, industry, listed, parent_id, created_at`
- `Project.client_id` 作为 FK，保留 `client_name` 冗余字段向后兼容
- 从现有 Project.client_name 抽取 + `normalize_client_name` 去重生成 clients 记录
- 前端 `Projects.vue` 支持"按客户聚合"视图

**B. 项目标签**

- 新建 `project_tags` 关联表
- 预置标签：上市准备 / 季审 / 年审 / 内审 / 专项 / 税审
- `Projects.vue` 顶部加标签多选筛选

**C. 归档/活跃切换**

- `Projects.vue` 顶部 Tab：活跃 / 归档 / 全部
- 默认"活跃"

**D. 项目模板**

- 新建项目时支持"基于上年同客户项目克隆"（复制底稿结构、程序裁剪、人员委派）
- `POST /api/projects/{id}/clone-from/{prev_id}`

### 2.4 人员（staff）

#### 2.4.1 现状

- `StaffMember` 模型（employee_no 工号 + name + role + ...）
- `StaffManagement.vue` 增删改+交接 flow
- `User` 模型是登录账号，独立
- 一级导航"人员"指 staff，"用户"指 user，并列容易混

#### 2.4.2 问题

- Staff 和 User 未强绑定：一个 StaffMember 可能没有 User 账号（外协人员）
- Staff 有 `grade` 字段（A/B/C/D/助理/高级），但在 `assignment_service.ROLE_MAP` 和 usePermission `ROLE_PERMISSIONS` 里没有 grade 维度
- 人员履历 `StaffMember.resume` 是文本，无结构化历史项目

#### 2.4.3 建议

**A. Staff/User 桥接字段**

- `StaffMember.user_id: UUID | null`（可空，外协无账号）
- 后端创建 User 时如选择"关联 staff"，自动写 user_id
- 前端 StaffManagement 显示"有账号 ✅"/"外协 ⚪"

**B. 级别化权限**

- `grade` 从"展示字段"升级为"权限字段"
- `usePermission.ROLE_PERMISSIONS` 加上 grade 维度：auditor_senior / auditor_junior
- `BatchAssignDialog.vue:296` 已用 `complexCycles` + `role === 'manager' || 'senior_auditor'` 做智能委派，把这里也对齐 grade

**C. 履历结构化（已在 §1.2 建议 F 提到类似，合并做）**

### 2.5 工时（workhours）

#### 2.5.1 现状

- `WorkHoursPage.vue`（填报）、`WorkHoursApproval.vue`（审批）、`workhour_list.py`（后端新端点）
- `WorkHour.status` 是 String(20) 自由字段，业务值 draft/confirmed/approved/tracking
- 前端 `WorkHoursPage.vue:22` 状态标签硬编码三元，未用 GtStatusTag

#### 2.5.2 建议

**A. 字典化 + GtStatusTag**

- 后端 `/api/system/dicts` 补 `workhour_status`：
  ```json
  [
    {"value": "draft", "label": "草稿", "color": "info"},
    {"value": "tracking", "label": "计时中", "color": "warning"},
    {"value": "confirmed", "label": "已确认", "color": ""},
    {"value": "approved", "label": "已审批", "color": "success"}
  ]
  ```
- 前端所有工时状态 tag 换成 `<GtStatusTag :value="row.status" dict-key="workhour_status" />`

**B. 审批门禁**

- 审批人工时 >=8h/天 且 >=40h/周 硬警示（已在 `WorkHoursApproval.vue:314` 部分实现，扩到填报侧）
- 填报时写入超 12h/天直接拒绝

**C. 计时能力**

- `WorkHourStatus='tracking'` memory 已记录但无前端 UI
- `WorkHoursPage.vue` 顶部加"开始计时 / 停止计时"按钮，写 WorkHour(project_id, status='tracking', started_at=now)；停止时 diff 小时写入 hours 字段 + status='draft'

### 2.6 工时管理（workhour management，与 2.5 区分）

#### 2.6.1 现状

- 项目经理/合伙人需要看"项目工时总览 / 员工工时分布 / 预算对比"
- 当前只在 `ManagerDashboard.vue` 和 `WorkHoursApproval.vue` 有零散统计
- 无"跨项目工时热力图"

#### 2.6.2 建议

**A. 项目工时卡片**

`ProjectDashboard.vue` 新增工时卡片：
- 已投入 / 预算 / 剩余 / 预计超支概率
- 点击进 `WorkHoursPage.vue?project_id=xxx` 筛选视图

**B. 员工热力图**

`ManagerDashboard.vue` 新增员工周工时热力图（横轴：周一~周日；纵轴：员工；色深=小时数）
- 复用 ECharts heatmap（GTChart 组件已封装 ECharts）

**C. 成本面板**

`PartnerDashboard.vue` 的 `/api/projects/{id}/cost-overview` 已有端点（见 apiPaths.ts:36）
- 增加跨项目"成本总览"，端点 `GET /api/my/cost-overview`

### 2.7 底稿（workpaper）

#### 2.7.1 现状（重点主题，单独展开）

| 视图 | 定位 | 问题 |
|------|------|------|
| `WorkpaperList.vue` | 清单 + 批量操作 + 批注抽屉 | 1200+ 行大文件，侧栏抽屉塞太满 |
| `WorkpaperEditor.vue` | Univer 单底稿编辑 | 版本冲突弹窗原生 ElMessageBox；硬编码颜色多 |
| `WorkpaperWorkbench.vue` | 三栏引导式编制（左树+中编辑+右 AI/附件） | 自写 banner 不用 GtPageHeader |
| `WorkpaperSummary.vue` | 跨企业合并汇总 | 用 el-table 未用 GtEditableTable |
| `MobileWorkpaperEditor.vue` | 手机端，stub | developing |

#### 2.7.2 问题清单

- 四个视图各自有 banner，无统一 GtPageHeader
- `WorkpaperList.vue` 的"审计循环标签"5 色硬编码（见 §2.1.2）
- 底稿提交复核的"前置条件"用 innerHTML 拼 `<ul><li>...`（`WorkpaperList.vue:1206-1215`），强耦合样式
- 自动保存状态散：`WorkpaperEditor.vue` 用 autoSaveMsg 字符串 + `WorkpaperList` 用不同变量名
- `useAutoSave` composable 不适合 Univer 大 snapshot，memory 已记录
- 批注回复气泡样式在 `WorkpaperList.vue:296` 硬编码背景色 `#f0f9eb`
- 智能提示面板 `SmartTipList.vue` 存在，但在 `WorkpaperEditor.vue` 里又自写了一份内联 tip 显示（第 90-94 行）
- `DataConsistencyMonitor` / `DependencyGraph` / `OcrFieldsDrawer` / `SamplingPanel` 等组件分散，没有统一右栏面板架构

#### 2.7.3 建议

**A. 统一底稿右栏面板**

新建 `components/workpaper/WorkpaperSidePanel.vue`：
- 标签页式容器：AI / 附件 / 版本 / 批注 / 程序要求 / 依赖 / 一致性 / 智能提示
- 所有三个底稿视图（WorkpaperEditor/WorkpaperWorkbench/WorkpaperList 抽屉）都复用此组件
- 每个 Tab 对应一个子组件（AiAssistantSidebar / AttachmentsTab / VersionsTab / AnnotationsTab / ...）

**B. 自动保存规范化**

新建 `composables/useWorkpaperAutoSave.ts`（独立于 useAutoSave）：
- setInterval 每 2 分钟调 onSave
- 状态 `{ saving, lastSavedAt, lastError, isDirty }`
- 直接绑定到顶部 `SyncStatusIndicator.vue`（已存在）
- WorkpaperEditor.vue 和 DisclosureEditor.vue（另一大型 snapshot 编辑）统一走此 composable

**C. 提交复核卡片**

把 `WorkpaperList.vue:1206` 的 innerHTML 拼接改成 `components/workpaper/SubmitReviewChecklist.vue` 组件：
- 各前置条件作为数据数组
- 用 `<el-steps>` 或 `<el-descriptions>` 结构化显示

**D. 程序要求 Tab 化**

`ProgramRequirementsSidebar.vue` 目前似乎只在 Workbench 里集成，应挂到底稿右栏面板作为"程序要求"Tab，编辑时可见。

**E. 批注气泡统一**

新建 `gt-annotation-bubble` CSS class，在 `styles/gt-polish.css` 定义。所有视图用 class 而非 inline。

### 2.8 附件（attachment）

#### 2.8.1 现状

- 两入口：`/attachments`（全局 AttachmentHub）+ `projects/:id/attachments`（AttachmentManagement）
- OCR 状态散在 `WorkpaperWorkbench.vue`（.gt-wpb-ocr-badge 内联 class）和 AttachmentManagement
- 附件预览靠 `backend/app/routers/attachments.py` 的 preview 端点，前端用 `window.open` 打开新标签

#### 2.8.2 建议

**A. 双入口明确定位**

- `/attachments` = 跨项目视图，供 partner/admin 审查/取证
- `/projects/:id/attachments` = 项目视图，供助理/经理
- 两者共享 `AttachmentTable.vue` 组件（props 控制是否显示"项目"列 / 是否允许上传）

**B. OCR 状态 Badge 组件化**

新建 `components/common/OcrStatusBadge.vue`：
- Props: `status: 'ok' | 'processing' | 'failed' | 'pending'`
- 样式从 `WorkpaperWorkbench.vue` 的 `.gt-wpb-ocr-badge` 抽取
- 替换所有 ocr badge 用法

**C. 预览组件化**

`AttachmentPreviewDrawer.vue` 把预览改为抽屉弹出，不开新标签：
- PDF/图片直接嵌入 `<iframe>` 或 `<img>`
- Word/Excel 调 LibreOffice 转 PDF 后嵌入
- OCR 结果并排显示
- 所有附件位置（WorkpaperEditor 右栏、AttachmentManagement、AttachmentHub）统一唤起此抽屉

### 2.9 复核（review）

#### 2.9.1 现状

- `ReviewInbox.vue` 独立文件存在，但 **router 三条路由全部指向 `ReviewWorkbench.vue`**（router:119-128），`ReviewInbox.vue` 实为死代码
- `ReviewInbox.vue` 和 `ReviewWorkbench.vue` 代码高度重复（`handleSingleApprove / handleBatchApprove / doBatchReview` 完全一致）
- `ReviewConversations.vue` 是多轮讨论线程
- `ReviewRecord`（单行批注）和 `review_conversations`（跨对象）两套并存，R1 已决定 ReviewRecord 为"→工单"真源

#### 2.9.2 建议

**A. 删除 ReviewInbox.vue（P0）**

一次性删除。router 已不引用，安全。

**B. ReviewWorkbench Tab 化**

目前 `ReviewWorkbench.vue` 既是收件箱又是详情。建议内部左右布局：
- 左栏：收件箱清单（跨项目 / 单项目切换）
- 右栏：选中底稿的复核界面（嵌入只读 WorkpaperEditor + 批注列表 + 通过/退回按钮）
- 避免"列表 ↔ 详情"的页面跳转切换

**C. SSE 事件驱动 Badge**

当前 `DefaultLayout.vue` 每 5 分钟轮询 badge。改为 SSE：
- 后端 event `review:submit` → 前端订阅 → badge 即时 +1
- 后端 event `review:processed` → badge -1

**D. 会话→工单统一入口**

`ReviewConversations.vue` 加"转工单"按钮，和 `ReviewWorkbench.vue` 走同一后端（IssueTicket source='review_comment'）。

### 2.10 枚举（enum / status / dict）

#### 2.10.1 现状（9 套 statusMaps + dictStore）

`utils/statusMaps.ts` 共 **9 个** StatusMap：
- WP_STATUS / WP_REVIEW_STATUS / ADJUSTMENT_STATUS / REPORT_STATUS / TEMPLATE_STATUS / PROJECT_STATUS / ISSUE_STATUS / PDF_TASK_STATUS + 可能漏数

dictStore 已覆盖部分但不全（workhour_status 就是个缺口例子）。

GtStatusTag 内部有 `STATUS_MAP_TO_DICT_KEY` 硬编码映射表桥接两套。

#### 2.10.2 问题

- 新加一个状态要动 3 个地方：后端 `dicts.py` + 前端 `statusMaps.ts` + GtStatusTag 的 `STATUS_MAP_TO_DICT_KEY`
- 有些组件直接 `dictStore.label('xxx', val)` 不走 GtStatusTag，失去统一入口
- 有些组件还在 el-tag 里手写三元 `row.status === 'x' ? 'success' : ...`（WorkHoursPage、MobileReview 等）

#### 2.10.3 治理方案（独立 spec）

**Phase 1：后端对齐**

- 盘点 `statusMaps.ts` 的 9 套，逐一对照后端 `core/dicts.py` 或 `/api/system/dicts`
- 每一项补齐后端（缺什么补什么）
- 确保后端返回 `{value, label, color}` 三元组，与前端 DictEntry 匹配

**Phase 2：前端收敛**

- 所有 el-tag 状态展示统一用 `<GtStatusTag dict-key="xxx" :value="..." />`
- 删除 `statusMaps.ts`
- 删除 GtStatusTag 的 `STATUS_MAP_TO_DICT_KEY` 和 fallback 分支

**Phase 3：CI 卡点**

- Lint 规则：Vue 模板不允许直接 `<el-tag :type="x.status === 'y' ? ... : ...">`
- 必须用 `<GtStatusTag>`

风险：破坏性改动，需独立 spec 三件套推进，类似 apiPaths 迁移。

### 2.11 年度（year context）

#### 2.11.1 现状

- `projectStore.year` 从 `route.query.year` 同步
- 部分视图从 `projectStore`，部分从 `route.query.year` 直接读
- "上年对比"模式各视图实现方式不一（TrialBalance 和 ReportView 不同）

#### 2.11.2 建议

**A. 严禁直读 route.query.year**

- `grep "route.query.year"` 盘点，全部改 `projectStore.year`
- CI 规则：不允许 `route.query.year` 在 view/component 出现（stores 层允许）

**B. 上年对比成为 displayPrefs 开关**

- `displayPrefs` 加字段 `priorYearCompare: boolean`
- `displayPrefs.ts` 的 "Aa" 面板加"显示上年列"开关
- 各视图（ReportView / TrialBalance / WorkpaperList）按此开关展示

**C. 年度切换即时生效**

- `GtInfoBar` 的年度切换目前会刷新当前视图数据
- 建议顶部"项目"上下文包含 year，切换 year 广播事件 `project:year-changed`
- 订阅此事件的视图自动 reload

### 2.12 编辑模式（view/edit toggle）

#### 2.12.1 现状

- `useEditMode` 设计完善（查看/编辑 + 未保存提示 + 路由拦截）
- **只有 `DisclosureEditor.vue` 接入**
- WorkpaperEditor / AuditReportEditor / ReportConfigEditor / TemplateManager / Adjustments / Materiality 全部直接进入编辑状态

#### 2.12.2 建议

**A. 所有编辑性页面接入 useEditMode**

清单（7 个）：
1. WorkpaperEditor.vue
2. AuditReportEditor.vue
3. ReportConfigEditor.vue
4. TemplateManager.vue
5. Adjustments.vue
6. Materiality.vue
7. ReportView.vue（某些模式下可编辑）

默认进入"查看模式"，右上角"编辑"按钮切到编辑模式。未保存时路由切换 `confirmLeave` 拦截。

**B. 编辑模式视觉标识**

编辑模式顶部加黄色横条"✏️ 编辑中 · 请记得保存"。切回查看消失。

**C. 权限卡点**

编辑模式切换按钮加 `v-permission`，无编辑权限的角色看不到（只能查看）。

### 2.13 显示（display - 金额/字号/字体/条件格式）

#### 2.13.1 现状

- `displayPrefs` store 覆盖：金额单位/字号/小数/零值/负数红/变动高亮
- 顶栏 "Aa" 面板切换
- **问题**：大量视图在 style 里硬编码 `font-size: 11-14px`，不走 `displayPrefs.fontConfig`

#### 2.13.2 硬编码盘点（本次 grep 结果）

`WorkpaperWorkbench.vue` 样式块内硬编码 `font-size` 至少 20 处（例：.gt-wpb-rec-code / .gt-wpb-rec-name / .gt-wpb-rec-reason / .gt-wpb-attach-name / .gt-wpb-ai-analysis-text ...）

`WorkpaperList.vue` 内联 style `font-size:11px / 12px / 13px` 至少 10 处

`WorkpaperEditor.vue` 内联 style `font-size:12px` 多处

#### 2.13.3 治理规则

**A. 分类对待**

- **结构性字号**（banner title / 导航 label / emoji 描述）：保留硬编码，但用 CSS 变量 `var(--gt-font-size-xs/sm/base/md/lg)`
- **表格字号**：必须用 `:style="{ fontSize: displayPrefs.fontConfig.tableFont }"`
- **金额**：用 `GtAmountCell` 或 `displayPrefs.fmt(v)`，不再本地写 `fmtAmt`

**B. 字体降级链**

`gt-tokens.css:76-80` 当前：
```
'GT Walsheim', 'FZYueHei', 'Microsoft YaHei', 'PingFang SC', 'Helvetica Neue', Arial, sans-serif
```

建议加：`'Segoe UI', 'Noto Sans CJK SC', ` 作为英文 Win 降级 + Linux 服务端打包字体时的降级。

**C. 自定义字号范围**

当前 fontSize 只有 11/12/13/14 四档。建议加"自定义" pro 模式，允许 10-18px 滑杆。老年审计员常抱怨"字太小"。

**D. 暗色模式激活**

`gt-dark-mode.scss` 已存在但未启用。建议：
- `displayPrefs` 加 `theme: 'light' | 'dark' | 'auto'`
- 跟随系统偏好（prefers-color-scheme）
- 顶栏 "Aa" 面板增加主题切换

### 2.14 权限（permission）

#### 2.14.1 现状

- `usePermission.ROLE_PERMISSIONS` 5 角色硬编码，优先后端 `user.permissions`
- router 守卫支持 `meta.permission`（单项）和 `meta.roles`（角色数组）
- `v-permission` 指令仅 2 处使用

#### 2.14.2 建议

**A. 全按钮 v-permission 铺设**

高危操作清单（按钮级必须加 v-permission）：
- 所有 `删除` 按钮（permission 各模块 `xxx:delete`）
- 所有 `审批 / 通过 / 退回` 按钮（`xxx:review` 或 `approve_xxx`）
- 所有 `签字` 按钮（`sign:execute`）
- 所有 `归档 / 解锁` 按钮（`archive:execute`）
- 所有 `导出报告 / 最终报表` 按钮（`report:export`）
- 所有 `转错报` 按钮（`adjustment:convert_to_misstatement`，新增）
- 所有 `催办 / 升级` 按钮（`send_reminder`, `escalate`）

grep `@click` + 关键字批量盘点。

**B. meta.roles 推广**

所有角色敏感路由（例：partner only、qc only）加 `meta.roles: string[]`。router 守卫已支持此机制。

**C. 后端权限自省端点**

`GET /api/permissions/self` 返回当前用户可用的权限清单 + 可访问路由。前端启动时调用，用于动态裁剪 UI（按钮隐藏/disabled）。

### 2.15 查询（search / filter）

#### 2.15.1 现状

- 顶栏"自定义查询" (CustomQueryDialog)
- 表格内搜索 (useTableSearch + TableSearchBar)
- 无全局搜索

#### 2.15.2 建议

**A. Ctrl+K 全局搜索**

- 顶栏加 icon "🔎"，Ctrl+K 唤起
- 搜索范围：项目 / 底稿 / 附注 / 附件 / 知识库
- 后端 `GET /api/search?q=xxx&scope=all`（首期接项目+底稿）
- 类 Spotlight 样式弹层，键盘导航

**B. TableSearchBar 全覆盖**

所有表格页必须能 Ctrl+F 搜索。目前 `DisclosureEditor / Adjustments / Misstatements` 已覆盖，`WorkpaperList / TrialBalance / ReportView` 需补。

**C. 筛选持久化**

- 筛选条件写入 URL query，分享链接即分享筛选状态
- 常用筛选支持"保存为视图"，侧栏显示我的视图列表

### 2.16 知识库（knowledge base）

#### 2.16.1 现状

- `KnowledgeBase.vue` 完备
- `useKnowledge` composable 仅在 DisclosureEditor / AuditReportEditor 接入
- WorkpaperEditor 无知识库入口

#### 2.16.2 建议

**A. WorkpaperEditor 接入**

右栏面板加"知识库"Tab，调 KnowledgePickerDialog 插入到叙述单元格。

**B. 按循环分类**

- 一级目录：B 风险评估 / C 控制测试 / D-N 实质性程序（按循环展开）/ A 完成阶段 / S 特定项目 / 通用
- 与底稿编码体系一致

**C. "我的收藏" + "团队收藏"**

- `POST /api/knowledge/{id}/favorite` 个人收藏
- 项目维度 `POST /api/projects/{pid}/knowledge/{id}/pin` 团队级置顶

**D. 版本/变更历史**

当前知识库文档覆盖式保存。建议 `knowledge_documents.versions` JSONB，保留最近 10 版本，可 diff 对比。

### 2.17 对话聊天与 LLM 辅助（AI）

#### 2.17.1 现状

`components/ai/` 共 **19 个组件**（含 `.js`）：
- AIChatPanel / AICommandBar / ContractAnalysis / ContractAnalysisPanel / DocumentOCRPanel / EvidenceChainPanel / EvidenceChainView / ConfirmationAIAssistant / ConfirmationAIPanel / AiContentConfirmDialog / AIContentDashboard / AIContentReviewPanel / AIInsightsDashboard / KnowledgeBasePanel / ModelTable / NLCommandInput / WorkpaperAIFill / CommandConfirmCard / index.js

同时 `components/workpaper/` 下有 `AiAssistantSidebar.vue` + `AiContentConfirmDialog.vue`（**与 ai/ 下同名重复！**）

#### 2.17.2 问题

- **组件重复**：`ai/AiContentConfirmDialog.vue` vs `workpaper/AiContentConfirmDialog.vue` 两份
- **组件大部分未被任何地方引用**：ContractAnalysis / ContractAnalysisPanel / EvidenceChainPanel / EvidenceChainView grep 零命中
- 没有统一的"AI 待确认"聚合视图（跨项目跨底稿）
- AI 会话无历史持久化

#### 2.17.3 建议

**A. 清理死代码**

- 确认 `ContractAnalysis / ContractAnalysisPanel / EvidenceChainPanel / EvidenceChainView` 是否有引用
- grep 零命中则删除
- `AiContentConfirmDialog.vue` 统一成一份（保留 `components/ai/` 版本，删除 `workpaper/` 版本，修正引用）

**B. AI 待确认聚合**

新建 `views/ai/AiContentInbox.vue`：
- 跨项目列出所有 `confirmation_status='pending'` 的 AI 生成内容
- 复用 `AIContentReviewPanel` 的单条确认逻辑
- 挂到 `PersonalDashboard.vue` 的一个 Tab

**C. AI 会话持久化**

- 新建 `ai_chat_sessions` 表（或在现有 chat_messages 加 project_id + wp_id 索引）
- 端点 `GET /api/projects/{pid}/workpapers/{wpid}/ai-sessions`
- WorkpaperEditor 右栏 AI Tab 打开时加载该底稿历史对话

**D. 模型管理收敛**

- `AIModelConfig.vue` 和 `AIPluginManagement.vue` 在 `SystemSettings.vue` 内合并为一个 Tab "AI 管理"
- 减少顶栏 icon 数（当前顶栏已 12+ 个按钮）

---

## 三、维护便利性（运维/架构视角）

### 3.1 路由规范一致性

**现状**

- router 有 4 种 meta：`requireAuth / developing / permission / roles / requiresAnnualDeclaration`
- 部分路由缺 meta（默认继承父级 requireAuth）
- `confirmation` 一级导航指向 `/confirmation`，但 **该路由不存在**（grep 零命中），点击会 404 或回退 NotFound

**建议**

**A. Confirmation 路由修复**

- 要么实现 `/confirmation` 路由（ConfirmationHub.vue），要么移除侧栏条目
- maturity 已标 developing，点击应跳 `/developing`（router 守卫已有 developing meta 机制，但 `/confirmation` 路径没在 routes 里，不会触发）
- **建议**：新建 `/confirmation` 路由占位符，指 `ConfirmationHub.vue` stub + `meta: { developing: true }`，触发守卫跳转到 `DevelopingPage`

**B. 路由 meta 矩阵**

一次性脚本 `scripts/audit-routes.mjs` 扫描 router/index.ts，输出矩阵：
```
路径 | name | component | requireAuth | developing | permission | roles | requiresAnnualDeclaration
```
检查每条路由四个 meta 字段完整性。

**C. 移动端路由**

- `MobilePenetration / MobileReview / MobileReport / MobileProjectList / MobileWorkpaperEditor` 5 个视图全是 stub
- 要么做完，要么**整体删除**（减少代码负担）
- 建议：Round 7+ 前**整体删除**，移动端独立再规划

### 3.2 API 路径管理

- `apiPaths.ts` 260+ 端点
- Vue 视图硬编码基线 173（CI 卡点）
- 本次新发现硬编码：`PartnerDashboard.vue:561, 582`；`QCDashboard.vue:325`

建议：专项提交一次"存量硬编码清理"PR，目标：基线 → <80

### 3.3 测试基础设施

- 后端：pytest 2830 tests / 0 errors，hypothesis 101 个属性测试
- 前端：无 vitest，仅 vue-tsc 0 错误

建议：
- 装 vitest + @vue/test-utils
- 至少覆盖纯逻辑：`utils/formatters / utils/confirm / utils/statusMaps / stores/displayPrefs / stores/dict / composables/usePermission`
- CI 加 `npm run test:unit` job

### 3.4 文档治理

- `memory.md` 已膨胀到 ~350 行（规则上限 200）
- 每轮打磨结束应**立即**拆分到 dev-history/architecture/conventions

建议：
- 新建 hook `auto-split-memory`（promptSubmit 触发时判断 memory.md 行数，超限自动迁移）
- memory.md 保留"最近 3 轮状态 + 活跃待办"即可

### 3.5 部署与启动

- Docker 镜像未打包 LibreOffice（PDF 导出依赖）
- Paperless-ngx / vLLM / ONLYOFFICE 三个副产品仍在 docker-compose 里，有的已不用
- .env 关键变量未在 .env.example 体现（DB_POOL_SIZE / MAX_UPLOAD_SIZE_MB 等）

建议：
- Dockerfile 加 `libreoffice-core libreoffice-writer libreoffice-calc` 依赖
- 清理 docker-compose 中未使用的服务（ONLYOFFICE 已替换）
- `.env.example` 补齐所有用到的变量，加中文注释

---

## 四、优先级与落地路线图

### P0（本周内做，低风险，高收益）

| # | 任务 | 涉及文件 | 工作量 |
|---|------|---------|--------|
| 1 | 删除 ReviewInbox.vue（死代码） | 1 文件 | 10 分钟 |
| 2 | 修复 PartnerDashboard.vue 2 处硬编码 | apiPaths.ts + 1 view | 30 分钟 |
| 3 | 修复 QCDashboard.vue:325 硬编码 | apiPaths.ts + 1 view | 20 分钟 |
| 4 | EqcrMetrics 对 eqcr 角色开放 | DefaultLayout + router | 15 分钟 |
| 5 | 登录后角色跳转 | stores/auth.ts | 30 分钟 |
| 6 | MobileXxx 视图整体删除或标记 developing | 5 文件 + router | 30 分钟 |
| 7 | `/confirmation` 路由修复（要么实现要么删除侧栏） | ThreeColumnLayout + router | 30 分钟 |
| **合计** | | | **半天** |

### P1（2 周内做，中风险）

| # | 任务 | 说明 |
|---|------|------|
| 8 | 侧栏 navItems computed 化 + 按角色路径覆盖 | §2.2 |
| 9 | confirm.ts 补齐 5 个语义化函数 + 全局替换 ElMessageBox.confirm | §2.8 |
| 10 | 所有编辑页接入 useEditMode | §2.12 |
| 11 | WorkpaperEditor + DisclosureEditor 统一 useWorkpaperAutoSave | §2.7 B |
| 12 | 工时填报/审批 Tab 合并 + GtStatusTag + workhour_status 字典 | §2.5 + §2.6 |
| 13 | AI 组件死代码清理（ContractAnalysis / EvidenceChain 等） | §2.17 A |
| 14 | AiContentConfirmDialog 去重（ai/ vs workpaper/） | §2.17 A |

### P2（一个月内做，需 spec 三件套）

| # | 任务 | 说明 |
|---|------|------|
| 15 | 全局组件铺设 Sprint（GtPageHeader 从 6 → 73） | §2.1 |
| 16 | statusMaps → dictStore 单向收敛 | §2.10 |
| 17 | QC 主工作台升级 + 项目级 QC Tab 化 | §1.3 B/C |
| 18 | EQCR 5 Tab 影子对比组件 + 备忘录版本 | §1.5 B/C/D |
| 19 | 底稿右栏面板统一（WorkpaperSidePanel） | §2.7 A |
| 20 | 客户主数据 + 项目标签 | §2.3 |
| 21 | v-permission 全按钮铺设 | §2.14 A |
| 22 | 附件预览抽屉组件化 | §2.8 C |

### P3（后续迭代，可选）

| # | 任务 | 说明 |
|---|------|------|
| 23 | Ctrl+K 全局搜索 | §2.15 A |
| 24 | AI 待确认聚合视图 + 会话持久化 | §2.17 B/C |
| 25 | 前端 vitest 基建 | §3.3 |
| 26 | 暗色模式激活 | §2.13 D |
| 27 | 客户沟通承诺结构化 | §1.2 F |
| 28 | 员工热力图 + 跨项目成本面板 | §2.6 B/C |

---

## 五、5 角色 UAT 穿刺清单（每轮打磨后都跑）

### 审计助理

- [ ] 登录 → **落到 /my/dashboard**（不是 / 通用页）
- [ ] 我的待办底稿 > 6 张时可看全部
- [ ] 提交复核弹窗文案风格与删除一致
- [ ] 版本冲突弹窗使用 confirmVersionConflict
- [ ] 顶栏可见"批注未读"badge
- [ ] 底稿保存 → 顶栏同步状态指示器显示"已保存"
- [ ] 附件拖拽可在 Workbench 和 Editor 都可用

### 项目经理

- [ ] 登录 → 侧栏"看板"默认指 /dashboard/manager
- [ ] 工时单入口 Tab 切换填报/审批/统计
- [ ] 管辖项目进度看板 vs 跨项目经理看板标题清晰
- [ ] 人员×项目矩阵可用
- [ ] 催办台 /my/reminders 可用
- [ ] 客户承诺是结构化表格，可勾选完成

### 质控

- [ ] 登录 → 落到 /qc/inspections
- [ ] QC 主工作台集成 6 Tab
- [ ] 项目级 QC 作为 ProjectDashboard 的 Tab（无独立 /projects/:id/qc-dashboard）
- [ ] 顶栏"质控"badge 显示本月应抽查项目数
- [ ] 规则编辑必须试运行才能保存

### 合伙人

- [ ] 登录 → 落到 /dashboard/partner
- [ ] 签字全景 Tab 可用，嵌入 GateReadinessPanel
- [ ] 待独立性声明项目单按钮 + 分页
- [ ] 合伙人私库分区可见
- [ ] 轮换状态卡片可用

### EQCR

- [ ] 登录 → /eqcr/workbench（独立性声明强制阻断）
- [ ] 5 判断 Tab 的"项目组值 vs 影子值"对比
- [ ] 备忘录版本历史切换
- [ ] EqcrMetrics 可见（eqcr 角色）
- [ ] 备忘录独立 Word 导出

---

## 六、不建议做的事（明确负面清单）

### 架构层面

- ❌ 不新增一级导航项（顶部已 10 项）
- ❌ 不引入新 UI 框架（Element Plus 已够用）
- ❌ 不把 Univer 换成其他电子表格
- ❌ 不做"多合伙人并行签字"（坚持串行）
- ❌ 不引入 GraphQL（REST + apiPaths 已稳定）

### 权限/合规层面

- ❌ 不给 partner 上"紧急绕过 GateRule"通道
- ❌ 不给 EQCR 直接对外联络客户
- ❌ 不给任何角色"编辑已归档报告"权限
- ❌ 不做"一键全通过所有底稿复核"
- ❌ 不做焦点时长后端落库（隐私决策已定）

### UX 层面

- ❌ 不加"AI 自动签字"
- ❌ 不在页面内加浮动悬浮球（干扰体验）
- ❌ 不在未完成填写时禁用所有其他入口（允许中断切换）
- ❌ 不加广告位 / 引导弹窗 / 气泡泡提示

### 数据层面

- ❌ 不删历史底稿数据（即使已归档）
- ❌ 不允许 ORM 层软删除绕过回收站
- ❌ 不做 DROP TABLE 的迁移脚本（只 ADD / MODIFY）

---

## 附录 A：代码锚点索引

| 章节 | 锚点文件 | 关键行 |
|------|---------|--------|
| 1.1 | `views/Dashboard.vue` | 52 (slice) |
| 1.1 | `views/WorkpaperEditor.vue` | 384, 445, 563 (ElMessageBox.confirm) |
| 1.2 | `layouts/ThreeColumnLayout.vue` | 324-335 (navItems) |
| 1.2 | `router/index.ts` | 232 (approve perm) |
| 1.3 | `router/index.ts` | 465-501 (qc 路由) |
| 1.4 | `views/PartnerDashboard.vue` | 561, 582 (硬编码) |
| 1.5 | `layouts/DefaultLayout.vue` | 131-134 (isEqcrEligible) |
| 1.5 | `views/eqcr/EqcrProjectView.vue` | 10 Tab 结构 |
| 2.1 | `views/WorkpaperList.vue` | 77-84 (硬编码颜色) |
| 2.1 | `components/common/` | 20 个全局组件 |
| 2.2 | `stores/roleContext.ts` | 37 (navItems) |
| 2.7 | `views/WorkpaperList.vue` | 1206-1215 (innerHTML 拼接) |
| 2.8 | `views/AttachmentHub.vue` + `AttachmentManagement.vue` | 两入口 |
| 2.9 | `views/ReviewInbox.vue` | 死代码 |
| 2.9 | `router/index.ts` | 119-128 (三条路由指同一 view) |
| 2.10 | `utils/statusMaps.ts` | 9 套 StatusMap |
| 2.10 | `components/common/GtStatusTag.vue` | 26 (桥接表) |
| 2.12 | `composables/useEditMode.ts` | 全文 |
| 2.13 | `stores/displayPrefs.ts` | 全文 |
| 2.13 | `styles/gt-tokens.css` | 76-80 (字体) |
| 2.14 | `composables/usePermission.ts` | 10-48 |
| 2.17 | `components/ai/` | 19 个组件（部分死代码） |
| 2.17 | `components/workpaper/AiContentConfirmDialog.vue` | 重复文件 |
| 3.1 | `router/index.ts` + `layouts/ThreeColumnLayout.vue:330` | /confirmation 不存在 |
| 3.2 | `views/QCDashboard.vue` | 325 (硬编码) |

---

## 附录 B：数据验证要点（本文所有数字均已 grep 核实）

| 断言 | 验证方式 | 结果 |
|------|---------|------|
| 73 个 .vue 视图 | `Get-ChildItem views/*.vue \| Measure-Object` | 73 |
| GtPageHeader 接入 6 个 | `Select-String -Pattern GtPageHeader -List` | 6 |
| GtEditableTable 接入 0 个 | 同上 | 0 |
| statusMaps.ts 9 套 | grep `export const` | 9 |
| components/ai/ 19 个 | Directory listing | 19 |
| navItems 硬编码 10 项 | ThreeColumnLayout.vue:325-335 | 10 |
| ReviewInbox.vue 无引用 | grep `ReviewInbox\.vue` | 无匹配 |
| /confirmation 无路由定义 | grep `path.*confirmation` | 无 |

本文件每轮打磨后更新；失效章节迁移到 dev-history.md。

（完）


---

## 七、横切主题补充（深度补完）

### 2.18 单元格选中与复制粘贴（Excel 级交互）

#### 2.18.1 现状

- `useCellSelection.ts`：单击/Ctrl多选/Shift范围选/鼠标拖拽框选/右键保持选区/selectionStats。文档级监听器用**引用计数共享**（`_instanceCount` + `_docClickCallbacks`），多实例不会泄漏。
- `useCopyPaste.ts`：HTML 表格 + 制表符纯文本双格式，兼容 Excel/Word 粘贴。
- `CellContextMenu.vue`：Teleport 到 body，含复制/查看公式/求和/对比差异四项 + slot（模块扩展）。
- **接入率**：只有 `TrialBalance / ReportView / DisclosureEditor / ConsolidationIndex` **4 个视图**接入。
- 其他编辑型视图（Adjustments / Misstatements / Materiality / WorkpaperList / WorkpaperSummary / CFSWorksheet）**没有 Excel 级选中**。

#### 2.18.2 问题清单

- **行选 / 列选 / 全选缺失**：当前只支持单元格选中，不支持"点行号选整行"、"点列名选整列"。Excel 标准行为缺失。
- **跨表格复制不一致**：某些视图用 `GtToolbar` 的 "复制整表"（CSV 格式），某些用右键"复制选中区域"（HTML），第三处用 `useCopyPaste.copySelection`，输出格式不统一。
- **粘贴入库缺失**：用户从 Excel 复制 100 行粘贴到 `Adjustments.vue`，当前不会"粘贴新增行"，只能一行一行手敲。
- **撤销不覆盖单元格编辑**：`operationHistory` 只接"删除/清空"动作，单元格误改无 Ctrl+Z。
- **选区统计只在 TrialBalance 显示**：`SelectionBar.vue` 求和/计数/平均在右上角，但只有 TrialBalance 挂了，其他视图没有。
- **键盘导航不全**：`useKeyboardNav` 只在 `GtEditableTable` 内部用，其他表格 Tab/方向键不响应。
- **右键菜单模块扩展断层**：`CellContextMenu` 的 `<slot />` 支持模块追加菜单项，但现有 4 接入视图都没用，"穿透到序时账"、"打开底稿"、"插入公式引用"等上下文动作都不在右键。

#### 2.18.3 建议（Excel 级全量行为）

**A. 选中能力升级**

扩展 `useCellSelection` 增加：
- `selectRow(rowIdx)` 选整行（点行号触发）
- `selectColumn(colIdx)` 选整列（点列名触发）
- `selectAll()` 选全部（Ctrl+A，表格 focus 时）
- `shrinkSelection() / expandSelection()` 方向键扩展选区（Ctrl+Shift+方向）

**B. 统一复制策略**

`utils/clipboard.ts` 新建：
```ts
export function copyRange(
  data: Record<string, any>[],     // 表格数据
  range: { r1, c1, r2, c2 },       // 矩形选区
  columns: ColDef[],                // 列定义
  format: 'html' | 'tsv' | 'csv' = 'tsv',
): Promise<void>
```

- 右键"复制选中区域"、工具栏"复制整表"、Ctrl+C 三入口统一调用，输出格式一致
- 去除 `useCopyPaste` 与 GtEditableTable 内置复制的重复

**C. 粘贴入库（PasteImport）**

新建 composable `usePasteImport.ts`：
- 监听表格容器 paste 事件
- 解析剪贴板（`text/plain` 制表符 / `text/html` 表格）
- 若选中单元格数 < 粘贴数据行数 → 弹"是否新增 X 行"确认
- 触发各视图的 `onPasteInsert(rows)` 回调

在 `Adjustments / Misstatements / Materiality / WorkpaperSummary` 接入。

**D. 右键菜单模块扩展**

按模块追加右键项，通过 `<template #extra>` 插槽：

| 视图 | 追加项 |
|------|------|
| TrialBalance | 穿透到序时账 / 打开底稿 / 查看调整分录 |
| ReportView | 穿透到行明细 / 查看公式 / 导出该行 |
| WorkpaperList | 打开编辑 / 分配复核人 / 查看历史 |
| Adjustments | 转未更正错报 / 复制分录到其他项目 |
| DisclosureEditor | 取数到该单元格 / 插入公式 |

**E. 单元格编辑撤销**

扩展 `operationHistory` 接收 `cell_edit` 类型：
```ts
await operationHistory.execute({
  type: 'cell_edit',
  description: `修改 ${ref} 从 ${oldVal} 为 ${newVal}`,
  execute: async () => { /* write via onChange */ },
  undo: async () => { /* restore oldVal */ },
})
```

所有 `@input` / `@change` 事件挂此 history，让用户 Ctrl+Z 恢复到上 1 步。

**F. 选区统计栏全铺**

`SelectionBar.vue` 挂到所有接入 useCellSelection 的视图顶部（选中 >= 2 格即显示），展示：求和 / 平均 / 计数 / 最大 / 最小。

#### 2.18.4 工作量估算

- A+B+F：全局 1 周
- C+D+E：跟随各视图迁移，每视图 +0.5 天


### 2.19 四表-报表-底稿-附注联动（审计业务核心链路）

#### 2.19.1 现状（后端已经"拉通"，前端没有呈现拉通）

后端 `event_handlers.py` 已注册完整联动链路：
- `ADJUSTMENT_*` → TB 重算（`on_adjustment_changed`）
- `TRIAL_BALANCE_UPDATED` → 报表增量更新（`ReportEngine.on_tb_updated`）
- `REPORTS_UPDATED` → 审计报告财务数据刷新（`AuditReportService.on_reports_updated`）
- `WORKPAPER_SAVED` → 审定数比对（`ConsistencyCheckService.update_workpaper_consistency`）
- `LEDGER_DATASET_ACTIVATED / ROLLED_BACK` → 所有底稿 stale 标记
- `ADJUSTMENT_*` → 底稿 stale 标记（by_account 粒度）
- `MAPPING_CHANGED` → TB 重算
- `ADJUSTMENT_* / TB / REPORTS` → 公式缓存/地址注册表失效

前端事件总线对应：`workpaper:saved` / `workpaper:parsed` / `materiality:changed` / `formula-changed` / `sse:sync-event` / `sse:sync-failed`。

#### 2.19.2 问题

- **联动链路对用户不可见**：调了一笔分录后，TB / 报表 / 底稿 / 附注不会自动"变红提醒"或"提示刷新"，用户不知道什么被动了。
- **穿透入口散**：`reports/drilldown/{row_code}` / `drilldown/ledger/{code}` / `ledger/penetrate` / `consol_worksheet/drill/*` / `penetrate-by-amount` 五套 drilldown 端点并存，前端入口位置不一致。
- **stale 状态前端没渲染**：后端已标 `workpaper.is_stale=true`，但 `WorkpaperList.vue` / `TrialBalance.vue` 的底稿一致性列**只判断 `consistent/inconsistent`**，不展示 `stale`（过期需重算）。
- **"从报表行到底稿"双向缺失**：可从 TB 到底稿（consistency 列 ✅），但从**报表项目**直接打到**对应底稿**的入口无。合伙人复核报告时想"点开这一行看它的底稿"点不了。
- **附注数据源联动**：附注取数来自底稿 fine_summary / audited / TB（memory 已记录优先级），但**附注单元格不显示数据来源**，合伙人无法验证"这个数字是从哪来的"。
- **四表（资产负债表+利润表+现金流+所有者权益变动）联动**：`ReportView.vue` 已实现，但**跨表核对公式**（如"本年净利润 = 利润表净利润 = 所有者权益变动表本年净利润 = 现金流量表补充资料净利润"）没有专门的"核对视图"。

#### 2.19.3 建议

**A. 统一穿透入口 + 全站双击/右键穿透**

新建 `composables/usePenetrate.ts`：
```ts
export function usePenetrate() {
  const router = useRouter()
  return {
    toLedger: (accountCode: string) => router.push(`/projects/${pid}/ledger?code=${accountCode}`),
    toWorkpaper: (wpCode: string) => { /* 通过 wp 映射跳转 */ },
    toReportRow: (type: string, rowCode: string) => { /* 报表行 drilldown */ },
    toAdjustment: (entryGroupId: string) => router.push(`/projects/${pid}/adjustments?group=${entryGroupId}`),
    toMisstatement: (id: string) => router.push(`/projects/${pid}/misstatements?id=${id}`),
    toNote: (noteId: string) => router.push(`/projects/${pid}/disclosure-notes?note=${noteId}`),
  }
}
```

所有金额单元格统一行为：
- **双击** → 按金额+科目 `penetrate-by-amount` 查到凭证
- **右键** → 菜单里列 5 个穿透目标（§2.18.3 D）
- **Shift+双击** → 打开对应底稿

**B. Stale 状态可视化**

`WorkpaperList.vue` / `TrialBalance.vue` 的一致性列增加第三态：
- ✅ consistent（绿）
- ⚠️ inconsistent（红，有差异）
- 🔄 stale（蓝，上游变了需重算）

点击 stale 图标弹窗"原因：2025-05-07 调整了 1622.01 科目分录 3 笔"，按钮"立即重算"。

**C. 报表行 → 底稿反向跳**

`ReportView.vue` 行级操作菜单（右键）新增"打开对应底稿"。后端端点 `GET /api/reports/{pid}/{year}/{type}/{row_code}/related-workpapers` 返回与该行映射的 wp 列表，前端多条时弹选择对话框。

**D. 附注单元格溯源**

参考 R4 的 `cell_provenance`，扩展到附注：
- `parsed_data.cell_provenance[cell_ref]` 记录 source type（trial_balance/workpaper/formula/manual） + source_ref
- 附注单元格 hover 显示 `<CellProvenanceTooltip>`（组件已存在于 workpaper/）
- 右键菜单增加"跳转到数据源"

**E. 跨表核对视图**

`ReportView.vue` 新增"跨表核对"Tab：
- 并排显示 4 张表的关键勾稽关系
- 自动校验 "利润表净利润 = 所有者权益变动表未分配利润本年增加数"、"现金流量表期末现金 = 资产负债表期末货币资金"等 7-10 条关键等式
- 不平时高亮红色，可点击"定位差异"

**F. 全局"联动状态"横条**

当 TB/报表/底稿/附注中任一被标记为 stale 时，顶部加一条横条提示 "当前项目有 3 处数据过期，[一键重算]"。类似 VS Code 顶部的 "Git branch 有未推送提交"。


### 2.20 协同编辑与并发锁

#### 2.20.1 现状

- 后端 R4 已建 `workpaper_editing_locks` 表：有效锁 = `released_at IS NULL AND heartbeat_at > now - 5min`，惰性清理。
- 前端**只有 `StructureEditor.vue`（formula 模块）** 实现了 acquireLock / releaseLock + `lockRefreshTimer`。
- `WorkpaperEditor.vue` / `DisclosureEditor.vue` / `AuditReportEditor.vue` 这些大型编辑器 **没接入编辑锁**，两人同时开同一底稿会互相覆盖。
- 版本冲突（`VERSION_CONFLICT`）只在保存失败时弹窗（`WorkpaperEditor.vue:384`），太晚。
- 没有"谁在编辑这个文件"的 presence 指示。

#### 2.20.2 建议

**A. 编辑锁统一 composable**

`composables/useEditingLock.ts`：
```ts
export function useEditingLock(params: {
  resourceType: 'workpaper' | 'disclosure' | 'audit_report'
  resourceId: Ref<string>
  heartbeatInterval?: number  // 默认 2 分钟
}) {
  // 进入编辑模式时 acquire
  // 心跳每 heartbeatInterval 刷一次
  // beforeUnload 自动 release
  // 返回 { locked, lockedBy, isMine, refresh, release }
}
```

在 `WorkpaperEditor / DisclosureEditor / AuditReportEditor / ReportConfigEditor / TemplateManager` 接入。

**B. Presence 指示**

- 顶部横条显示 "另一位审计员（李四）正在编辑此底稿"，本人只能进入"只读模式"
- SSE 事件 `editing:started { resource_id, user_id }` 推送给所有订阅者
- 类似 Google Docs 多人头像显示

**C. 强制接管**

- Partner/admin 可点击"强制接管"按钮，弹窗确认后：后端标记原锁失效 + SSE 通知原编辑者切只读
- 审计日志记录接管事件

**D. 离线冲突**

- `OfflineConflictWorkbench.vue` 已存在，挂到"项目设置"下的隐藏入口
- 网络断开时前端缓存修改到 IndexedDB，重连后 post diff，冲突走此 workbench 手动解决

### 2.21 快捷键与全站键盘体系

#### 2.21.1 现状

- `utils/shortcuts.ts` 有 `ShortcutManager` 全局单例，共注册 13 个 `shortcut:*` 事件（save/undo/redo/search/goto/export/submit/escape/refresh/help/tab-focus/list-up/list-down）。
- 输入框聚焦时自动忽略（除 Escape）。
- **没有快捷键帮助面板**：`shortcut:help` 事件定义了但没有 UI 监听。

#### 2.21.2 建议

**A. "?" 键唤起快捷键帮助**

新建 `components/common/ShortcutHelpDialog.vue`：
- 按 "?" 或 F1 触发
- 按 scope 分组展示 `shortcutManager.getAll()` 的全部快捷键
- 支持搜索

**B. 统一快捷键表**

| 快捷键 | 功能 | 生效范围 |
|--------|------|---------|
| Ctrl+S | 保存 | 编辑页 |
| Ctrl+Z | 撤销 | 全站（operationHistory） |
| Ctrl+Y / Ctrl+Shift+Z | 重做 | 全站 |
| Ctrl+F | 表内搜索 | 表格页 |
| Ctrl+K | 全局搜索 | 全站 |
| Ctrl+P | 打印 | 编辑页 |
| Ctrl+E | 导出 | 编辑页 |
| Ctrl+Enter | 提交 | 复核/错报转换 |
| Esc | 退出全屏 / 关闭弹窗 | 全站 |
| F1 或 ? | 快捷键帮助 | 全站 |
| F5 | 刷新数据 | 数据页 |
| G+P | goto 项目 | 全站 |
| G+W | goto 我的底稿 | 全站 |
| G+R | goto 复核收件箱 | 全站 |

**C. 每页顶部"键盘图标"入口**

顶栏加 `⌨️` icon，点击唤起帮助对话框。对新用户友好。

### 2.22 导出与打印

#### 2.22.1 现状

- Excel 导出：`export-excel` 端点在 reports / audit-report / excel-html/module 多处
- Word 导出：AuditReport / Disclosure / module / StructureEditor
- PDF 导出：WorkpaperEditor / archive / LibreOffice 依赖
- 打印：`GtPrintPreview.vue` + `styles/gt-print.css`，但**只在少数视图接入**

#### 2.22.2 问题

- 导出入口散在各页面，风格不统一
- 没有"导出中心"（合并导出多个报表到一个 zip）
- 打印样式 `gt-print.css` 存在但大多数页面直接打印会混乱

#### 2.22.3 建议

**A. 导出中心**

新建 `views/ExportCenter.vue`（/projects/:id/export）：
- 用户勾选要导出的内容（TB / 4 张报表 / 附注 / 底稿 / 审计报告 / 归档包）
- 一次打包 zip 下载
- 后端端点 `POST /api/projects/{pid}/export/bundle`

**B. 打印预设**

- 每个可打印视图注入 `<GtPrintPreview>`：Ctrl+P 触发，先预览再打印
- 打印样式强制：A4 纵向、页眉（项目名+年度）、页脚（页码+打印时间+操作员）
- 金额列打印时强制"元"单位（避免 displayPrefs 误导客户）

**C. 水印**

- 所有导出 PDF 默认加"致同会计师事务所审计工作底稿 · 机密"水印
- 归档包 manifest_hash 已做 SHA-256，但**水印**与 hash 分离展示

**D. 导出权限**

- 所有导出按钮挂 `v-permission="'xxx:export'"`
- 导出日志记录到 audit_log（谁、何时、导出了什么）

### 2.23 通知中心与催办

#### 2.23.1 现状

- `NotificationCenter.vue` 挂在顶栏 slot，30 秒轮询 + SSE 实时刷新
- 通知类型在 `notificationTypes.ts`（R1 Task 19 创建）
- 催办散落在 WorkpaperList / ProjectDashboard

#### 2.23.2 建议

**A. 通知分类 Tab**

`NotificationCenter.vue` 下拉面板加 Tab 分类：
- 复核相关（提交复核 / 退回 / 批注）
- 催办（我收到的 / 我发出的）
- 系统（版本发布 / 维护通知）
- AI（AI 待确认）

**B. "免打扰"时段**

- 用户个人设置"免打扰时段"（18:00 - 9:00，默认开）
- 期间不弹 el-notification，但仍累计计数

**C. 催办升级链**

- 已有"L2/L3/Q SLA 超时通知签字合伙人"后端逻辑
- 前端可视化：`/my/reminders` 显示升级时间线

### 2.24 回收站与软删除（全局规则）

#### 2.24.1 现状

- `RecycleBin.vue` 完备，支持恢复/永久删除/清空全部
- 所有软删除经 `SoftDeleteMixin` + `operationHistory` 记录
- 用户偏好"删除必须二次确认"已在 confirm.ts 落地

#### 2.24.2 建议

**A. TTL 自动清理**

- 回收站记录保留 90 天，超期后台 job 物理删除
- 删除前 7 天通过 NotificationCenter 通知拥有人
- 后台 job 在 workers/ 新增 `recycle_bin_cleanup_worker.py`

**B. 回收站容量告警**

- 单项目回收站 > 500 条 / > 1 GB 时顶栏提示

**C. 恢复权限**

- 自己删的自己可恢复
- 别人删的需要对应权限或 admin

### 2.25 移动端策略决断

#### 2.25.1 现状

- `MobilePenetration / MobileReview / MobileReport / MobileProjectList / MobileWorkpaperEditor` 5 视图全是 stub
- `ThreeColumnLayout.vue` 的 `onTouchStart / onTouchEnd` 已支持左右滑展开/收起导航

#### 2.25.2 建议

**方案 A（推荐）：整体删除**
- 现阶段审计工作台定位是"桌面端"，移动端不是核心场景
- 删除 5 stub + 对应 router 条目
- `ThreeColumnLayout` 的移动端媒体查询保留（响应式）
- Round 8+ 若确有需求再独立立项

**方案 B：保留但放一级隐藏**
- 仅保留 `MobileProjectList`（项目列表）给合伙人差旅途中看进度
- 其他 4 个删除


### 2.26 错误处理与 API 响应规范

#### 2.26.1 现状

- `composables/useApiError.ts` 有 `parseApiError` 抽取错误
- `utils/http.ts` 响应拦截器自动解包 ApiResponse
- `api.get` 返回 unwrapped data（409 时返回 `{detail: {...}}`，靠 `validateStatus=s<600`）
- `ErrorBoundary.vue` 包裹 router-view

#### 2.26.2 问题

- 前端错误弹窗五花八门：`ElMessage.error('操作失败: ' + e.message)` / `ElMessage.error('加载失败')` / 静默吞掉
- 网络错误（超时/断网）与业务错误（400/409/403）处理混杂
- 长操作（生成 Word / 重算报表）没有 Loading 遮罩，用户不知道是卡了还是在执行

#### 2.26.3 建议

**A. 错误规范**

`utils/errorHandler.ts`（新建）提供 3 级策略：
```ts
export function handleApiError(e: any, context: string) {
  // 网络错误 → "网络不通，请检查连接"
  // 401 → 自动刷新 token（已有）
  // 403 → "无权操作"
  // 404 → "资源不存在"
  // 409 → 显示后端 detail.message + 冲突详情对话框
  // 5xx → 显示 "系统错误，请联系管理员" + 记录 trace_id
}
```

所有 catch 块统一 `handleApiError(e, '保存底稿')`，不再手搓 message。

**B. Loading 策略**

- 快速请求（< 500ms）：不显示 loading
- 中等（0.5 - 3s）：el-loading 局部遮罩
- 长操作（> 3s）：顶部进度条（NProgress 已在路由用，扩展到关键 API）
- 异步任务（生成归档包）：后端 job 模式 + 前端轮询，NotificationCenter 完成通知

**C. Trace ID 暴露**

- 后端已有 `RequestIDMiddleware` 生成 trace_id
- 前端 error toast 右下角加"复制 trace id"小按钮，方便用户报错时粘贴

### 2.27 国际化与多语言

#### 2.27.1 现状

- `i18n/` 存在（en-US.json, zh-CN.json, index.ts）
- 大量文案仍硬编码中文

#### 2.27.2 建议

（次优先级，R7+ 再做）

- 当前确认只做中文
- 把 `i18n/en-US.json` 保留骨架，不投入人力翻译
- 禁止新代码继续加 i18n key 注入（维护负担）
- 未来客户有英文需求再启动

### 2.28 审计日志与用户行为可追溯

#### 2.28.1 现状

- 后端 `@audit_log` 装饰器已覆盖删除/审批/状态变更
- 审计日志种子 `audit_log_rules_seed.json`（AL-01~05）
- 前端无"我的操作历史"视图

#### 2.28.2 建议

**A. 我的操作历史视图**

- `PersonalDashboard.vue` 新增 Tab "我的操作"，查看自己近 7 天的重要操作
- 合伙人/admin 可跨用户查询，`/settings/audit-logs`

**B. 关键操作二次确认增强**

以下操作除了 confirmDangerous 弹窗，还应**要求重新输入密码**：
- 永久删除项目
- 强制签字（admin 绕过 gate）
- 强制接管编辑锁
- 导出含客户 PII 的报告

**C. 审计日志保留期**

- 日志保留 2 年（符合审计工作底稿保存要求）
- 每年归档到冷数据存储（S3 Glacier / SFTP）

### 2.29 性能与大数据量

#### 2.29.1 现状

- `VirtualScrollTable.vue` 已有虚拟滚动
- `GtEditableTable` 支持大表格
- load_test.py 双模式压测

#### 2.29.2 问题

- VirtualScrollTable 接入面小，大多数视图用 el-table 原生（>500 行卡顿）
- TrialBalance.vue 6000 行科目时渲染 >3s
- ReportView 切 tab 每次重新请求，无前端缓存

#### 2.29.3 建议

**A. 虚拟滚动铺开**

- TB / 序时账 / 大型底稿 / AttachmentHub 等 > 500 行视图强制用 VirtualScrollTable
- 设定阈值：行数 > 200 自动开启

**B. 前端缓存**

- 引入 `@tanstack/vue-query`（memory 记录 queryClient 已引入）
- 报表 / TB / 底稿 列表统一走 query cache，切 tab 不重请求
- 缓存 TTL 2 分钟，SSE 收到相关事件时 invalidate

**C. 图表异步**

- GTChart 组件用 `<Suspense>` 包装，数据未 ready 先显示 skeleton
- 避免首屏等待图表数据

### 2.30 空态与首次使用引导

#### 2.30.1 现状

- `useWorkflowGuide` composable 有 8 个预定义引导
- 空态用户偏好"全宽简洁（图标+一句话+一个按钮）"
- 部分视图已遵守（KnowledgeBase / Projects），部分违反（PBC / Confirmation 直接空白或开发中）

#### 2.30.2 建议

**A. 统一空态组件**

新建 `components/common/GtEmpty.vue`：
```
<el-empty :image-size="80">
  <h4>{{ title }}</h4>
  <p>{{ description }}</p>
  <el-button type="primary" @click="$emit('action')">{{ actionText }}</el-button>
</el-empty>
```

所有空态必须经此组件，文案不再自由发挥。

**B. 首次使用引导**

- auditor 首次登录后触发引导：去填第一张底稿、去填工时、去看复核收件箱
- manager 首次登录：去委派、去批工时、去看进度板
- 每个引导走 `useWorkflowGuide` 单次触发，存 localStorage `gt_guide_completed_xxx`

**C. 空壳页（developing）体验**

- 当前 developing 路由跳 `DevelopingPage.vue`（"开发中"）
- 建议 `DevelopingPage` 增加 "计划排期" 和 "订阅上线通知"功能，让用户知道什么时候能用


### 2.31 全屏与多视图工作模式

#### 2.31.1 现状

- `useFullscreen` composable 已在 17 视图接入
- 三栏 / 四栏切换在顶部视图切换按钮

#### 2.31.2 建议

**A. 双视图并列**

某些场景用户希望"左边 TB，右边底稿"同屏对照。建议：
- 顶栏加"分屏"按钮，点击后把当前视图拆成左右两栏
- 右栏通过"固定"按钮钉一个视图
- 实现：路由 query `split_right=/projects/xxx/workpapers/yyy`

**B. 记忆布局**

- 用户上次折叠中间栏/四栏位置记到 localStorage（已做）
- 额外记"分屏内容"和"分屏比例"

### 2.32 搜索/筛选/排序规范

#### 2.32.1 现状

- `useTableSearch` 行内搜索
- 表格列 sortable / filter 用 Element Plus 原生

#### 2.32.2 建议

**A. 筛选即过滤 URL**

所有表格筛选条件写入 URL query：`?client=XX&year=2025&status=draft`
- 刷新页面保持筛选
- 分享链接即分享筛选状态

**B. 保存筛选视图**

- 用户可对当前筛选条件"另存为视图"
- 侧栏显示"我的视图"列表
- 后端 `user_views` 表

**C. 多列排序**

- Element Plus 默认单列排序
- 升级为多列：Shift+点击列头加次序
- 用 `useMultiSort` composable 封装

### 2.33 用户个人设置

#### 2.33.1 现状

- `displayPrefs` 覆盖金额/字号/负数红等
- `SystemSettings.vue` 是**系统设置**（管理员功能），不是个人设置
- 用户没有"我的设置"集中管理页

#### 2.33.2 建议

**A. 新建 `/my/settings`**

- Tab 1：显示偏好（同 "Aa" 面板）
- Tab 2：通知偏好（邮件 / 站内信 / 免打扰时段）
- Tab 3：键盘偏好（是否启用快捷键）
- Tab 4：安全（改密码 / 查看登录历史）
- Tab 5：头像 / 签名档

**B. 与 SystemSettings 区分**

- `/settings` = 系统级（admin）
- `/my/settings` = 个人级（所有登录用户）

### 2.34 埋点与运营数据

#### 2.34.1 现状

- `utils/monitor.ts` + `webVitals.ts` 已上报 Web Vitals + 请求日志
- 没有业务埋点

#### 2.34.2 建议（低优，R8+）

**A. 关键业务动作埋点**

- 建项数 / 底稿数 / 平均编制时长 / 平均复核时长 / 被退回率
- AI 使用率（被采纳 / 被修改 / 被拒绝）
- 各角色使用频次

**B. 埋点数据面板**

- admin 视角 `/admin/analytics`
- 用 Metabase（已 metabase.py 端点）直连只读库

---

## 八、最终落地优先级表（P0 → P3，35 项）

### P0（本周内做，零~低风险，高收益）—— 9 项，总工时 1 天

1. 删除 ReviewInbox.vue
2. 修复 PartnerDashboard.vue 2 处硬编码 + QCDashboard.vue:325 硬编码
3. EqcrMetrics 对 eqcr 角色开放
4. 登录后角色跳转
5. 删除 MobileXxx 5 视图（含 router）
6. /confirmation 路由修复或移除侧栏
7. AI 组件死代码清理（Contract/EvidenceChain）+ AiContentConfirmDialog 去重
8. confirm.ts 补齐语义化函数（confirmSubmitReview/confirmVersionConflict/confirmLeave）
9. 统一空态组件 GtEmpty.vue 创建

### P1（2 周内做，中风险）—— 12 项

10. 侧栏 navItems 动态化（角色感知）
11. 全局替换 ElMessageBox.confirm → confirm.ts
12. 所有编辑页接入 useEditMode
13. useEditingLock composable + 5 个编辑器接入
14. useWorkpaperAutoSave 独立 composable
15. 工时填报/审批 Tab 合并 + GtStatusTag
16. 右键菜单模块扩展（5 视图注入 slot）
17. 单元格编辑纳入 operationHistory（Ctrl+Z 可撤）
18. Stale 状态三态可视化
19. 错误处理规范 errorHandler.ts 铺开
20. Trace ID 暴露到 error toast
21. 快捷键帮助面板 `?` 唤起

### P2（一个月内做，需 spec 三件套）—— 10 项

22. 全局组件铺设 Sprint（GtPageHeader 6→73）
23. statusMaps → dictStore 单向收敛
24. QC 主工作台升级 + 项目级 QC Tab 化
25. EQCR 5 Tab 影子对比 + 备忘录版本
26. 底稿右栏面板统一 WorkpaperSidePanel
27. 客户主数据 + 项目标签
28. v-permission 全按钮铺设
29. 单元格选中升级（行/列选/Ctrl+A/粘贴入库）
30. 四表-报表-底稿-附注统一穿透 usePenetrate
31. 跨表核对视图 + 联动状态横条

### P3（后续迭代）—— 4 项

32. Ctrl+K 全局搜索
33. AI 待确认聚合 + 会话持久化
34. 导出中心 + 水印
35. 用户个人设置 `/my/settings`

---

## 九、关键代码锚点索引（补增部分）

| 章节 | 锚点文件 | 关键行/函数 |
|------|---------|--------|
| 2.18 | `composables/useCellSelection.ts` | 全文（含引用计数设计） |
| 2.18 | `composables/useCopyPaste.ts` | copySelection |
| 2.18 | `components/common/CellContextMenu.vue` | 全文 |
| 2.19 | `backend/app/services/event_handlers.py` | 订阅链路全文 |
| 2.19 | `utils/eventBus.ts` | Events 映射表 |
| 2.19 | `backend/app/routers/drilldown.py` | 穿透端点 |
| 2.19 | `backend/app/routers/penetrate_by_amount.py` | 按金额穿透 |
| 2.20 | `components/formula/StructureEditor.vue` | acquireLock/releaseLock 范式 |
| 2.20 | `views/OfflineConflictWorkbench.vue` | 离线冲突 |
| 2.21 | `utils/shortcuts.ts` | 13 shortcut 事件 |
| 2.22 | `styles/gt-print.css` + `components/common/GtPrintPreview.vue` | 打印 |
| 2.23 | `components/collaboration/NotificationCenter.vue` | 轮询 30s + SSE |
| 2.24 | `views/RecycleBin.vue` | operationHistory 集成 |
| 2.26 | `composables/useApiError.ts` + `utils/http.ts` | 错误处理 |
| 2.29 | `components/common/VirtualScrollTable.vue` | 虚拟滚动 |
| 2.30 | `composables/useWorkflowGuide.ts` | 8 引导预定义 |

---

## 十、本文与 v1 前版的增量说明

v1 前版（~800 行）覆盖：5 角色穿刺 + 17 主题 + 4 级路线图
v1 当前版（~1500 行）补充：

**新增 15 主题（§2.18 - §2.34）**：
- 单元格选中/复制粘贴（Excel 级交互）
- 四表-报表-底稿-附注联动可视化
- 协同编辑锁（Presence + 强制接管）
- 快捷键帮助 + 全站键盘体系
- 导出中心 + 打印规范 + 水印
- 通知分类 + 免打扰
- 回收站 TTL 自动清理
- 移动端决断（建议整体删除）
- 错误处理规范 + Trace ID 暴露
- 国际化（暂不投入）
- 审计日志用户可见化
- 虚拟滚动铺开 + 前端缓存
- 空态统一 + 首次引导
- 双视图并列
- 筛选保存 + 多列排序
- 用户个人设置
- 业务埋点（R8+）

**新的量化**：
- useCellSelection 接入视图 4/73
- 编辑锁前端仅 1 个（StructureEditor）
- 撤销仅接 2 动作（Adjustments 删除 + RecycleBin 删除）
- 通知中心仅 30s 轮询 + SSE，无分类无免打扰

（完）


---

## 十一、全局功能与组件库的版面位置规约

目标：每个全局功能和组件都有**唯一的归属位置**，禁止同一功能在多个位置重复出现。下面按"从上到下、从左到右"的 DOM 结构展开。

### 11.0 版面分层总览

审计平台 UI 分为 **4 层 × 10 区**：

```
┌─────────────────────────────────────────────────────────────────┐
│ 顶栏 Topbar (52px)                                              │
│  ├ 左：Logo + 面包屑                                            │
│  ├ 中：全局搜索（新，Ctrl+K 触发）                              │
│  └ 右：工具簇（展示/视图/通知/入口）+ 用户菜单                   │
├──────┬───────────────┬──────────────────────────────────────────┤
│ 左栏 │   中栏         │    右主内容区                             │
│ Nav  │ Middle       │    Detail（四栏时前再有 Catalog 栏）      │
│ (导航) │ (清单/目录)   │  ┌──────────────────────────────────┐  │
│      │              │  │ 页面横幅 GtPageHeader             │  │
│      │              │  │  ├ 返回 + 标题                    │  │
│      │              │  │  ├ 信息栏 GtInfoBar（单位/年度/模板）│  │
│      │              │  │  └ 操作栏 GtToolbar（复制/导入导出/全屏/公式/模板/编辑切换）│
│      │              │  ├──────────────────────────────────┤  │
│      │              │  │ 联动状态横条（新，仅 stale 时出现）│  │
│      │              │  ├──────────────────────────────────┤  │
│      │              │  │ 页面主体（表格 / 编辑器 / 图表）   │  │
│      │              │  │  ├ 搜索栏 TableSearchBar（紫带）   │  │
│      │              │  │  ├ 选区状态栏 SelectionBar         │  │
│      │              │  │  └ 主内容（el-table / GtEditableTable / Univer）│
│      │              │  ├──────────────────────────────────┤  │
│      │              │  │ 底部分页 + 统计                   │  │
│      │              │  └──────────────────────────────────┘  │
│      │              │  ┌──── 右栏抽屉（按需）──────────────┐  │
│      │              │  │ AI / 附件 / 版本 / 批注 / 程序要求 │  │
│      │              │  └──────────────────────────────────┘  │
├──────┴───────────────┴──────────────────────────────────────────┤
│ 悬浮层（Teleport to body）                                       │
│  ├ 右键菜单 CellContextMenu                                     │
│  ├ 弹窗 el-dialog / 抽屉 el-drawer                              │
│  ├ 通知气泡 el-notification                                     │
│  ├ 全局搜索面板（新，Ctrl+K）                                   │
│  └ 快捷键帮助面板（新，? 或 F1）                                │
└─────────────────────────────────────────────────────────────────┘
```

### 11.1 顶栏 Topbar 位置（52px 高）

**证据**：`ThreeColumnLayout.vue:4-138`

#### 11.1.1 左区：Logo + 面包屑（保留不动）

- Logo（点击折叠导航）
- el-breadcrumb（首页 / 当前模块）

#### 11.1.2 中区：**新增 — 全局搜索**

**位置**：`gt-topbar-center` 区域，面包屑右侧
**组件**：新建 `GlobalSearchBar.vue`
**触发**：Ctrl+K 或点击搜索框
**样式**：半宽浅色边框 input，placeholder "🔎 搜项目/底稿/附注/附件/知识库（Ctrl+K）"
**交互**：点击 / Ctrl+K 展开为悬浮面板（Teleport to body）

对应 `utils/shortcuts.ts` 的 `shortcut:search` 事件。

#### 11.1.3 右区：工具簇（重新组织）

现状右侧工具簇顺序：知识库 / 私人库 / AI 模型 / 排版模板 / 吐槽求助 / 公式管理 / 自定义查询 / **Aa（显示设置）** / 视图切换 / 回收站 / 系统设置 / 导入指示 / SyncStatus / 复核收件箱 / 通知 / EQCR / 头像

**问题**：14 个图标挤在 52px 高顶栏，新用户一脸懵

**治理方案 — 三簇分组**：

| 簇 | 图标顺序 | 归属建议 |
|----|---------|---------|
| **角色动作簇**（高频，保留顶栏） | 📋复核收件箱 · 🔔通知 · 🛡️EQCR · 📊EQCR 指标 | 已在顶栏，不动 |
| **显示偏好簇**（可见） | Aa（显示设置）· 🌓（主题切换，新）| 顶栏保留 Aa |
| **全站工具簇**（折叠到"⚙️ 工具箱"下拉） | 知识库 / 私人库 / AI 模型 / 排版模板 / 吐槽求助 / 公式管理 / 自定义查询 / 回收站 / 系统设置 / 键盘帮助 | **新增 `⚙️ 工具箱` el-dropdown**，点击弹下拉菜单 |

这样顶栏从 14 图标 → 6-7 图标，视觉负担减半。角色动作簇是"每天必用"，偏好簇是"偶尔调"，工具箱是"少用但全"。

#### 11.1.4 右区：**新增 — 全局保存状态指示（编辑页可见）**

**位置**：Aa 左侧（如当前路由是编辑页）
**组件**：`SaveStatusBadge.vue`
**显示**：✓ 已保存 / ⏳ 保存中 / ⚠ 未保存 X 分钟
**交互**：点击触发 `shortcut:save` 立即保存

### 11.2 左栏 Nav 位置（导航）

**证据**：`ThreeColumnLayout.vue:140-176`

#### 11.2.1 顶部保留：仪表盘 / 项目 / 人员 / 工时 / 看板 / ...（10 项硬编码）

按 §2.2 动态化改造，**按角色显示不同项**。

#### 11.2.2 **新增：底部"我的"区（分割线下方）**

- 我的待办（/my/dashboard）
- 我的催办（/my/reminders）
- 我的 AI 待确认（/my/ai-inbox）
- 我的操作历史（/my/audit-logs）

这些放**收起按钮（gt-sidebar-bottom）之上**，为"聚合入口"区。

#### 11.2.3 左栏宽度策略

折叠时 56px，展开时 180-300px（已可拖拽）。建议：新用户默认展开，高频用户折叠后把鼠标 hover 自动临时展开 200ms（Windows 开始菜单风格）。

### 11.3 中栏 Middle（项目清单 / 占位）

**当前**：`MiddleProjectList.vue` / `MiddlePlaceholder.vue` / `ConsolMiddleNav.vue`

**建议新增**：

- 中栏顶部加**全局筛选条**（仅当前模块上下文有效），例：项目模块中可筛选"活跃/归档/全部 + 负责人 + 年度"
- 中栏底部加**"最近访问"折叠区**，显示用户最近打开的 5 个项目/底稿

### 11.4 右主内容区（Detail）— 页面结构规约

这是本次规约的重点。**所有项目子页面必须遵守此结构**。

#### 11.4.1 第一行：页面横幅 GtPageHeader（必需）

**组件**：`components/common/GtPageHeader.vue`
**位置**：`gt-detail` 的第 1 个子元素
**规范**：
- `title` 必填（主模块名）
- 默认 slot 放 `<GtInfoBar>`（单位/年度/模板/口径）
- `#actions` slot 放 `<GtToolbar>`（所有表格操作按钮）
- `showSyncStatus` 对接 SSE

**现状**：只有 6/73 视图用了。P2 优先项（§2.1）是把剩余 67 个统一迁过来。

**禁止**：
- 不得在 detail 内另写 `.banner` / `.page-header` / `.gt-wpb-banner` 等自定义横幅
- 不得在横幅外另加"返回"按钮

#### 11.4.2 第二行：**新增 — 联动状态横条（按需）**

**组件**：`components/common/LinkageStatusBar.vue`（新建）
**位置**：GtPageHeader 之下、表格之上
**触发条件**：
- 当前项目存在 stale 底稿（workpaper.is_stale = true）
- 当前项目存在上游变更未同步（TB/报表/附注）
- 从 sse:sync-event / sse:sync-failed 监听

**样式**：黄色/红色细条（高 28px），文字 "当前项目有 3 处数据过期，[一键重算] [查看详情]"
**关闭**：点击"×"暂时隐藏（sessionStorage），下次数据变化重新显示

对应 §2.19 F 的实现。

#### 11.4.3 第三行：工具栏 / 搜索栏 / 筛选栏（可选，按页面类型）

**位置规则**：按类型分三档
- 简单列表页（StaffManagement）：工具栏内嵌到 GtPageHeader.actions，无独立行
- 中等列表页（Projects）：工具栏独立一行（紫带条）
- 复杂页（WorkpaperList）：搜索栏 + 筛选栏 + 工具栏三级叠加

**组件位置**：
- `TableSearchBar.vue` → 表格正上方（表格 mt: 8px）
- `SelectionBar.vue` → 表格顶部浮动（选中时才显示）
- `GtToolbar` → GtPageHeader 的 actions slot 内

#### 11.4.4 主体：表格 / 编辑器 / 图表

**表格归一**：
- 数据展示表格 → `el-table`（保留，低成本）
- **编辑**表格 → 强制 `GtEditableTable`（§2.1）
- 大数据量表格 → `VirtualScrollTable`（§2.29）
- 合并表格 → 专用 ConsolWorksheet*.vue

**编辑器归一**：
- 电子表格编辑 → Univer（不变）
- 富文本编辑 → TipTap（DisclosureEditor 已用）
- 代码/公式编辑 → CodeMirror（若引入）

**右键菜单**：
- 所有表格右键统一挂 `CellContextMenu`（Teleport to body）
- 通过 `<template #extra>` slot 插入模块特有项（§2.18.3 D）

#### 11.4.5 右侧：**统一底稿/报表侧边栏（新）**

**组件**：`WorkpaperSidePanel.vue`（§2.7 A）
**位置**：Detail 内右栏，抽屉或固定栏二选一
**内容**：
- AI 助手
- 附件
- 版本历史
- 批注
- 程序要求
- 依赖关系
- 数据一致性
- 智能提示

**适用视图**：WorkpaperEditor / WorkpaperWorkbench / DisclosureEditor / AuditReportEditor / ReportConfigEditor
**禁止**：不得在这五个编辑器里另写独立的 AI/附件/批注面板

#### 11.4.6 底部：分页 / 统计 / 合计

**位置**：Detail 最底部，sticky bottom
**组件**：
- 分页 → `el-pagination`（右对齐）
- 合计 → `el-table :show-summary`（表格底）
- 选区统计 → `SelectionBar`（浮动到右下角，选中 >= 2 格时显示）

### 11.5 悬浮层（Teleport to body）

#### 11.5.1 右键菜单 CellContextMenu

- **位置**：Teleport to body，绝对定位（鼠标右键处）
- **z-index**：2000（高于 dialog）
- **关闭**：点击 body 任意位置 + ESC
- **样式**：白底 + 紫色品牌色分隔符

#### 11.5.2 **新增 — 全局搜索面板**

- **位置**：Teleport to body，视窗居中（或顶部滑下）
- **尺寸**：640 × 480
- **触发**：Ctrl+K
- **内容**：上方搜索框 + 下方结果列表 + 分类 Tab（项目/底稿/附注/附件/知识库）

#### 11.5.3 **新增 — 快捷键帮助面板**

- **位置**：Teleport to body，视窗居中
- **尺寸**：480 × 600
- **触发**：F1 或 ?
- **内容**：按 scope 分组的快捷键清单 + 搜索框

#### 11.5.4 弹窗 el-dialog

- **位置**：Teleport to body
- **必须加 `append-to-body`**（三栏布局 overflow:hidden 会截断，memory 已记录）
- **遮罩**：半透明白色 rgba(255,255,255,0.6) + backdrop-filter: blur(2px)

#### 11.5.5 NotificationCenter

- **位置**：顶栏 `#nav-notifications` slot
- **下拉面板**：Teleport to body，右上角 360×420
- **内容**：Tab 分类（复核 / 催办 / 系统 / AI）

#### 11.5.6 侧栏抽屉

- **位置**：Teleport to body，从右侧滑入
- **尺寸**：480px 宽 / 视窗高
- **用途**：附件预览（§2.8 C）、版本历史、批注、...

### 11.6 组件库在页面的"唯一位置"清单

防止同一功能出现在多处的关键一览表：

| 组件 | 唯一归属位置 | 禁止出现在 |
|------|-------------|-----------|
| `GtPageHeader` | Detail 区首行 | detail 内部另加自定义 banner |
| `GtInfoBar` | GtPageHeader 默认 slot | 独立一行 |
| `GtToolbar` | GtPageHeader.actions slot | 表格上方、页面底部 |
| `GtStatusTag` | 表格状态列 + 详情区状态标签 | 禁止 `el-tag :type="x==='y'?..."` 三元 |
| `GtAmountCell` | 金额列 | 禁止本地 `fmtAmt()` |
| `GtEditableTable` | 可编辑表格 | 禁止裸 el-table + el-input 手拼编辑 |
| `CellContextMenu` | Teleport to body（共享） | 各视图自写右键菜单 |
| `TableSearchBar` | 表格正上方（紫带） | 无 |
| `SelectionBar` | 右下角浮动（选中时） | 无 |
| `SyncStatusIndicator` | 顶栏右侧 | 页面内 |
| `NotificationCenter` | 顶栏 `#nav-notifications` slot | 页面内 |
| `FormulaManagerDialog` | 顶栏工具箱或编辑器内 F7 唤起 | 每模块自建一份 |
| `CustomQueryDialog` | 顶栏工具箱唤起 | 无 |
| `KnowledgePickerDialog` | useKnowledge composable 唤起 | 无 |
| `GtPrintPreview` | useFullscreen/Ctrl+P 触发 | 无 |
| `LinkageStatusBar`（新） | Detail 第二行 | 无 |
| `WorkpaperSidePanel`（新） | 编辑器右栏 | 无 |
| `GlobalSearchBar`（新） | 顶栏中区 | 无 |
| `ShortcutHelpDialog`（新） | F1 触发 Teleport | 无 |
| `SaveStatusBadge`（新） | 顶栏右区（编辑页） | 无 |
| `OcrStatusBadge`（新） | 附件行 | 禁止各处自写 .gt-wpb-ocr-badge |

### 11.7 角色差异化布局

| 角色 | 顶栏右区角色动作簇 | 左栏导航 | Detail 区默认内容 |
|------|------------------|---------|-----------------|
| auditor | 📋 复核（我提交的）· 🔔 通知 | 6 项（精简） | /my/dashboard |
| manager | 📋 复核 · 🔔 通知 · ✅ 工时审批 | 8 项（+ 看板/委派） | /dashboard/manager |
| qc | 🛡️ 抽查 · 🔔 通知 · 📋 规则 | 4 项（聚焦 QC） | /qc/inspections |
| partner | 📋 复核 · 🔔 通知 · ✍️ 待签字 | 9 项（全） | /dashboard/partner |
| eqcr | 🛡️ 独立复核 · 📊 EQCR 指标 · 🔔 | 5 项（精简） | /eqcr/workbench |
| admin | 全部 | 10 项（全） | / |

实现方式：§2.2 动态导航 + §1.1 登录角色跳转。

### 11.8 响应式断点

| 断点 | 行为 |
|------|-----|
| ≥ 1440px | 完整 4 栏 |
| 1200-1440px | 3 栏，catalog 收起 |
| 992-1200px | 2 栏（nav + detail），middle 收起 |
| 768-992px | 1 栏，nav 抽屉化（汉堡菜单） |
| < 768px | 移动端单栏（建议删除相关 stub，§2.25） |

### 11.9 交互位置速查表

| 交互 | 触发位置 |
|------|---------|
| 返回上级 | GtPageHeader 的"← 返回"按钮 |
| 切项目年度 | GtInfoBar 的年度下拉 |
| 切金额单位 | 顶栏 Aa 面板 |
| 切字号 | 顶栏 Aa 面板 |
| 切主题 | 顶栏 Aa 面板（新增） |
| 搜索当前表 | 表格上方 TableSearchBar（Ctrl+F） |
| 搜索全站 | 顶栏 GlobalSearchBar（Ctrl+K） |
| 打开公式管理 | 顶栏工具箱 · GtToolbar "公式管理"按钮 · F7 |
| 打开知识库 | 顶栏工具箱 · 编辑器右栏 Tab |
| 查看通知 | 顶栏 🔔 |
| 撤销 | Ctrl+Z（全站） |
| 看快捷键 | F1 或 ? |
| 进入编辑 | GtToolbar 的"编辑"按钮 |
| 保存 | Ctrl+S · GtToolbar · 顶栏 SaveStatusBadge |
| 提交复核 | GtToolbar "提交复核"按钮（仅 wp 编辑页） |
| 导出 | GtToolbar "导出"按钮 · Ctrl+E |
| 全屏 | GtToolbar "全屏"按钮 · F11 |
| 打开右键菜单 | 表格单元格右键 |
| 穿透到序时账 | 金额单元格双击 · 右键"穿透" |
| 转错报 | 分录右键"转为错报" · 行末"转错报"按钮 |

### 11.10 版面位置改动的工作量清单

| 改动 | 涉及文件 | 工时 |
|------|---------|------|
| 顶栏工具箱收纳（14→6-7） | ThreeColumnLayout.vue | 1 天 |
| 全局搜索 GlobalSearchBar | 新 1 文件 + 顶栏接入 + 后端端点 | 3 天 |
| 快捷键帮助面板 ShortcutHelpDialog | 新 1 文件 + shortcut:help 监听 | 1 天 |
| SaveStatusBadge 顶栏 | 新 1 文件 + 编辑页接入 | 0.5 天 |
| LinkageStatusBar 横条 | 新 1 文件 + 后端 stale 聚合端点 | 2 天 |
| WorkpaperSidePanel 统一 | 重构 5 编辑器右栏 | 4 天 |
| OcrStatusBadge 抽取 | 新 1 文件 + 3 处替换 | 0.5 天 |
| "我的"左栏底部区 | ThreeColumnLayout 改 + 4 路由 | 1 天 |
| 中栏最近访问 | MiddleProjectList 改 | 0.5 天 |
| **合计** | | **~14 天** |

这一章的改动基本让 UI 的"位置秩序"完成最后一公里。

（完）
