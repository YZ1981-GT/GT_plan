# R9 全局深度复盘 — 技术设计文档

> 版本：v1.0  
> 日期：2026-05-12  
> 对应需求：requirements.md F1-F25

---

## D1 GtPageHeader 批量接入策略（F1）

### 现状

13/69 视图接入，50+ 视图自写 `<h2 class="gt-page-title">` 或 `<div class="gt-page-banner">`。

### 设计决策

**模式 A（简单标题，18 个视图）**：直接替换 `<h2>` 为 `<GtPageHeader title="xxx">`

```vue
<!-- Before -->
<div class="gt-page-header">
  <h2 class="gt-page-title">复核批注</h2>
  <div class="gt-header-actions">...</div>
</div>

<!-- After -->
<GtPageHeader title="复核批注">
  <template #actions>...</template>
</GtPageHeader>
```

**模式 B（Dashboard banner，7 个视图）**：GtPageHeader 新增 `variant="banner"` prop

```vue
<GtPageHeader title="项目经理工作台" variant="banner" icon="📊">
  <template #subtitle>
    {{ overview.total_projects }} 个项目 · {{ overview.risk_alert_count }} 个风险预警
  </template>
  <template #actions>...</template>
</GtPageHeader>
```

### 改动文件清单

| 文件 | 模式 | 改动量 |
|------|------|--------|
| GtPageHeader.vue | 新增 variant/icon prop | +30 行 |
| AnnotationsPanel.vue | A | ~10 行 |
| AttachmentManagement.vue | A | ~10 行 |
| AuxSummaryPanel.vue | A | ~10 行 |
| CheckInsPage.vue | A | ~10 行 |
| CollaborationIndex.vue | A | ~10 行 |
| ConsistencyDashboard.vue | A | ~10 行 |
| ConsolSnapshots.vue | A | ~10 行 |
| ForumPage.vue | A | ~10 行 |
| PersonalDashboard.vue | A | ~10 行 |
| ProcedureTrimming.vue | A | ~10 行 |
| ProjectDashboard.vue | A | ~10 行 |
| RecycleBin.vue | A | ~10 行 |
| ReportFormatManager.vue | A | ~10 行 |
| ReportTracePanel.vue | A | ~10 行 |
| StaffManagement.vue | A | ~10 行 |
| SubsequentEvents.vue | A | ~10 行 |
| UserManagement.vue | A | ~10 行 |
| WorkHoursPage.vue | A | ~10 行 |
| AuditCheckDashboard.vue | B | ~15 行 |
| ManagementDashboard.vue | B | ~15 行 |
| ManagerDashboard.vue | B | ~15 行 |
| PartnerDashboard.vue | B | ~15 行 |
| QCDashboard.vue | B | ~15 行 |
| MyProcedureTasks.vue | B | ~15 行 |
| ProjectProgressBoard.vue | B | ~15 行 |

---

## D2 金额显示统一方案（F2, F3）

### 设计决策

1. **统一格式化函数**：新建 `utils/formatAmount.ts`

```typescript
export function formatAmount(value: number | string | null | undefined): string {
  if (value == null || value === '') return ''
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(num)) return String(value)
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
```

2. **GtAmountCell 替代手写 span**：当前 GtAmountCell 已有格式化+穿透+hover，直接替换

3. **列宽规约**：所有金额列 `min-width="180"` + `align="right"`，CSS 确保 `white-space: nowrap`

### 改动文件

| 文件 | 改动 |
|------|------|
| utils/formatAmount.ts | 新建 |
| Drilldown.vue | 12 处 `<span class="gt-amt">` → `<GtAmountCell>` |
| LedgerPenetration.vue | 20+ 处替换 + 列宽从 170→200 |
| LedgerImportHistory.vue | 6 处替换 |
| Adjustments.vue | 金额列加 GtAmountCell |
| Misstatements.vue | 金额列加 GtAmountCell |
| WorkHoursPage.vue | 工时数值列加 nowrap |

---

## D3 穿透统一架构（F5, F6）

### 现状

```
usePenetrate composable 已有方法：
- toLedger(accountCode, year?)
- toReportRow(reportType, rowCode)
- toWorkpaperEditor(wpId)
- toAdjustment(accountCode)
```

