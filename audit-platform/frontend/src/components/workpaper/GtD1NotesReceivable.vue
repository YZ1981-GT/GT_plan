<template>
  <div class="d1-notes-receivable" :class="{ 'is-readonly': review.isReadonly.value }">
    <!-- ═══ 新子组件分发（sheetName v-if 模式，GtWpRenderer 外层 sheet 目录行控制） ═══ -->
    <!-- 程序表 D1A — selfLoad via render-config?force_component_type=a-program-console -->
    <GtAProgramConsole
      v-if="currentSheet === 'D1A'"
      :wp-id="props.wpId"
      sheet-name="D1A"
      :schema="{ columns: [], rows: [] }"
      :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
      :readonly="props.readonly ?? false"
      :hide-categories="true"
    />
    <D1TabAdjudication
      v-else-if="currentSheet === 'D1-1'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :sheet-name="props.sheetName"
    />
    <D1TabDetailCategory
      v-else-if="currentSheet === 'D1-2'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :sheet-name="props.sheetName"
    />
    <D1TabDetailCustomer
      v-else-if="currentSheet === 'D1-3'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :sheet-name="props.sheetName"
    />
    <D1TabBadDebt
      v-else-if="currentSheet === 'D1-4'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :sheet-name="props.sheetName"
    />
    <D1TabPolicyCheck
      v-else-if="currentSheet === 'D1-14'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :display-prefs="localDisplayPrefs"
    />
    <D1TabEclCalc
      v-else-if="currentSheet === 'D1-15'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :display-prefs="localDisplayPrefs"
    />
    <D1TabBusinessMode
      v-else-if="currentSheet === 'D1-6'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :sheet-name="props.sheetName"
    />
    <D1TabMemoReconciliation
      v-else-if="currentSheet === 'D1-7'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :sheet-name="props.sheetName"
    />
    <D1TabEndorsementDetail
      v-else-if="currentSheet === 'D1-8'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :sheet-name="props.sheetName"
    />
    <D1TabInterestCheck
      v-else-if="currentSheet === 'D1-9'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :sheet-name="props.sheetName"
    />
    <D1TabInventoryCount
      v-else-if="currentSheet === 'D1-10'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :display-prefs="localDisplayPrefs"
      :sheet-name="props.sheetName"
    />
    <D1TabRelatedPartyCheck
      v-else-if="currentSheet === 'D1-11'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :display-prefs="localDisplayPrefs"
      :sheet-name="props.sheetName"
    />
    <D1TabPledgeCheck
      v-else-if="currentSheet === 'D1-12'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :display-prefs="localDisplayPrefs"
      :sheet-name="props.sheetName"
    />
    <D1TabSamplingVouching
      v-else-if="currentSheet === 'D1-13'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :display-prefs="localDisplayPrefs"
      :sheet-name="props.sheetName"
    />
    <D1TabWriteoffCheck
      v-else-if="currentSheet === 'D1-16'"
      :all-responses="allResponses"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :is-readonly="props.readonly ?? false"
      :display-prefs="localDisplayPrefs"
      :sheet-name="props.sheetName"
    />

    <!-- ═══ 尚未迁移的 sheet 走 OnlyOffice 降级（D1-5调整分录/D1-16） ═══ -->
    <div v-else class="d1-fallback-sheet">
      <GtOnlyOfficeSheet
        :wp-id="props.wpId"
        :sheet-name="props.sheetName || ''"
        :project-id="props.projectId"
      />
    </div>
  </div>
</template>


<script setup lang="ts">
import { ref, computed, defineAsyncComponent, toRef, onMounted, onBeforeUnmount } from 'vue'
import { useD1FormData } from './composables/useD1FormData'
import { useD1NotesReceivable, type TabStatus } from './composables/useD1NotesReceivable'
import { useD1Review } from './composables/useD1Review'
import D1TabDisclosure from './d1/D1TabDisclosure.vue'
import D1TabAdjudication from './d1/D1TabAdjudication.vue'
import D1TabDetailCategory from './d1/D1TabDetailCategory.vue'
import D1TabDetailCustomer from './d1/D1TabDetailCustomer.vue'
import D1TabBadDebt from './d1/D1TabBadDebt.vue'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'

