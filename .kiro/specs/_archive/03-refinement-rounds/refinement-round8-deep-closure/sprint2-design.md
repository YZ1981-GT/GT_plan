# Sprint 2（P1）设计文档

## D1：WorkpaperSidePanel 统一右栏

### 组件结构

```
components/workpaper/
├── WorkpaperSidePanel.vue        # 容器（Tab 切换）
├── side-tabs/
│   ├── SideAiTab.vue             # AI 助手（复用 AiAssistantSidebar 逻辑）
│   ├── SideProcedureTab.vue      # 程序要求
│   ├── SidePriorYearTab.vue      # 上年对比（复用 PriorYearCompareDrawer 逻辑）
│   ├── SideAttachmentTab.vue     # 附件列表 + 上传
│   ├── SideKnowledgeTab.vue      # 知识库搜索 + 插入
│   ├── SideCommentTab.vue        # 批注/复核意见
│   └── SideFineCheckTab.vue      # 自检结果
```

### WorkpaperSidePanel.vue 核心逻辑

```vue
<template>
  <div class="gt-wp-side-panel">
    <div class="gt-wp-side-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.icon }}
        <span v-if="tab.badge" class="gt-badge">{{ tab.badge }}</span>
      </button>
    </div>
    <div class="gt-wp-side-content">
      <SideAiTab v-if="activeTab === 'ai'" :project-id="projectId" :wp-id="wpId" />
      <SideProcedureTab v-if="activeTab === 'procedure'" :project-id="projectId" :wp-id="wpId" />
      <SidePriorYearTab v-if="activeTab === 'prior'" :project-id="projectId" :wp-id="wpId" />
      <SideAttachmentTab v-if="activeTab === 'attachment'" :project-id="projectId" :wp-id="wpId" />
      <SideKnowledgeTab v-if="activeTab === 'knowledge'" :project-id="projectId" :wp-id="wpId" />
      <SideCommentTab v-if="activeTab === 'comment'" :project-id="projectId" :wp-id="wpId" />
      <SideFineCheckTab v-if="activeTab === 'finecheck'" :project-id="projectId" :wp-id="wpId" @badge-update="fineCheckBadge = $event" />
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ projectId: string; wpId: string }>()
const activeTab = ref('ai')
const fineCheckBadge = ref(0)

const tabs = computed(() => [
  { key: 'ai', icon: '🤖', label: 'AI', badge: 0 },
  { key: 'procedure', icon: '📋', label: '程序', badge: 0 },
  { key: 'prior', icon: '📜', label: '上年', badge: 0 },
  { key: 'attachment', icon: '📎', label: '附件', badge: 0 },
  { key: 'knowledge', icon: '📚', label: '知识库', badge: 0 },
  { key: 'comment', icon: '💬', label: '批注', badge: 0 },
  { key: 'finecheck', icon: '🔍', label: '自检', badge: fineCheckBadge.value },
])
</script>
```

### SideFineCheckTab.vue 核心

```vue
<template>
  <div class="gt-side-finecheck">
    <div v-if="loading" v-loading="true" style="min-height: 100px" />
    <div v-else-if="!checks.length" class="gt-empty-hint">暂无检查项</div>
    <div v-else>
      <div v-for="chk in checks" :key="chk.rule_code" class="gt-finecheck-item" :class="{ 'gt-finecheck-fail': !chk.passed }">
        <span class="gt-finecheck-code">{{ chk.rule_code }}</span>
        <span class="gt-finecheck-desc">{{ chk.description }}</span>
        <span v-if="chk.passed" class="gt-finecheck-ok">✓</span>
        <span v-else class="gt-finecheck-fail-msg">
          ✗ {{ chk.message }}
          <el-button size="small" text type="primary" @click="onLocate(chk)">定位</el-button>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// onLocate 调用 Univer API 定位到指定单元格
function onLocate(chk: FineCheckResult) {
  if (chk.cell_ref) {
    eventBus.emit('workpaper:locate-cell', { sheetName: chk.sheet_name, cellRef: chk.cell_ref })
  }
}
</script>
```

WorkpaperEditor 订阅 `workpaper:locate-cell` 事件，调 Univer `setActiveRange`。

---

## D2：useStaleStatus composable

### composables/useStaleStatus.ts