仅 TrialBalance + ReportView 接入。

### 设计决策

**统一穿透入口模式**：所有金额单元格通过 GtAmountCell 的 `@click` 事件触发穿透

```vue
<GtAmountCell
  :value="row.closing_balance"
  :clickable="true"
  @click="penetrate.toLedger(row.account_code)"
/>
```

**穿透闭环路径**：

```
报表(ReportView) → 试算表(TrialBalance) → 序时账(LedgerPenetration)
    ↓                    ↓                        ↓
  附注(DisclosureEditor)  底稿(WorkpaperEditor)    凭证详情(Drilldown)
    ↓                    ↓
  调整分录(Adjustments) ← 错报(Misstatements)
```

每个节点的"返回"按钮通过 GtPageHeader 的 `@back` 事件实现面包屑式导航。

### 新增接入视图

| 视图 | 穿透方向 | 方法 |
|------|----------|------|
| LedgerPenetration | 余额→序时账 | penetrate.toLedger() |
| Adjustments | 分录金额→序时账 | penetrate.toLedger() |
| Misstatements | 错报金额→科目余额 | penetrate.toLedger() |
| DisclosureEditor | 附注行→底稿 | penetrate.toWorkpaperEditor() |
| WorkpaperWorkbench | 审定数→调整分录 | penetrate.toAdjustment() |
| AuxSummaryPanel | 辅助余额→辅助序时 | penetrate.toLedger() |

---

## D4 v-permission 全量覆盖方案（F4）

### 设计决策

**分类标准**：
- 危险操作（必须有 v-permission）：删除 / 签字 / 归档 / 导出 / 审批 / 强制操作
- 普通操作（可选）：查看 / 搜索 / 刷新 / 导航

**CI 卡点**：扩展 `scripts/find-missing-v-permission.mjs`，新增规则：
- 含 `@click="onDelete"` / `@click="onArchive"` / `@click="onSign"` / `@click="onExport"` 的按钮必须有 v-permission
- 输出违规列表，CI 阈值 ≤ 2

### 需补权限的按钮清单（代码锚定）

| 文件 | 按钮 | 权限码 |
|------|------|--------|
| ArchiveWizard.vue | "开始归档" | archive:execute |
| RecycleBin.vue | "恢复" / "永久删除" | recycle:restore / recycle:purge |
| SamplingEnhanced.vue | "执行抽样" | sampling:execute |
| ReportConfigEditor.vue | "保存" | report_config:edit |
| IssueTicketList.vue | "关闭" | ticket:close |
| Adjustments.vue | "新增 AJE" | adjustment:create |
| ManagerDashboard.vue | "派单" | assignment:batch |
| QCDashboard.vue | "发起抽查" | qc:initiate |

---

## D5 AI 对话统一（F8）

### 现状

| 组件 | 端点 | 特点 |
|------|------|------|
| AiAssistantSidebar | `/api/workpapers/{wpId}/ai/chat` | fetch + 流式 |
| AIChatPanel | `/api/ai/chat` | fetch + 文件分析 + 命令执行 |
| WorkpaperWorkbench 内联 | `/api/workpapers/${wpId}/ai/chat` | api.post 非流式 |

### 设计决策

新建 `composables/useAiChat.ts`：

```typescript
interface UseAiChatOptions {
  endpoint: string | ComputedRef<string>
  context?: ComputedRef<Record<string, string>>
  streaming?: boolean
}

export function useAiChat(options: UseAiChatOptions) {
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)
  
  async function send(message: string) { ... }
  function clear() { ... }
  
  return { messages, loading, send, clear }
}
```

- AiAssistantSidebar：`useAiChat({ endpoint: computed(() => \`/api/workpapers/${wpId}/ai/chat\`), streaming: true })`
- AIChatPanel：`useAiChat({ endpoint: '/api/ai/chat', streaming: true })`
- WorkpaperWorkbench：删除内联代码，使用 WorkpaperSidePanel AI Tab

---

## D6 角色首页差异化（F7）

### 设计决策

`Dashboard.vue` 保持为路由入口，按角色 computed 展示不同卡片组合：