const GtAProgramConsole = defineAsyncComponent(() => import('./GtAProgramConsole.vue'))

const D1TabPolicyCheck = defineAsyncComponent(() => import('./d1/D1TabPolicyCheck.vue'))
const D1TabEclCalc = defineAsyncComponent(() => import('./d1/D1TabEclCalc.vue'))
const D1TabBusinessMode = defineAsyncComponent(() => import('./d1/D1TabBusinessMode.vue'))
const D1TabMemoReconciliation = defineAsyncComponent(() => import('./d1/D1TabMemoReconciliation.vue'))
const D1TabEndorsementDetail = defineAsyncComponent(() => import('./d1/D1TabEndorsementDetail.vue'))
const D1TabInterestCheck = defineAsyncComponent(() => import('./d1/D1TabInterestCheck.vue'))
const D1TabInventoryCount = defineAsyncComponent(() => import('./d1/D1TabInventoryCount.vue'))
const D1TabRelatedPartyCheck = defineAsyncComponent(() => import('./d1/D1TabRelatedPartyCheck.vue'))
const D1TabPledgeCheck = defineAsyncComponent(() => import('./d1/D1TabPledgeCheck.vue'))
const D1TabSamplingVouching = defineAsyncComponent(() => import('./d1/D1TabSamplingVouching.vue'))
const D1TabWriteoffCheck = defineAsyncComponent(() => import('./d1/D1TabWriteoffCheck.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode: string  // "D1"
  year: number
  readonly?: boolean
  sheetName?: string
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── Composables ─────────────────────────────────────────────────────────────

const { allResponses, loading, saving, loadAll, saveImmediate, saveDebouncedText, flushPendingSave, getField, setFieldImmediate, writebackTrialBalance, loadSubWorkpaperData } =
  useD1FormData(toRef(props, 'wpId'), toRef(props, 'projectId'))

const d1 = useD1NotesReceivable(
  allResponses,
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  toRef(props, 'year'),
  saveImmediate,
  computed(() => props.readonly ?? false),
  loadSubWorkpaperData
)

const review = useD1Review(
  allResponses,
  d1.procedureProgress,
  d1.canInputOverallConclusion,
  saveImmediate,
  computed(() => props.readonly ?? false)
)

// ─── Local UI State ──────────────────────────────────────────────────────────

/** 从 sheetName prop 提取 sheet 编码（如 "应收票据审定表D1-1" → "D1-1"） */
const currentSheet = computed<string>(() => {
  const name = props.sheetName || ''
  // 精确匹配：sheetName 末尾含 D1A 或 D1-N 编码（含两位数如 D1-14）
  const m = name.match(/(D1(?:A|-\d+))\s*$/)
  if (m) return m[1]
  // 模糊匹配：按关键字（两位数编码需优先匹配，避免 D1-1 误匹配 D1-14）
  if (name.includes('政策检查') || name.includes('D1-14')) return 'D1-14'
  if (name.includes('测算表') || name.includes('D1-15')) return 'D1-15'
  if (name.includes('业务模式') || name.includes('D1-6')) return 'D1-6'
  if (name.includes('备查簿') || name.includes('D1-7')) return 'D1-7'
  if (name.includes('背书') || name.includes('贴现明细') || name.includes('D1-8')) return 'D1-8'
  if (name.includes('贴息') || name.includes('D1-9')) return 'D1-9'
  if (name.includes('监盘') || name.includes('D1-10')) return 'D1-10'
  if (name.includes('关联方') || name.includes('D1-11')) return 'D1-11'
  if (name.includes('质押') || name.includes('D1-12')) return 'D1-12'
  if (name.includes('转回') || name.includes('核销') || name.includes('D1-16')) return 'D1-16'
  if (name.includes('检查表') || name.includes('D1-13')) return 'D1-13'
  if (name.includes('审定表') || name.includes('D1-1')) return 'D1-1'
  if (name.includes('按类别') || name.includes('D1-2')) return 'D1-2'
  if (name.includes('按客户') || name.includes('D1-3')) return 'D1-3'
  if (name.includes('坏账准备') || name.includes('D1-4')) return 'D1-4'
  // 无匹配 → 走旧 el-tabs 路径
  return ''
})

/** displayPrefs 本地构建（供 D1-14/D1-15 子组件使用） */
const localDisplayPrefs = computed(() => ({
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  fmtPercent: (v: number) => (v * 100).toFixed(2) + '%',
}))

const showAmendDialog = ref(false)
const amendReason = ref('')

// ─── Sheet Directory ─────────────────────────────────────────────────────────

const sheetDirectory = computed(() => {
  const sheets = [
    { code: 'D1A', name: '审计程序表' },
    { code: 'D1-1', name: '审定表' },
    { code: 'D1-2', name: '原值明细表(按类别)' },
    { code: 'D1-3', name: '原值明细表(按客户)' },
    { code: 'D1-4', name: '坏账准备计算表' },
    { code: 'D1-5', name: '调整分录汇总' },
    { code: 'D1-6', name: '业务模式分析' },
    { code: 'D1-7', name: '备查簿核对' },
    { code: 'D1-8', name: '背书贴现明细' },
    { code: 'D1-9', name: '贴息检查' },
    { code: 'D1-10', name: '票据监盘' },
    { code: 'D1-11', name: '关联方检查' },
    { code: 'D1-12', name: '质押检查' },
    { code: 'D1-13', name: '一般检查表' },
    { code: 'D1-14', name: 'ECL会计政策一致性' },
    { code: 'D1-15', name: 'ECL测试数据' },
    { code: 'D1-16', name: '转回核销检查' },
    { code: 'D1-17', name: '附注披露(上市公司)' },
    { code: 'D1-18', name: '附注披露(国企)' },
    { code: 'D1-19', name: '分析提示' },
    { code: 'D1-20', name: '工作底稿目录' },
  ]
  return sheets.map(s => {
    const statusMap: Record<string, string> = {
      'completed': 'success',
      'in-progress': '',
      'not-started': 'info',
    }
    const labelMap: Record<string, string> = {
      'completed': '已完成',
      'in-progress': '进行中',
      'not-started': '未开始',
    }
    // Simple status lookup from tab completion
    const status: TabStatus = 'not-started'
    return { ...s, statusType: statusMap[status] || 'info', statusLabel: labelMap[status] || '未开始' }
  })
})

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val === null || val === undefined) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number | '' | null | undefined): string {
  if (val === null || val === undefined || val === '') return '-'
  return (Number(val) * 100).toFixed(2) + '%'
}