```ts
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'

export function useStaleStatus(projectId: Ref<string>) {
  const isStale = ref(false)
  const staleCount = ref(0)
  const lastChangedAt = ref('')

  async function check() {
    if (!projectId.value) return
    try {
      const data = await api.get(`/api/projects/${projectId.value}/stale-summary`)
      staleCount.value = (data as any)?.stale_count || 0
      isStale.value = staleCount.value > 0
      lastChangedAt.value = (data as any)?.last_changed_at || ''
    } catch { /* ignore */ }
  }

  async function recalc() {
    await api.post(`/api/projects/${projectId.value}/trial-balance/recalc`)
    staleCount.value = 0
    isStale.value = false
  }

  onMounted(() => {
    check()
    eventBus.on('workpaper:saved', check)
    eventBus.on('year:changed', check)
  })

  onUnmounted(() => {
    eventBus.off('workpaper:saved', check)
    eventBus.off('year:changed', check)
  })

  return { isStale, staleCount, lastChangedAt, check, recalc }
}
```

### 视图接入

ReportView / DisclosureEditor / AuditReportEditor 顶部加：

```vue
<div v-if="stale.isStale" class="gt-stale-banner">
  ⚠️ 上游数据已变更（{{ stale.lastChangedAt }}），建议
  <el-button text type="primary" size="small" @click="stale.recalc()">点击重算</el-button>
</div>
```

---

## D3：ShadowCompareRow 组件

### components/eqcr/ShadowCompareRow.vue

```vue
<template>
  <div class="gt-shadow-compare-row">
    <div class="gt-scr-label">{{ label }}</div>
    <div class="gt-scr-values">
      <div class="gt-scr-team">
        <span class="gt-scr-sublabel">项目组值</span>
        <GtAmountCell :value="teamValue" :unit="unit" />
      </div>
      <div class="gt-scr-shadow">
        <span class="gt-scr-sublabel">影子值</span>
        <GtAmountCell :value="shadowValue" :unit="unit" />
      </div>
      <div class="gt-scr-diff" :class="{ 'gt-scr-diff--exceed': exceedsThreshold }">
        <span class="gt-scr-sublabel">差异</span>
        <span>{{ diffDisplay }}</span>
      </div>
    </div>
    <div class="gt-scr-verdict">
      <el-radio-group v-model="localVerdict" size="small" @change="onVerdictChange">
        <el-radio-button value="pass">通过</el-radio-button>
        <el-radio-button value="flag">标记异常</el-radio-button>
        <el-radio-button value="discuss">需要讨论</el-radio-button>
      </el-radio-group>
      <el-input v-model="note" placeholder="备注（选填）" size="small" maxlength="200" @blur="onNoteSave" />
    </div>
  </div>
</template>

<script setup lang="ts">
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import { computed, ref, watch } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  label: string
  teamValue: number | null
  shadowValue: number | null
  unit?: string
  thresholdPct?: number
  verdict?: string
  verdictNote?: string
}>()

const emit = defineEmits<{
  (e: 'verdict-change', payload: { verdict: string; note: string }): void
}>()

const displayPrefs = useDisplayPrefsStore()
const localVerdict = ref(props.verdict || '')
const note = ref(props.verdictNote || '')

const diff = computed(() => {
  if (props.teamValue == null || props.shadowValue == null) return null
  return props.shadowValue - props.teamValue
})

const diffPct = computed(() => {
  if (diff.value == null || !props.teamValue) return null
  return (diff.value / Math.abs(props.teamValue)) * 100
})

const exceedsThreshold = computed(() => {
  if (diffPct.value == null || !props.thresholdPct) return false
  return Math.abs(diffPct.value) > props.thresholdPct
})

const diffDisplay = computed(() => {
  if (diff.value == null) return '—'
  const sign = diff.value >= 0 ? '+' : ''
  const pct = diffPct.value != null ? ` (${sign}${diffPct.value.toFixed(1)}%)` : ''
  return `${sign}${displayPrefs.fmt(diff.value)}${pct}`
})

function onVerdictChange(val: string) {
  emit('verdict-change', { verdict: val, note: note.value })
}
function onNoteSave() {
  if (localVerdict.value) emit('verdict-change', { verdict: localVerdict.value, note: note.value })
}
</script>
```

---

## D4：PartnerSignDecision 视图

### 布局