```typescript
const roleCards = computed(() => {
  switch (authStore.user?.role) {
    case 'auditor': return ['myWorkpapers', 'recentProjects', 'schedule', 'quickActions']
    case 'manager': return ['pendingApprovals', 'projectProgress', 'overdueAlerts', 'teamWorkload']
    case 'qc': return ['inspectionCoverage', 'ruleAlerts', 'annualReport']
    case 'partner': return ['pendingSign', 'riskSummary', 'independenceStatus']
    case 'eqcr': return ['eqcrProjects', 'keyFindings', 'memoStatus']
    default: return ['myWorkpapers', 'recentProjects', 'schedule']
  }
})
```

每个卡片是独立组件，按需 lazy 加载。

---

## D7 Ctrl+Z 撤销实现（F9）

### 设计决策

Univer 内置 undo/redo 命令系统，只需连接快捷键：

```typescript
// WorkpaperEditor.vue setup
import { UndoCommand, RedoCommand } from '@univerjs/core'

onMounted(() => {
  // Univer 已内置 Ctrl+Z/Y 处理，无需额外绑定
  // 但需确认 shortcutManager 不拦截
  shortcutManager.unregister('shortcut:undo')
  shortcutManager.unregister('shortcut:redo')
})
```

operationHistory 扩展：监听 Univer 命令执行事件记录审计轨迹（可选，P2）。

---

## D8 vitest 基建（F18）

### 设计决策

```json
// package.json devDependencies 新增
{
  "vitest": "^3.1.0",
  "@vue/test-utils": "^2.4.0",
  "jsdom": "^25.0.0"
}
```

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
  },
  resolve: { alias: { '@': '/src' } },
})
```

优先测试的 composables：
1. `usePenetrate` — 路由跳转逻辑
2. `useEditingLock` — 锁获取/释放/心跳
3. `useProjectEvents` — 事件订阅/过滤
4. `useAiChat`（新建后）— 消息发送/流式解析

---

## D9 粘贴结构化入库方案（F10）

### 现状

`composables/usePasteImport.ts` 已实现核心逻辑：监听 paste 事件 → 解析 TSV/CSV → 回调 onParsed(rows)。仅 Misstatements.vue 接入。

### 设计决策

usePasteImport 保持通用，各视图提供 `columnMap` 配置：

```typescript
const { startListening, stopListening } = usePasteImport({
  columnMap: {
    0: 'account_code',    // 第 0 列 → 科目编码
    1: 'account_name',    // 第 1 列 → 科目名称
    2: 'debit_amount',    // 第 2 列 → 借方
    3: 'credit_amount',   // 第 3 列 → 贷方
    4: 'summary',         // 第 4 列 → 摘要
  },
  onParsed(rows) {
    // 批量创建调整分录
    batchCreateAdjustments(rows)
  },
  validate(row) {
    // 可选：行级校验
    return row.debit_amount || row.credit_amount
  }
})
```

### 接入视图

| 视图 | columnMap | onParsed 动作 |
|------|-----------|---------------|
| Adjustments.vue | 科目/名称/借/贷/摘要 | batchCreateAdjustments API |
| TrialBalance.vue | 科目/AJE借/AJE贷 | 写入调整列 |
| WorkHoursPage.vue | 日期/项目/时长/描述 | batchCreateWorkHours API |

---

## D10 ReviewWorkbench 只读 Editor（F14）

### 现状

ReviewWorkbench 中栏当前只展示复核批注列表，无底稿内容预览。复核人需要在另一个 Tab 打开 WorkpaperEditor 对照看。

### 设计决策

中栏嵌入 Univer 只读实例：

```vue
<UniverSheet
  :data="wpSnapshot"
  :readonly="true"
  :highlights="reviewMarkers"