// ─── Tab Status Helper ───────────────────────────────────────────────────────

function tabDotClass(tabName: string): string {
  const status = d1.tabCompletionStatus.value.get(tabName) || 'not-started'
  if (status === 'completed') return 'tab-dot tab-dot-completed'
  if (status === 'in-progress') return 'tab-dot tab-dot-progress'
  return 'tab-dot tab-dot-empty'
}

// ─── Event Handlers ──────────────────────────────────────────────────────────

function onProcTextChange(stepIdx: number, field: string, val: string): void {
  const n = stepIdx + 1
  const itemId = `D1-proc-${n}-${field}`
  const item = { item_id: itemId, conclusion: null, remark: val }
  allResponses.value.set(itemId, item)
  saveDebouncedText(item)
}

function onOverallConclusionChange(val: string): void {
  const item = { item_id: 'D1-proc-overall', conclusion: null, remark: val }
  allResponses.value.set('D1-proc-overall', item)
  saveDebouncedText(item)
}

function onAdjChange(row: any): void {
  d1.updateAdjustment(row.index, { type: row.type })
}

function onAdjTextChange(row: any): void {
  d1.updateAdjustment(row.index, row)
}

function pushToA13(row: any): void {
  d1.publishAdjustmentCreated(row)
}

function onInventoryChange(field: string, val: string): void {
  const itemId = `D1-inventory-${field}`
  const item = { item_id: itemId, conclusion: null, remark: val }
  allResponses.value.set(itemId, item)
  saveDebouncedText(item)
}