```
┌── GtPageHeader "签字决策 — {clientName} {year}" ──────────────┐
└────────────────────────────────────────────────────────────────┘
┌── 左栏 (35%) ──────┬── 中栏 (40%) ──────┬── 右栏 (25%) ──────┐
│ GateReadinessPanel │ PDF 预览 (iframe) │ 风险摘要列表      │
│ （互动式，可展开） │                    │ 10 条 top 风险    │
│                    │                    │ 红/黄/绿 badge    │
└────────────────────┴────────────────────┴────────────────────┘
┌── 底栏操作 ──────────────────────────────────────────────────┐
│ [← 回退到复核]  [✍️ 签字]  [📋 查看历史]  [🖨️ 打印]         │
└────────────────────────────────────────────────────────────────┘
```

### 签字流程

1. 点击"签字"→ 调 `confirmSignature(clientName, '年度审计报告')`
2. 弹窗要求输入客户名全称确认
3. 输入匹配后调 `POST /api/signatures/sign`
4. 成功 → feedback.success + 跳 `/partner/sign-history`

### PDF 预览（中栏）

**端点确认**：需 grep 确认 `/api/reports/{pid}/preview-pdf` 或类似端点是否已存在。

可能的已有端点：
- `GET /api/projects/{pid}/audit-report/export?format=pdf`（已有，但是下载不是预览）
- `GET /api/projects/{pid}/workpapers/{wp_id}/export-pdf`（底稿级）

**方案**：
- 若已有 PDF 导出端点，中栏用 `<iframe :src="pdfUrl" />` 内嵌预览
- 若无预览端点，新建 `GET /api/projects/{pid}/audit-report/preview-pdf`（返回 PDF blob，前端用 URL.createObjectURL 渲染）
- 降级方案：中栏改为"报告内容预览"（HTML 渲染，非 PDF），复用 AuditReportEditor 只读模式

### 风险摘要右栏

调 `GET /api/projects/{pid}/risk-summary`，按严重度排序展示。

---

## D5：风险摘要后端

### routers/risk_summary.py

```python
@router.get("/api/projects/{project_id}/risk-summary")
async def get_risk_summary(project_id: str, db: AsyncSession = Depends(get_db)):
    svc = RiskSummaryService(db)
    return await svc.aggregate(project_id)
```

### services/risk_summary_service.py

聚合 6 个数据源：
1. `IssueTicket` where severity='high' and status != 'closed'
2. `ReviewRecord` where resolved_at IS NULL
3. `UnadjustedMisstatement` where amount > materiality_threshold
4. `Adjustment` where review_status='rejected' and not converted
5. AI flags（从 `wp_ai_service` 最近分析结果）
6. `WorkHour` 预算超支判断

---

## D6：ManagerDashboard 四 Tab

### Tab 结构

```vue
<el-tabs v-model="activeTab">
  <el-tab-pane label="📊 项目矩阵" name="matrix">
    <ManagerProjectMatrix :manager-id="userId" />
  </el-tab-pane>
  <el-tab-pane label="⏱️ 团队成本" name="cost">
    <ManagerTeamCost :manager-id="userId" />
  </el-tab-pane>
  <el-tab-pane label="💬 客户承诺" name="commitments">
    <!-- 现有承诺表格 -->
  </el-tab-pane>
  <el-tab-pane label="🚨 异常告警" name="alerts">
    <ManagerAlerts :manager-id="userId" />
  </el-tab-pane>
</el-tabs>
```

### 后端端点

- `GET /api/manager/projects/matrix` → 聚合 Project + WorkingPaper + WorkHour + IssueTicket
- `GET /api/manager/alerts` → 聚合预算超支/逾期/卡住/阻塞/未整改

---

## D7：QcHub.vue

### 布局

```
┌── 今日关注（4 卡片）──────────────────────────────────────────┐
│ [本月应抽查: N]  [逾期整改: M]  [高风险客户: K]  [规则预警: L] │
└────────────────────────────────────────────────────────────────┘
┌── 主工作区（4 Tab）──────────────────────────────────────────┐
│ [待抽查 | 抽查中 | 整改中 | 已完结]                           │
│ 每 Tab 是 el-table 列表                                       │
└────────────────────────────────────────────────────────────────┘
┌── 侧边快捷入口 ──────────────────────────────────────────────┐
│ → 规则管理  → 案例库  → 年报  → 客户趋势                      │
└────────────────────────────────────────────────────────────────┘
```

### 路由变更

```ts
{ path: '/qc', name: 'QcHub', component: () => import('@/views/qc/QcHub.vue'), meta: { roles: ['qc', 'admin', 'partner'] } },
// QCDashboard 降级
{ path: '/projects/:projectId/qc-dashboard', redirect: to => `/projects/${to.params.projectId}/dashboard?tab=qc` },
```