/>
```

- `wpSnapshot`：从 `/api/workpapers/{wpId}/univer-data` 获取（已有端点）
- `highlights`：ReviewRecord 的 cell_reference 映射为 Univer 高亮区域
- 点击高亮区域 → 右栏滚动到对应批注

### 改动文件

| 文件 | 改动 |
|------|------|
| ReviewWorkbench.vue | 中栏从空白改为 UniverSheet 只读 |
| composables/useWorkpaperReviewMarkers.ts | 已有，直接复用 |

---

## D11 知识库搜索关联底稿上下文（F17）

### 现状

KnowledgeBase.vue 搜索是全局关键词搜索，不感知当前用户正在编辑的底稿/科目。

### 设计决策

搜索时自动注入上下文参数：

```typescript
// KnowledgeBase.vue 或 KnowledgePickerDialog.vue
const contextHint = computed(() => {
  const wp = currentWorkpaper.value  // 从 route params 或 eventBus 获取
  if (!wp) return ''
  return `${wp.wp_code} ${wp.account_name || ''}`
})

// 搜索 API 加 context 参数
api.get(apiPaths.knowledgeLibrary.search, {
  params: { q: keyword, context: contextHint.value }
})
```

后端 `/api/knowledge-library/search` 已有 `q` 参数，新增可选 `context` 参数做相关性加权（BM25 boost）。

---

## D12 错误处理统一（F21）

### 现状

`handleApiError(e, '操作名')` 已封装在 `utils/errorHandler.ts`，提供统一 toast + 日志 + 特殊状态码处理（401 跳登录 / 409 冲突提示 / 5xx 容灾）。当前仅 7 个视图接入，其余 60+ 视图的 catch 块各自 `ElMessage.error(e.message)` 或静默 `console.error`。

### 设计决策

**批量替换规则**：所有 `catch (e) { ElMessage.error(...) }` 改为 `catch (e) { handleApiError(e, '操作名') }`

无需改 handleApiError 本身逻辑，纯机械替换。CI 可加 lint 规则：`catch` 块内禁止直接调 `ElMessage.error`（推荐 eslint-plugin-custom-rules 或 grep 卡点）。

---

## D13 useEditMode 统一接入（F22）

### 现状

useEditMode 提供 `isEditing / isDirty / enterEdit / exitEdit / markDirty / clearDirty` + 路由离开守卫。当前 5 处接入，其余可编辑视图用 `const editing = ref(false)` 自管理，缺少离开守卫和 dirty 检测。

### 设计决策

需接入的视图（grep 确认含"编辑/保存"交互但未用 useEditMode）：
- `Adjustments.vue`：有编辑模式但用自定义 ref
- `WorkHoursPage.vue`：有编辑行但无 dirty 守卫
- `StaffManagement.vue`：有编辑弹窗
- `SubsequentEvents.vue`：有新增/编辑
- `SamplingEnhanced.vue`：有配置编辑
- `CFSWorksheet.vue`：有编辑模式
- `ConsolidationIndex.vue`：有多 Tab 编辑

接入模式统一：`const { isEditing, isDirty, enterEdit, exitEdit, markDirty, clearDirty } = useEditMode()`

---

## D14 死代码清理（F25）

### 待删除文件清单（grep 零引用确认）

| 文件 | 原因 |
|------|------|
| `components/ai/ContractAnalysis.vue` | grep 零引用 |
| `components/ai/ContractAnalysisPanel.vue` | grep 零引用 |
| `components/ai/EvidenceChainPanel.vue` | grep 零引用 |
| `components/ai/EvidenceChainView.vue` | grep 零引用 |
| `components/workpaper/AiContentConfirmDialog.vue` | 与 `components/ai/AiContentConfirmDialog.vue` 重复 |
| `views/ReviewInbox.vue` | 路由全指向 ReviewWorkbench，此文件无引用 |

删除后需确认 vue-tsc 仍 0 错误。

---

## 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| GtPageHeader banner 模式改动影响已接入视图 | 中 | 新增 variant prop 默认 'default'，不影响现有 |
| GtAmountCell 替换后穿透行为变化 | 中 | 逐视图替换 + 手动验证穿透目标正确 |
| AI 对话合并后丢失 AIChatPanel 的文件分析功能 | 低 | useAiChat 保留 fileAnalysis 方法 |
| vitest 与 Vite 配置冲突 | 低 | 独立 vitest.config.ts |
| v-permission 大量新增导致普通用户功能受限 | 中 | 确认 ROLE_PERMISSIONS 覆盖所有新权限码 |