function onCheckChange(prefix: string, n: number, val: string): void {
  const itemId = `D1-${prefix}-${n}-conclusion`
  setFieldImmediate(itemId, { conclusion: val })
}

async function onReview(): Promise<void> {
  await review.doReview()
  emit('completed')
}

async function onAmend(): Promise<void> {
  if (!amendReason.value.trim()) return
  await review.startAmendment(amendReason.value)
  showAmendDialog.value = false
  amendReason.value = ''
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadAll()
})

onBeforeUnmount(() => {
  flushPendingSave()
})
</script>

<style scoped>
.d1-notes-receivable {
  padding: 16px;
  max-width: 1400px;
  margin: 0 auto;
  min-height: 100%;
  display: flex;
  flex-direction: column;
}
.d1-notes-receivable.is-readonly {
  pointer-events: auto;
}
.reviewed-banner {
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 4px;
  padding: 8px 16px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #52c41a;
  font-weight: 500;
}
.linkage-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.ref-chip {
  cursor: pointer;
}
.d1-section {
  padding: 12px 0;
}
.d1-sub-wp-placeholder {
  padding: 48px;
  text-align: center;
  color: #bfbfbf;
  font-size: 14px;
  border: 1px dashed #d9d9d9;
  border-radius: 8px;
  margin: 16px 0;
}

/* Tab dots */
.tab-dot {
  margin-right: 4px;
  font-size: 10px;
}
.tab-dot-completed {
  color: #52c41a;
}
.tab-dot-completed::before {
  content: '✓';
}
.tab-dot-progress {
  color: #1890ff;
}
.tab-dot-progress::before {
  content: '●';
}
.tab-dot-empty {
  color: #bfbfbf;
}
.tab-dot-empty::before {
  content: '○';
}

/* Procedure cards */
.progress-bar {
  margin-bottom: 16px;
}
.risk-badges {
  margin-bottom: 12px;
  display: flex;
  gap: 6px;
}
.procedure-card {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  margin-bottom: 10px;
  overflow: hidden;
}
.procedure-card .card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #fafafa;
}
.step-num {
  background: #1890ff;
  color: #fff;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}
.step-name {
  font-weight: 500;
  font-size: 14px;
}
.card-body-proc {
  padding: 10px 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.card-body-proc .el-textarea {
  width: 100%;
}
.overall-conclusion {
  margin-top: 20px;
  padding: 16px;
  background: #f9f9f9;
  border-radius: 8px;
}
.overall-conclusion h4 {
  margin: 0 0 8px;
}

/* Adjudication table */
.cross-ref {
  background: #e6f7ff;
  padding: 2px 4px;
  border-radius: 2px;
}
.auto-calc {
  color: #8c8c8c;
  font-style: italic;
}

/* ECL */
.ecl-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.migration-matrix {
  margin-bottom: 16px;
}
.ecl-summary {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 13px;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
}
.diff-exceed {
  color: #ff4d4f;
  font-weight: 600;
}

/* Adjustment */
.adj-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}
.adj-totals {
  font-size: 13px;
  color: #666;
}

/* Endorsement */
.endorse-summary {
  margin-top: 12px;
  display: flex;
  gap: 16px;
  font-size: 13px;
  flex-wrap: wrap;
}
.warning-text {
  color: #ff4d4f;
  font-size: 12px;
}

/* Check rows */
.check-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.check-label {
  min-width: 200px;
  font-size: 13px;
}

/* Match panel */
.match-panel {
  margin-bottom: 8px;
}

/* Review */
.review-section {
  border-top: 1px solid #f0f0f0;
  padding-top: 16px;
  margin-top: 16px;
}
.review-section h4 {
  margin: 0 0 8px;
}
.pending-list {
  margin-bottom: 12px;
  font-size: 13px;
  color: #666;
}
.pending-list ul {
  margin: 4px 0;
  padding-left: 20px;
}

/* OnlyOffice fallback sheet — 填满可用高度 */
.d1-fallback-sheet {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 280px);
}
.d1-fallback-sheet :deep(.gt-onlyoffice-sheet) {
  flex: 1;
  min-height: calc(100vh - 340px);
}
</style>