### ProjectDashboard.vue 改造

ProjectDashboard.vue 当前是 Tab 布局（进度/底稿/工时/...）。新增一个 Tab：

```vue
<el-tab-pane label="质控" name="qc" v-if="canViewQc">
  <Suspense>
    <QCDashboardEmbed :project-id="projectId" />
  </Suspense>
</el-tab-pane>
```

新建 `components/qc/QCDashboardEmbed.vue`：
- 从 QCDashboard.vue 抽取核心内容（项目评级 + 复核人画像 + 规则执行结果）
- 去掉 GtPageHeader（嵌入模式不需要）
- Props: `projectId`

---

## D8：v-permission 铺设

### 权限码清单

| 权限码 | 角色 |
|--------|------|
| `project:delete` | admin |
| `workpaper:edit` | auditor, manager, partner, admin |
| `workpaper:submit_review` | auditor, manager, admin |
| `workpaper:review_approve` | manager, partner, admin |
| `workpaper:review_reject` | manager, partner, admin |
| `adjustment:convert_to_misstatement` | auditor, manager, partner, admin |
| `sign:execute` | partner, admin |
| `archive:execute` | partner, admin |
| `archive:unlock` | admin |
| `qc:publish_report` | qc, admin |
| `sign:revoke` | admin |
| `report:export_final` | partner, admin |
| `independence:edit` | all |
| `eqcr:approve` | eqcr, admin |
| `assignment:batch` | manager, partner, admin |
| `workpaper:escalate` | manager, partner, admin |

---

## D9：附注行 → 底稿穿透

### 后端

```python
# routers/disclosure_notes.py 新增
@router.get("/api/notes/{project_id}/{year}/{note_section}/row/{row_code}/related-workpapers")
async def get_note_row_related_workpapers(project_id, year, note_section, row_code, db):
    # 通过 report_line_mapping → account_code → wp_mapping 查找关联底稿
    ...
```

### 前端

DisclosureEditor 的 CellContextMenu 新增菜单项：

```vue
<div class="gt-ucell-ctx-item" @click="onNoteRowRelatedWp">
  <span class="gt-ucell-ctx-icon">📝</span> 查看相关底稿
</div>
```

---

## D10：重要性变更 → 错报阈值即时重算

### Misstatements.vue 订阅

```ts
onMounted(() => {
  eventBus.on('materiality:changed', onMaterialityChanged)
})

async function onMaterialityChanged(payload: { projectId: string; year?: number }) {
  if (payload.projectId === projectId.value) {
    await loadMaterialityThreshold()
    await loadMisstatements()
  }
}
```

### GateReadinessPanel 订阅

```ts
eventBus.on('materiality:changed', () => {
  // 重新调用 gate_engine.evaluate
  revalidate()
})
```

---

## D11：未保存提醒 + beforeunload（R8-S2-14）

### useWorkpaperAutoSave 暴露 isDirty

```ts
// composables/useWorkpaperAutoSave.ts 新增导出
const isDirty = ref(false)

// 在 onSave 成功后 isDirty = false
// 在数据变更时 isDirty = true（watch 或手动 markDirty()）

return { ..., isDirty, markDirty }
```

### WorkpaperEditor 接入

```ts
import { onBeforeRouteLeave } from 'vue-router'
import { confirmLeave } from '@/utils/confirm'

const { isDirty } = useWorkpaperAutoSave(...)

onBeforeRouteLeave(async () => {
  if (isDirty.value) {
    const leave = await confirmLeave('底稿')
    return leave  // false 阻止导航
  }
})

// beforeunload
onMounted(() => {
  window.addEventListener('beforeunload', onBeforeUnload)
})
onUnmounted(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
})
function onBeforeUnload(e: BeforeUnloadEvent) {
  if (isDirty.value) { e.preventDefault(); e.returnValue = '' }
}
```

### DisclosureEditor / AuditReportEditor 同理

两者已有 `useEditMode`，在 `isEditing && isDirty` 时触发 confirmLeave。

---

## 全局约束（Sprint 2 所有新代码必须遵守）

- 所有新增 `ElMessage.xxx` / `ElNotification` 调用必须走 `utils/feedback.ts`
- 所有新增 `ElMessageBox.confirm` 必须走 `utils/confirm.ts` 语义化函数
- 所有新增状态字符串比较必须用 `constants/statusEnum.ts` 常量
