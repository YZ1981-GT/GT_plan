<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * D4TabCustomerStructure — D4-9 重要客户结构分析表
 *
 * 对齐源模板真实结构（openpyxl实读 "重要客户结构分析D4-9"）：
 * 一、审计目标（固定文本）
 * 二、审计过程（AI辅助）
 * 本期Top10客户表：序号/客户名称/销售金额/销售金额占比(=金额/本期销售总额)/销售数量/销售数量占比(=数量/本期总数量)/上期排名
 * 上期Top10客户表：同结构
 * 三、审计说明（含模板提示文字）
 * 四、审计结论
 *
 * 公式：D列=IF(C=0,0,C/$C$24) 金额占比; F列=IF(E=0,0,E/$E$24) 数量占比
 * 合计行：C=SUM; D=IF(C=0,0,C/总额); E=SUM; F同
 * 本期销售总额从D4-7!D26取（跨sheet引用）
 */
import { ref, computed, inject, toRef, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
// D4-9 双向回写：子组件自管 sync bridge + WorkpaperSyncEditorHost（dedicated sync sheet）。
// sheet_key=d49-managed，同 entry gt-d4-operating-revenue（后端 phase5_d4_customer_structure
// 作为 sibling sheet 并入 phase5_d4_revenue_detail，adapter d4.revenue_detail）——与 D4-1 同架构。
// 移除 legacy GtOnlyOfficeSheet 单向入口（Requirement 7.1 / 7.5）。
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from '../../sync/useWorkpaperSyncBridge'
import { readStoreProjection } from '../../sync/workpaperSyncApi'
import { capabilityForEntry } from '../../sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from '../../sync/WorkpaperSyncEditorHost.vue'
import GtEntrySyncCapabilityNotice from '../../sync/GtEntrySyncCapabilityNotice.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const reloadWorkpaperData = inject<(() => Promise<void> | void) | null>('reloadWorkpaperData', null)

// ─── 双模式 sync bridge（D4-9 重要客户结构分析）──────────────────────────────
// D4-9 作为 gt-d4-operating-revenue 的 sibling sheet（sheetKey=d49-managed，后端
// phase5_d4_customer_structure 并入 phase5_d4_revenue_detail，adapter d4.revenue_detail），
// 与 D4-1 同架构 —— 不建独立 entry。flushHtml 先 flush 待存改动再 readStoreProjection
// （防投影旧值）；capability 现算；fail-visible，能力未裁决 / OO 不健康时 fail-closed（Req 7.4）。
const D4_9_ENTRY = 'xlsx/gt-d4-operating-revenue'
const D4_9_SHEET_KEY = 'd49-managed'
const ooHealthy = ref(false)
async function checkOoHealth() {
  try {
    const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    ooHealthy.value = res.data?.data?.healthy ?? res.data?.healthy ?? false
  } catch { ooHealthy.value = false }
}
checkOoHealth()
const syncSwitching = ref(false)
const syncBridge = useWorkpaperSyncBridge({
  entryId: ref(D4_9_ENTRY),
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: ref(D4_9_SHEET_KEY),
  capability: capabilityForEntry(D4_9_ENTRY),
  flushHtml: async () => {
    flushSave()
    const snap = await readStoreProjection({ projectId: props.projectId, wpId: props.wpId, entryId: D4_9_ENTRY })
    return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: D4_9_SHEET_KEY }
  },
  reloadHtml: async () => { if (reloadWorkpaperData) await reloadWorkpaperData() },
})
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncBusy = computed(
  () => syncSwitching.value
    || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)
// editorMode 由 sync bridge 的 mode 表达（不再是本地 legacy ref）。
const editorMode = computed<string>({
  get: () => (syncBridge.mode.value === 'oo' ? '在线编辑' : '结构化视图'),
  set: (v: string) => { void switchMode(v === '在线编辑' ? 'onlyoffice' : 'structured') },
})
const modeOptions = computed(() => [
  { label: '结构化视图', value: '结构化视图' },
  { label: '在线编辑', value: '在线编辑', disabled: props.isReadonly || !ooHealthy.value || syncBusy.value },
])
async function switchMode(target: 'structured' | 'onlyoffice'): Promise<void> {
  const cur = syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'structured'
  if (target === cur) return
  if (target === 'onlyoffice') {
    if (props.isReadonly || !ooHealthy.value) return
    syncSwitching.value = true
    try { await syncBridge.switchToOnlyOffice() } finally { syncSwitching.value = false }
    return
  }
  syncSwitching.value = true
  try { await syncBridge.switchToHtml() } finally { syncSwitching.value = false }
}
// fail-visible：同步失败以中文 tag 显式呈现，不静默吞。
const syncStateTag = computed(() => {
  const st = String(syncBridge.state.value)
  if (syncBusy.value) return { text: '同步中…', type: 'info' as const }
  if (syncBridge.dirty?.value) {
    return syncBridge.mode.value === 'oo'
      ? { text: 'excel 侧有未同步改动', type: 'warning' as const }
      : { text: 'html 侧有未同步改动', type: 'warning' as const }
  }
  if (st.includes('error') || String(syncBridge.lastError?.value || '')) {
    return { text: '同步失败，请重试', type: 'danger' as const }
  }
  return { text: '已同步', type: 'success' as const }
})

const auditObjective = '利润表中记录的营业收入已发生，且与被审计单位有关。'

// ─── 审计过程 ─────────────────────────────────────────────────────────
const auditProcess = ref('')
function loadAuditProcess() { auditProcess.value = props.allResponses.get('D4-9-audit-process')?.remark || '' }
watch(() => props.allResponses.get('D4-9-audit-process')?.remark, () => loadAuditProcess(), { immediate: true })
function updateAuditProcess(val: string) { if (props.isReadonly) return; auditProcess.value = val; persist('D4-9-audit-process', val) }

// ─── 客户数据 ─────────────────────────────────────────────────────────
// 行身份 = rowId（稳定 UUID，禁下标）。后端投影 iter_store_rows 复用
// store_row_identity fail-closed：缺/重复 rowId 抛 StorePayloadError（design §2.3）。
interface CustomerRow {
  rowId: string
  name: string
  amount: number
  quantity: number
  priorRank: string
}
interface PeriodData {
  rows: CustomerRow[]
  totalAmount: number
  totalQuantity: number
}

const currentPeriod = ref<PeriodData>({ rows: [], totalAmount: 0, totalQuantity: 0 })
const priorPeriod = ref<PeriodData>({ rows: [], totalAmount: 0, totalQuantity: 0 })

/** 生成稳定行身份。优先 crypto.randomUUID，回退到时间+随机串（老浏览器/测试环境）。 */
function createRowId(): string {
  const c = (globalThis as any).crypto as { randomUUID?: () => string } | undefined
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  return `d49-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function makeRow(): CustomerRow {
  return { rowId: createRowId(), name: '', amount: 0, quantity: 0, priorRank: '' }
}

function defaultRows(): CustomerRow[] {
  return Array.from({ length: 10 }, () => makeRow())
}

/**
 * 对历史行（无 rowId）补齐稳定身份，不改动既有手工值。
 * @returns 是否发生了补齐（用于判定是否需要一次性持久化）
 */
function backfillRowIds(rows: CustomerRow[]): boolean {
  let changed = false
  for (const r of rows) {
    if (!r.rowId || typeof r.rowId !== 'string' || !r.rowId.trim()) {
      r.rowId = createRowId()
      changed = true
    }
  }
  return changed
}

function loadData() {
  const resp = props.allResponses.get('D4-9-data')
  if (resp?.remark) {
    try {
      const d = JSON.parse(resp.remark)
      const currentRows: CustomerRow[] = Array.isArray(d.current?.rows) ? d.current.rows : defaultRows()
      const priorRows: CustomerRow[] = Array.isArray(d.prior?.rows) ? d.prior.rows : defaultRows()
      currentPeriod.value = { rows: currentRows, totalAmount: d.current?.totalAmount || 0, totalQuantity: d.current?.totalQuantity || 0 }
      priorPeriod.value = { rows: priorRows, totalAmount: d.prior?.totalAmount || 0, totalQuantity: d.prior?.totalQuantity || 0 }
      // 历史 store 无 rowId → 一次性补齐并持久化（Requirement 3.2），不丢既有手工值。
      // current/prior 各区独立生成，rowId 在两区内各自唯一（Requirement 3.4）。
      const changed = backfillRowIds(currentPeriod.value.rows)
      const changedPrior = backfillRowIds(priorPeriod.value.rows)
      // 只读态仅在内存补齐（供投影用），不回写；可写态一次性持久化。
      if ((changed || changedPrior) && !props.isReadonly) persistData()
      return
    } catch {}
  }
  currentPeriod.value = { rows: defaultRows(), totalAmount: 0, totalQuantity: 0 }
  priorPeriod.value = { rows: defaultRows(), totalAmount: 0, totalQuantity: 0 }
}
watch(() => props.allResponses.get('D4-9-data')?.remark, () => loadData(), { immediate: true })

// 计算列
interface ComputedCustomerRow extends CustomerRow {
  amountRatio: number
  quantityRatio: number
}
function computeRows(period: PeriodData): ComputedCustomerRow[] {
  return period.rows.map(r => ({
    ...r,
    amountRatio: period.totalAmount === 0 ? 0 : r.amount / period.totalAmount,
    quantityRatio: period.totalQuantity === 0 ? 0 : r.quantity / period.totalQuantity,
  }))
}
const computedCurrent = computed(() => computeRows(currentPeriod.value))
const computedPrior = computed(() => computeRows(priorPeriod.value))

// 合计
const currentSum = computed(() => ({
  amount: currentPeriod.value.rows.reduce((s, r) => s + r.amount, 0),
  quantity: currentPeriod.value.rows.reduce((s, r) => s + r.quantity, 0),
}))
const priorSum = computed(() => ({
  amount: priorPeriod.value.rows.reduce((s, r) => s + r.amount, 0),
  quantity: priorPeriod.value.rows.reduce((s, r) => s + r.quantity, 0),
}))
const currentSumRatio = computed(() => ({
  amount: currentPeriod.value.totalAmount === 0 ? 0 : currentSum.value.amount / currentPeriod.value.totalAmount,
  quantity: currentPeriod.value.totalQuantity === 0 ? 0 : currentSum.value.quantity / currentPeriod.value.totalQuantity,
}))
const priorSumRatio = computed(() => ({
  amount: priorPeriod.value.totalAmount === 0 ? 0 : priorSum.value.amount / priorPeriod.value.totalAmount,
  quantity: priorPeriod.value.totalQuantity === 0 ? 0 : priorSum.value.quantity / priorPeriod.value.totalQuantity,
}))

// 集中度警告
const concentrationWarning = computed(() => {
  if (currentPeriod.value.totalAmount === 0) return null
  const top5Sum = currentPeriod.value.rows.slice(0, 5).reduce((s, r) => s + r.amount, 0)
  const ratio = top5Sum / currentPeriod.value.totalAmount
  if (ratio > 0.5) return `Top5客户集中度${(ratio * 100).toFixed(1)}%，超过50%警戒线`
  return null
})

function addRow(period: 'current' | 'prior') {
  if (props.isReadonly) return
  const target = period === 'current' ? currentPeriod.value : priorPeriod.value
  target.rows.push(makeRow())
  persistData()
}
function removeRow(period: 'current' | 'prior', idx: number) {
  if (props.isReadonly) return
  const target = period === 'current' ? currentPeriod.value : priorPeriod.value
  target.rows.splice(idx, 1)
  persistData()
}
function updateData() { if (props.isReadonly) return; persistData() }
function persistData() {
  const data = { current: currentPeriod.value, prior: priorPeriod.value }
  props.allResponses.set('D4-9-data', { item_id: 'D4-9-data', conclusion: null, remark: JSON.stringify(data) })
  debounceSave()
}

// ─── 审计说明 / 结论 ──────────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')
function loadNoteConclusion() {
  auditNote.value = props.allResponses.get('D4-9-note')?.remark || ''
  auditConclusion.value = props.allResponses.get('D4-9-conclusion')?.remark || ''
}
watch(() => props.allResponses.get('D4-9-note')?.remark, () => loadNoteConclusion(), { immediate: true })
function updateNote(val: string) { if (props.isReadonly) return; auditNote.value = val; persist('D4-9-note', val) }
function updateConclusion(val: string) { if (props.isReadonly) return; auditConclusion.value = val; persist('D4-9-conclusion', val) }

// ─── 格式化 ──────────────────────────────────────────────────────────
function fmtAmt(val: number): string { return val === 0 ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function fmtPercent(val: number | null): string { if (val == null) return '-'; return (val * 100).toFixed(2) + '%' }

// ─── AI辅助 ──────────────────────────────────────────────────────────
const aiAvailable = ref(false)
const aiLoadingKey = ref<string | null>(null)
async function checkAiHealth() { try { const res = await http.get('/api/ai/health', { _silent: true } as any); const s = res.data?.data?.status ?? res.data?.status; aiAvailable.value = s === 'healthy' || s === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
async function callD4Ai(section: string, existing: string): Promise<string> { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section, existingContent: existing, relatedContext: {} }, { _silent: true } as any); return res.data?.data?.content ?? res.data?.content ?? '' }
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

async function generateNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'note'
  try {
    const top5 = computedCurrent.value.slice(0, 5).map(r => `${r.name||'未命名'}:${fmtAmt(r.amount)}(${fmtPercent(r.amountRatio)})`).join('、')
    const ctx = `本期Top5客户：${top5}\nTop5集中度：${fmtPercent(currentSumRatio.value.amount)}\n本期销售总额：${fmtAmt(currentPeriod.value.totalAmount)}`
    const text = await callD4Ai('analysis-note', ctx)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateNote(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}
async function generateConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'conclusion'
  try {
    const ctx = `审计说明：${auditNote.value || '（未填写）'}\n集中度警告：${concentrationWarning.value || '无'}`
    const text = await callD4Ai('adj-conclusion', ctx)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateConclusion(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

// ─── 导入导出 ────────────────────────────────────────────────────────
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: toRef(props, 'wpId') as Ref<string>, projectId: toRef(props, 'projectId') as Ref<string> })
function handleExportTemplate() { exportTemplate('D4-9' as any) }
function handleExportData() { exportData('D4-9' as any) }
function handleImportUpload(file: File): boolean { importData('D4-9' as any, file).then(r => { if (r && r.rowCount > 0) loadData() }); return false }

// ─── 持久化 ──────────────────────────────────────────────────────────
let debounceTimer: ReturnType<typeof setTimeout> | null = null
function persist(itemId: string, value: string) { props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: value }); debounceSave() }
function debounceSave() { if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000) }
function flushSave() { const keys = ['D4-9-audit-process', 'D4-9-data', 'D4-9-note', 'D4-9-conclusion']; const items = keys.map(k => props.allResponses.get(k)).filter(Boolean); window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } })) }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })
</script>


<template>
  <div class="d4-customer-structure">

    <!-- 双模式切换（结构化视图 ↔ 在线编辑，走统一双向 sync bridge） -->
    <div class="mode-bar">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      <div class="mode-bar-status">
        <el-tag :type="syncStateTag.type" size="small">{{ syncStateTag.text }}</el-tag>
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d4-operating-revenue" />
      </div>
    </div>

    <!-- 结构化视图 -->
    <template v-if="editorMode === '结构化视图'">    <!-- 一、审计目标 -->
    <section class="sec">
      <h4 class="sec-title">一、审计目标</h4>
      <div class="objective-list"><p class="objective-item">{{ auditObjective }}</p></div>
    </section>

    <!-- 二、审计过程 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">二、审计过程</h4>
        <el-tooltip :content="aiTip" placement="top">
          <el-button size="small" type="primary" plain :loading="aiLoadingKey === 'process'" :disabled="isReadonly || !aiAvailable" @click="generateNote">🤖 AI辅助</el-button>
        </el-tooltip>
      </div>
      <el-input type="textarea" :rows="2" :model-value="auditProcess" :disabled="isReadonly"
        placeholder="1.获取本期及上期前十大客户销售明细，分析客户集中度变化及原因……"
        @input="(v: string) => updateAuditProcess(v)" />
    </section>

    <!-- 集中度警告 -->
    <el-alert v-if="concentrationWarning" :title="concentrationWarning" type="warning" show-icon :closable="false" style="margin-bottom: 12px" />

    <!-- 本期客户 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">本期：</h4>
        <div class="sec-actions">
          <el-dropdown size="small" trigger="click" :disabled="isReadonly">
            <el-button size="small">导入导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
                <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
                <el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx,.xls" :before-upload="handleImportUpload" :disabled="importing"><span>{{ importing ? '导入中...' : '导入数据' }}</span></el-upload></el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-tooltip content="批量数据建议：先导出模板在Excel中填写后导入" placement="top" :show-after="300">
            <el-button size="small" :disabled="isReadonly" @click="addRow('current')">+ 增行</el-button>
          </el-tooltip>
          <GtIndexChip value="wp:D4-7" :context-project-id="projectId" />
          <GtIndexChip value="wp:D4-2" :context-project-id="projectId" />
        </div>
      </div>

      <!-- 本期销售总额 -->
      <div class="total-row">
        <span>本期销售总额：</span>
        <el-tooltip content="数据来源: D4-7按产品毛利分析合计行(D26)，或手动填入" placement="right" :show-after="200">
          <el-input-number v-model="currentPeriod.totalAmount" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="total-input" @change="updateData" />
        </el-tooltip>
        <span style="margin-left:16px">本期总数量：</span>
        <el-input-number v-model="currentPeriod.totalQuantity" :controls="false" size="small" :disabled="isReadonly" class="total-input" @change="updateData" />
      </div>

      <el-table :data="computedCurrent" border class="customer-table" :header-cell-style="{ fontSize: '13px', fontWeight: '600', background: '#f5f7fa', textAlign: 'center' }">
        <el-table-column label="序号" width="55" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column label="客户名称" min-width="160">
          <template #default="{ row, $index }"><el-input v-model="currentPeriod.rows[$index].name" size="small" :disabled="isReadonly" placeholder="客户" @input="updateData" /></template>
        </el-table-column>
        <el-table-column label="销售金额" width="120" align="right">
          <template #default="{ row, $index }"><WpAmountInput v-model="currentPeriod.rows[$index].amount" size="small" :disabled="isReadonly" class="num-cell" @change="updateData" /></template>
        </el-table-column>
        <el-table-column label="销售金额占比" width="110" align="right">
          <template #default="{ row }"><el-tooltip content="公式: IF(金额=0,0,金额/本期销售总额)" placement="top" :show-after="200"><span class="has-formula">{{ fmtPercent(row.amountRatio) }}</span></el-tooltip></template>
        </el-table-column>
        <el-table-column label="销售数量" width="100" align="right">
          <template #default="{ row, $index }"><el-input-number v-model="currentPeriod.rows[$index].quantity" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateData" /></template>
        </el-table-column>
        <el-table-column label="销售数量占比" width="110" align="right">
          <template #default="{ row }"><el-tooltip content="公式: IF(数量=0,0,数量/本期总数量)" placement="top" :show-after="200"><span class="has-formula">{{ fmtPercent(row.quantityRatio) }}</span></el-tooltip></template>
        </el-table-column>
        <el-table-column label="上期排名" width="80" align="center">
          <template #default="{ row, $index }"><el-input v-model="currentPeriod.rows[$index].priorRank" size="small" :disabled="isReadonly" placeholder="" @input="updateData" /></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="40" fixed="right">
          <template #default="{ $index }"><el-button size="small" type="danger" text @click="removeRow('current', $index)">✕</el-button></template>
        </el-table-column>
      </el-table>
      <div class="sum-row">
        <span>合计：金额 {{ fmtAmt(currentSum.amount) }} ({{ fmtPercent(currentSumRatio.amount) }})，数量 {{ fmtAmt(currentSum.quantity) }} ({{ fmtPercent(currentSumRatio.quantity) }})</span>
      </div>
    </section>

    <!-- 上期客户 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">上期：</h4>
        <el-tooltip content="批量数据建议：先导出模板在Excel中填写后导入" placement="top" :show-after="300">
          <el-button size="small" :disabled="isReadonly" @click="addRow('prior')">+ 增行</el-button>
        </el-tooltip>
      </div>
      <div class="total-row">
        <span>上期销售总额：</span>
        <el-tooltip content="数据来源: D4-7按产品毛利分析上期合计行(L26)" placement="right" :show-after="200">
          <el-input-number v-model="priorPeriod.totalAmount" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="total-input" @change="updateData" />
        </el-tooltip>
        <span style="margin-left:16px">上期总数量：</span>
        <el-input-number v-model="priorPeriod.totalQuantity" :controls="false" size="small" :disabled="isReadonly" class="total-input" @change="updateData" />
      </div>
      <el-table :data="computedPrior" border class="customer-table" :header-cell-style="{ fontSize: '13px', fontWeight: '600', background: '#f5f7fa', textAlign: 'center' }">
        <el-table-column label="序号" width="55" align="center"><template #default="{ $index }">{{ $index + 1 }}</template></el-table-column>
        <el-table-column label="客户名称" min-width="160"><template #default="{ row, $index }"><el-input v-model="priorPeriod.rows[$index].name" size="small" :disabled="isReadonly" placeholder="客户" @input="updateData" /></template></el-table-column>
        <el-table-column label="销售金额" width="120" align="right"><template #default="{ row, $index }"><WpAmountInput v-model="priorPeriod.rows[$index].amount" size="small" :disabled="isReadonly" class="num-cell" @change="updateData" /></template></el-table-column>
        <el-table-column label="销售金额占比" width="110" align="right"><template #default="{ row }"><span class="has-formula">{{ fmtPercent(row.amountRatio) }}</span></template></el-table-column>
        <el-table-column label="销售数量" width="100" align="right"><template #default="{ row, $index }"><el-input-number v-model="priorPeriod.rows[$index].quantity" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateData" /></template></el-table-column>
        <el-table-column label="销售数量占比" width="110" align="right"><template #default="{ row }"><span class="has-formula">{{ fmtPercent(row.quantityRatio) }}</span></template></el-table-column>
        <el-table-column label="上期排名" width="80" align="center"><template #default="{ row, $index }"><el-input v-model="priorPeriod.rows[$index].priorRank" size="small" :disabled="isReadonly" @input="updateData" /></template></el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="40" fixed="right"><template #default="{ $index }"><el-button size="small" type="danger" text @click="removeRow('prior', $index)">✕</el-button></template></el-table-column>
      </el-table>
      <div class="sum-row">
        <span>合计：金额 {{ fmtAmt(priorSum.amount) }} ({{ fmtPercent(priorSumRatio.amount) }})，数量 {{ fmtAmt(priorSum.quantity) }} ({{ fmtPercent(priorSumRatio.quantity) }})</span>
      </div>
    </section>

    <!-- 三、审计说明 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">三、审计说明</h4>
        <div class="sec-actions">
          <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiLoadingKey === 'note'" :disabled="isReadonly || !aiAvailable" @click="generateNote">🤖 AI辅助</el-button></el-tooltip>
          <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-9-note')">💬</el-button>
        </div>
      </div>
      <p class="guidance-hint">本年前十名客户的销售额较去年增加/减少_____%，大于/小于本年营业收入比去年营业收入增加/减少的比率_____%</p>
      <p class="guidance-hint">主要是因为…………</p>
      <el-input type="textarea" :rows="4" :model-value="auditNote" :disabled="isReadonly" placeholder="请输入客户结构分析审计说明..." @input="(v: string) => updateNote(v)" />
    </section>

    <!-- 四、审计结论 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">四、审计结论</h4>
        <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiLoadingKey === 'conclusion'" :disabled="isReadonly || !aiAvailable" @click="generateConclusion">🤖 AI辅助</el-button></el-tooltip>
      </div>
      <el-input type="textarea" :rows="3" :model-value="auditConclusion" :disabled="isReadonly" placeholder="请输入审计结论..." @input="(v: string) => updateConclusion(v)" />
    </section>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示（IPO/上市公司）</summary>
      <div class="guidance-content">
        <p>1. 如果发行人的客户为公众公司，可获取客户的信息披露文件，与客户披露的采购金额核对，同时分析客户的偿债能力；</p>
        <p>2. 结合发行人业务特点和主要客户基本经营信息，分析客户购买力、结算周期和销售波动情况，是否存在客户异常采购的情况；</p>
        <p>3. 对当期销售占比较大的客户，了解大客户大量采购的原因，以及最终销售情况；对于重要客户为经销商的情况，关注终端客户同经销商地域的匹配性。</p>
        <p>4. 关注公司及其实际控制人与大客户是否存在除购销关系外的其他关系。</p>
      </div>
    </details>
  
    </template>

    <!-- 在线编辑：统一双向 sync host（替代 legacy GtOnlyOfficeSheet 单向入口） -->
    <template v-else>
      <div class="oo-container">
        <WorkpaperSyncEditorHost v-if="syncOoDescriptor" :descriptor="syncOoDescriptor" :bridge="syncBridge" />
        <div v-else class="oo-loading">正在打开 D4-9 同步编辑器…</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.d4-customer-structure { padding: 16px; }
.sec { margin-bottom: 20px; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; margin: 0 0 8px; }
.sec-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.sec-actions { display: flex; gap: 8px; align-items: center; }
.objective-list { padding: 10px 14px; background: #f5f7fa; border-radius: 6px; }
.objective-item { margin: 0; font-size: var(--wp-font-size, 13px); color: #303133; line-height: 1.7; }
.total-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: var(--wp-font-size, 13px); flex-wrap: wrap; }
.total-input { width: 140px; }
.total-input :deep(.el-input__inner) { text-align: right; }
.customer-table { font-size: var(--wp-font-size, 13px); }
.customer-table :deep(.el-table__cell) { font-size: var(--wp-font-size, 13px); padding: 4px 0; }
.num-cell { width: 100%; }
.num-cell :deep(.el-input__inner) { text-align: right; font-size: var(--wp-font-size, 13px); }
.has-formula { border-bottom: 1px dashed #909399; cursor: help; }
.sum-row { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; padding: 6px 12px; background: #f5f7fa; border-radius: 4px; }
.guidance-hint { font-size: 12px; color: #909399; margin: 0 0 4px; line-height: 1.6; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #f0f7ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { font-size: var(--wp-font-size, 13px); font-weight: 500; cursor: pointer; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.8; }
.guidance-content p { margin: 0 0 4px; }

.mode-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.mode-bar-status { display: flex; align-items: center; gap: 8px; }
.oo-container { min-height: 600px; height: calc(100vh - 280px); }
.oo-loading { padding: 40px; text-align: center; color: #909399; font-size: var(--wp-font-size, 13px); }
</style>
