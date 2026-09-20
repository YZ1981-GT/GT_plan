<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * D4TabCustomerPrice — D4-10 重要客户销售价格分析
 *
 * 对齐源模板真实结构（openpyxl实读 "重要客户销售价格分析D4-10"）：
 * 一、审计目标（固定文本）
 * 二、审计过程（AI辅助）
 * 主表：客户×产品 多行
 *   序号/客户名称/产品种类/销售金额/占比(=D/$D$总额)/销售数量/占比(=F/$F$总数量)
 *   /销售单价/年度均价(或销售指导价格)/与均价差异(=(H-I)/I)/差异原因
 *   /市场价格/与市场价差异(=(H-L)/L)/差异原因
 * 三、审计说明  四、审计结论
 *
 * 公式：E=IF(D=0,0,D/$D$34); G=IF(F=0,0,F/$F$34)
 *        J=IF(AND(I=0,H=0),0,IF(AND(I=0,H>0),1,(H-I)/I))
 *        M=IF(AND(L=0,H=0),0,IF(AND(L=0,H>0),1,(H-L)/L))
 */
import { ref, computed, inject, toRef, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from '../../sync/useWorkpaperSyncBridge'
import { readStoreProjection } from '../../sync/workpaperSyncApi'
import { capabilityForEntry } from '../../sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from '../../sync/WorkpaperSyncEditorHost.vue'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import type useD4CrossSheet from '../../composables/useD4CrossSheet'
import { eventBus } from '@/utils/eventBus'
import { mergeCustomers } from '../../composables/d4PriceUpstreamMerge'
import {
  D4_10_TOTAL_AMOUNT_PRESET,
  resolvePresetOrOverride,
} from '../../composables/useD4FormulaEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 上游联动（宿主 provide 的 useD4CrossSheet 实例） ────────────────────
// 从 D4-9 客户结构（customerStructureData，派生自 D4-2 主营明细）取重要客户行。
type D4CrossSheet = ReturnType<typeof useD4CrossSheet>
const crossSheet = inject<D4CrossSheet | null>('d4CrossSheet', null)

// ─── 异常价格阈值（客户价格：与均价/市价差异绝对值 > 20%） ────────────
const ABNORMAL_THRESHOLD = 0.2

// 双模式（结构化视图 / 在线编辑）
// ─── 双模式 sync bridge（批次B 第六张：D4-10 迁 useWorkpaperSyncBridge，sheet_key=d410-managed）──
//     flushSave/loadData 等为函数声明（提升），flushPendingSave 仅运行时调用（debounceTimer 已初始化）。
const D4_10_ENTRY = 'xlsx/gt-d4-operating-revenue'
const D4_10_SHEET_KEY = 'd410-managed'
const ooHealthy = ref(false)
async function checkOoHealth() {
  try {
    const res = await http.get(`/api/workpapers/onlyoffice/health`, { _silent: true } as any)
    ooHealthy.value = res.data?.data?.healthy ?? res.data?.healthy ?? false
  } catch { ooHealthy.value = false }
}
checkOoHealth()
const syncSwitching = ref(false)
const syncHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
function flushPendingSave() { if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null } flushSave() }
function reloadD410() { loadData(); loadNoteConclusion(); loadAuditProcess() }
const syncBridge = useWorkpaperSyncBridge({
  entryId: ref(D4_10_ENTRY),
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: ref(D4_10_SHEET_KEY),
  capability: capabilityForEntry(D4_10_ENTRY),
  flushHtml: async () => {
    flushPendingSave()
    const snap = await readStoreProjection({ projectId: props.projectId, wpId: props.wpId, entryId: D4_10_ENTRY })
    return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: D4_10_SHEET_KEY }
  },
  reloadHtml: async () => { reloadD410() },
})
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncBusy = computed(
  () => syncSwitching.value
    || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)
const editorMode = computed<'structured' | 'onlyoffice'>({
  get: () => (syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'structured'),
  set: (v) => { void switchMode(v) },
})
const modeOptions = computed(() => [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice', disabled: props.isReadonly || !ooHealthy.value || syncBusy.value },
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

const auditObjective = '利润表中记录的营业收入已发生，且与被审计单位有关，已记录于恰当的账户。'

// ─── 审计过程 ─────────────────────────────────────────────────────────
const auditProcess = ref('')
function loadAuditProcess() { auditProcess.value = props.allResponses.get('D4-10-audit-process')?.remark || '' }
watch(() => props.allResponses.get('D4-10-audit-process')?.remark, () => loadAuditProcess(), { immediate: true })
function updateAuditProcess(val: string) { if (props.isReadonly) return; auditProcess.value = val; persist('D4-10-audit-process', val) }

// ─── 数据 ────────────────────────────────────────────────────────────
interface PriceRow {
  rowId: string       // 稳定行身份（双向回写用，禁下标作身份）
  seq: number | null  // 序号（同客户多产品时仅首行有）
  customer: string
  product: string
  amount: number       // 销售金额
  quantity: number     // 销售数量
  unitPrice: number    // 销售单价 H
  avgPrice: number     // 年度均价(或指导价) I
  avgReason: string    // 与均价差异原因 K
  marketPrice: number  // 市场价格 L
  marketReason: string // 与市场差异原因 N
}

const rows = ref<PriceRow[]>([])
const totalAmount = ref(0)
const totalQuantity = ref(0)
/** 手工覆盖「本期销售总额」；false 时真源为预设 WP 公式 */
const totalAmountManualOverride = ref(false)
/** 公式真源声明（preset；用户手工覆盖后仍保留以便恢复） */
const TOTAL_AMOUNT_FORMULA_REF = D4_10_TOTAL_AMOUNT_PRESET

/** 生成稳定行身份（优先 crypto.randomUUID，回退时间+随机）。 */
function genRowId(): string {
  try { if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID() } catch { /* */ }
  return `r-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}
/** 历史无 rowId 行一次性补齐（不丢手工值，双向回写身份前提，同 D4-9 backfill）。 */
function backfillRowIds(list: PriceRow[]): boolean {
  let changed = false
  for (const r of list) { if (!r.rowId) { r.rowId = genRowId(); changed = true } }
  return changed
}

function loadData() {
  const resp = props.allResponses.get('D4-10-data')
  if (resp?.remark) {
    try {
      const d = JSON.parse(resp.remark)
      rows.value = d.rows || []
      totalAmount.value = d.totalAmount || 0
      totalQuantity.value = d.totalQuantity || 0
      totalAmountManualOverride.value = Boolean(d.totalAmountManualOverride)
      // totalAmountFormulaRef 持久化供导入导出；运行时预设常量即 SoT，二次编辑走 manualOverride
      if (backfillRowIds(rows.value) && !props.isReadonly) persistData()
      return
    } catch {}
  }
  rows.value = []
  totalAmount.value = 0
  totalQuantity.value = 0
  totalAmountManualOverride.value = false
}
watch(() => props.allResponses.get('D4-10-data')?.remark, () => loadData(), { immediate: true })

/** 公式派生总额：未审合计 ≡ WP('D4-2','本期未审合计')；上游空不造 0 */
const formulaTotalAmount = computed(() => {
  const upstream = crossSheet?.mainRevenueUnadjustedTotal?.value.current
    ?? crossSheet?.mainRevenueTotal.value.current
    ?? 0
  return upstream > 0 ? upstream : 0
})

watch(
  formulaTotalAmount,
  (upstream) => {
    const next = resolvePresetOrOverride({
      presetValue: upstream,
      storedValue: totalAmount.value,
      manualOverride: totalAmountManualOverride.value,
    })
    if (!totalAmountManualOverride.value && next !== totalAmount.value && (upstream > 0 || next === 0)) {
      if (upstream > 0) {
        totalAmount.value = next
        persistData()
      }
    }
  },
  { immediate: true },
)

function onTotalAmountInput(v: number) {
  if (props.isReadonly) return
  totalAmountManualOverride.value = true
  totalAmount.value = v
  updateData()
}

function resetTotalAmountToFormula() {
  if (props.isReadonly) return
  totalAmountManualOverride.value = false
  const upstream = formulaTotalAmount.value
  if (upstream > 0) totalAmount.value = upstream
  persistData()
}

// 计算列
interface ComputedPriceRow extends PriceRow {
  amountRatio: number    // E=D/$D总额
  quantityRatio: number  // G=F/$F总数量
  avgDiff: number | null // J=(H-I)/I
  marketDiff: number | null // M=(H-L)/L
}
const computedRows = computed<ComputedPriceRow[]>(() => rows.value.map(r => ({
  ...r,
  amountRatio: totalAmount.value === 0 ? 0 : r.amount / totalAmount.value,
  quantityRatio: totalQuantity.value === 0 ? 0 : r.quantity / totalQuantity.value,
  avgDiff: (r.avgPrice === 0 && r.unitPrice === 0) ? 0 : r.avgPrice === 0 ? (r.unitPrice > 0 ? 1 : 0) : (r.unitPrice - r.avgPrice) / r.avgPrice,
  marketDiff: (r.marketPrice === 0 && r.unitPrice === 0) ? 0 : r.marketPrice === 0 ? (r.unitPrice > 0 ? 1 : 0) : (r.unitPrice - r.marketPrice) / r.marketPrice,
})))

// ─── 异常客户清单 + 回标上游（方案 C，spec Req 4.1） ──────────────────
// 与均价/市价差异绝对值 > 20% 视为价格异常，按客户名归并（取最大差异率），
// 经 eventBus 'd4:price-abnormal' 回标 D4-2 主营明细对应行。幂等：每次发全量异常集，
// 空集 = 清除本表标记（由接收端处理）。
const abnormalCustomers = computed(() => {
  const byName = new Map<string, number>()
  for (const r of computedRows.value) {
    const maxDiff = Math.max(
      r.avgDiff != null ? Math.abs(r.avgDiff) : 0,
      r.marketDiff != null ? Math.abs(r.marketDiff) : 0,
    )
    const name = (r.customer || '').trim()
    if (!name || maxDiff <= ABNORMAL_THRESHOLD) continue
    byName.set(name, Math.max(byName.get(name) ?? 0, maxDiff))
  }
  return [...byName.entries()].map(([name, diffPct]) => ({ name, diffPct }))
})

watch(abnormalCustomers, (items) => {
  eventBus.emit('d4:price-abnormal', {
    wpCode: 'D4-10',
    targetKey: 'customer',
    items,
    timestamp: Date.now(),
  })
}, { deep: true })

function addRow() {
  if (props.isReadonly) return
  rows.value.push({ rowId: genRowId(), seq: null, customer: '', product: '', amount: 0, quantity: 0, unitPrice: 0, avgPrice: 0, avgReason: '', marketPrice: 0, marketReason: '' })
  persistData()
}
function removeRow(idx: number) { if (props.isReadonly) return; rows.value.splice(idx, 1); persistData() }
function updateData() { if (props.isReadonly) return; persistData() }
function persistData() {
  const data = {
    rows: rows.value,
    totalAmount: totalAmount.value,
    totalQuantity: totalQuantity.value,
    totalAmountManualOverride: totalAmountManualOverride.value,
    totalAmountFormulaRef: TOTAL_AMOUNT_FORMULA_REF,
  }
  props.allResponses.set('D4-10-data', { item_id: 'D4-10-data', conclusion: null, remark: JSON.stringify(data) })
  debounceSave()
}

// ─── 审计说明/结论 ────────────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')
function loadNoteConclusion() { auditNote.value = props.allResponses.get('D4-10-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-10-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-10-note')?.remark, () => loadNoteConclusion(), { immediate: true })
function updateNote(val: string) { if (props.isReadonly) return; auditNote.value = val; persist('D4-10-note', val); emitNoteUpdated() }
function updateConclusion(val: string) { if (props.isReadonly) return; auditConclusion.value = val; persist('D4-10-conclusion', val); emitNoteUpdated() }
// 结论/说明变更 → 供 D4 附注/审计说明消费（方案 C，spec Req 5.1，复用现有事件族+桥）
function emitNoteUpdated() { eventBus.emit('disclosure:note-text-updated', { wpCode: 'D4-10', timestamp: Date.now() }) }

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
    const abnormals = computedRows.value.filter(r => r.avgDiff != null && Math.abs(r.avgDiff) > 0.2)
    const ctx = `异常价格差异客户：${abnormals.length ? abnormals.map(r => `${r.customer}-${r.product}与均价差异${fmtPercent(r.avgDiff)}`).join('、') : '无'}\n总行数：${rows.value.length}`
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
    const ctx = `审计说明：${auditNote.value || '（未填写）'}`
    const text = await callD4Ai('adj-conclusion', ctx)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateConclusion(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

// ─── 导入导出 ────────────────────────────────────────────────────────
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: toRef(props, 'wpId') as Ref<string>, projectId: toRef(props, 'projectId') as Ref<string> })
function handleExportTemplate() { exportTemplate('D4-10' as any) }
function handleExportData() { exportData('D4-10' as any) }
function handleImportUpload(file: File): boolean { importData('D4-10' as any, file).then(r => { if (r && r.rowCount > 0) loadData() }); return false }

// ─── 从 D4-9 客户结构导入（上游联动，spec Req 2） ────────────────────
// merge：按客户名去重，只填客户名/销售金额（录入列），不覆盖手工改过的行；
// 派生列（占比/差异）交前端 computed 重算；本期销售总额自动 = D4-2 主营合计。
const importingUpstream = ref(false)
async function importFromUpstream() {
  if (props.isReadonly) return
  if (!crossSheet) { ElMessage.warning('上游联动未就绪，请在营业收入底稿内打开本表'); return }
  const upstream = crossSheet.customerStructureData.value
  if (!upstream || upstream.length === 0) {
    ElMessage.warning('D4-2 主营明细为空，无法取客户结构；请先编制 D4-2 主营业务收入明细')
    return
  }
  importingUpstream.value = true
  try {
    const { added, updated } = mergeCustomers(
      rows.value,
      upstream,
      (name, amount) => ({ rowId: genRowId(), seq: null, customer: name, product: '', amount, quantity: 0, unitPrice: 0, avgPrice: 0, avgReason: '', marketPrice: 0, marketReason: '' }),
    )
    // 本期销售总额自动带出（公式真源 WP('D4-2','本期未审合计')；仅在未手工覆盖时填）
    const upstreamTotal = crossSheet.mainRevenueTotal.value.current
    if (!totalAmountManualOverride.value && upstreamTotal) {
      totalAmount.value = upstreamTotal
    } else if (!totalAmount.value && upstreamTotal) {
      totalAmount.value = upstreamTotal
    }
    persistData()
    ElMessage.success(`已从 D4-9 客户结构导入：新增 ${added} 户、补金额 ${updated} 户`)
  } finally {
    importingUpstream.value = false
  }
}

// ─── 持久化 ──────────────────────────────────────────────────────────
let debounceTimer: ReturnType<typeof setTimeout> | null = null
function persist(itemId: string, value: string) { props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: value }); debounceSave() }
function debounceSave() { if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000) }
function flushSave() { const keys = ['D4-10-audit-process', 'D4-10-data', 'D4-10-note', 'D4-10-conclusion']; const items = keys.map(k => props.allResponses.get(k)).filter(Boolean); window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } })) }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })
</script>


<template>
  <div class="d4-customer-price">

    <!-- 双模式切换 -->
    <div class="mode-bar">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      <el-tag :type="syncStateTag.type" size="small" effect="light">{{ syncStateTag.text }}</el-tag>
    </div>

    <!-- 结构化视图 -->
    <template v-if="editorMode === 'structured'">    <!-- 一、审计目标 -->
    <section class="sec">
      <h4 class="sec-title">一、审计目标</h4>
      <div class="objective-list"><p class="objective-item">{{ auditObjective }}</p></div>
    </section>

    <!-- 二、审计过程 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">二、审计过程</h4>
        <el-tooltip :content="aiTip" placement="top">
          <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable">🤖 AI辅助</el-button>
        </el-tooltip>
      </div>
      <el-input type="textarea" :rows="2" :model-value="auditProcess" :disabled="isReadonly"
        placeholder="1.选取定价有较大或异常变化的产品进行测试，检查售价变动是否符合定价政策，价格变动是否合理。"
        @input="(v: string) => updateAuditProcess(v)" />
    </section>

    <!-- 主表 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">重要客户销售价格分析</h4>
        <div class="sec-actions">
          <el-tooltip content="从 D4-9 客户结构（源自 D4-2 主营明细）导入重要客户与销售金额，自动带出本期销售总额" placement="top" :show-after="300">
            <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="importingUpstream" @click="importFromUpstream">从 D4-9 导入客户</el-button>
          </el-tooltip>
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
            <el-button size="small" :disabled="isReadonly" @click="addRow">+ 增行</el-button>
          </el-tooltip>
          <GtIndexChip value="wp:D4-9" :context-project-id="projectId" />
          <GtIndexChip value="wp:D4-11" :context-project-id="projectId" />
        </div>
      </div>

      <!-- 本期销售总额：公式真源 WP('D4-2','本期未审合计')；手工可覆盖并「恢复公式」 -->
      <div class="total-row">
        <span>本期销售总额：</span>
        <el-tooltip
          :content="totalAmountManualOverride
            ? `已手工覆盖（原公式 ${TOTAL_AMOUNT_FORMULA_REF}）`
            : `公式取数: ${TOTAL_AMOUNT_FORMULA_REF} ≡ D4-2 主营本期合计`"
          placement="right"
          :show-after="200"
        >
          <el-input-number
            :model-value="totalAmount"
            :controls="false"
            size="small"
            :disabled="isReadonly"
            :precision="2"
            class="total-input"
            @update:model-value="(v: number | undefined) => onTotalAmountInput(Number(v ?? 0))"
          />
        </el-tooltip>
        <el-tag v-if="!totalAmountManualOverride" size="small" type="info" class="formula-tag" effect="plain">
          {{ TOTAL_AMOUNT_FORMULA_REF }}
        </el-tag>
        <el-button
          v-else
          size="small"
          link
          type="primary"
          :disabled="isReadonly"
          @click="resetTotalAmountToFormula"
        >恢复公式</el-button>
        <span style="margin-left:16px">本期总数量：</span>
        <el-input-number v-model="totalQuantity" :controls="false" size="small" :disabled="isReadonly" class="total-input" @change="updateData" />
      </div>

      <el-table :data="computedRows" border class="price-table" max-height="520"
        :header-cell-style="{ fontSize: '13px', fontWeight: '600', background: '#f5f7fa', textAlign: 'center' }">
        <el-table-column label="序号" width="55" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column label="客户名称" min-width="120">
          <template #default="{ $index }"><el-input v-model="rows[$index].customer" size="small" :disabled="isReadonly" placeholder="客户" @input="updateData" /></template>
        </el-table-column>
        <el-table-column label="产品种类" min-width="100">
          <template #default="{ $index }"><el-input v-model="rows[$index].product" size="small" :disabled="isReadonly" placeholder="产品" @input="updateData" /></template>
        </el-table-column>
        <!-- 销售情况 -->
        <el-table-column label="销售情况" align="center">
          <el-table-column label="销售金额" width="100" align="right">
            <template #default="{ $index }"><WpAmountInput v-model="rows[$index].amount" size="small" :disabled="isReadonly" class="num-cell" @change="updateData" /></template>
          </el-table-column>
          <el-table-column label="占比" width="75" align="right">
            <template #default="{ row }"><el-tooltip content="公式: IF(金额=0,0,金额/本期销售总额)" placement="top" :show-after="200"><span class="has-formula">{{ fmtPercent(row.amountRatio) }}</span></el-tooltip></template>
          </el-table-column>
          <el-table-column label="销售数量" width="85" align="right">
            <template #default="{ $index }"><el-input-number v-model="rows[$index].quantity" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateData" /></template>
          </el-table-column>
          <el-table-column label="占比" width="75" align="right">
            <template #default="{ row }"><el-tooltip content="公式: IF(数量=0,0,数量/本期总数量)" placement="top" :show-after="200"><span class="has-formula">{{ fmtPercent(row.quantityRatio) }}</span></el-tooltip></template>
          </el-table-column>
        </el-table-column>
        <!-- 销售单价分析 -->
        <el-table-column label="销售单价分析" align="center">
          <el-table-column label="销售单价" width="90" align="right">
            <template #default="{ $index }"><el-input-number v-model="rows[$index].unitPrice" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateData" /></template>
          </el-table-column>
          <el-table-column label="年度均价" width="90" align="right">
            <template #default="{ $index }">
              <el-tooltip content="年度均价或销售指导价格" placement="top" :show-after="200">
                <el-input-number v-model="rows[$index].avgPrice" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateData" />
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="与均价差异" width="90" align="right">
            <template #default="{ row }">
              <el-tooltip content="公式: IF(均价=0且单价=0,0,IF(均价=0且单价>0,100%,(单价-均价)/均价))" placement="top" :show-after="200">
                <span :class="['has-formula', { 'val-exceed': row.avgDiff != null && Math.abs(row.avgDiff) > 0.2 }]">{{ fmtPercent(row.avgDiff) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="差异原因" min-width="100">
            <template #default="{ $index }"><el-input v-model="rows[$index].avgReason" size="small" :disabled="isReadonly" placeholder="" @input="updateData" /></template>
          </el-table-column>
          <el-table-column label="市场价格" width="90" align="right">
            <template #default="{ $index }"><el-input-number v-model="rows[$index].marketPrice" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateData" /></template>
          </el-table-column>
          <el-table-column label="与市场差异" width="90" align="right">
            <template #default="{ row }">
              <el-tooltip content="公式: IF(市场价=0且单价=0,0,IF(市场价=0且单价>0,100%,(单价-市场价)/市场价))" placement="top" :show-after="200">
                <span :class="['has-formula', { 'val-exceed': row.marketDiff != null && Math.abs(row.marketDiff) > 0.2 }]">{{ fmtPercent(row.marketDiff) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="差异原因" min-width="100">
            <template #default="{ $index }"><el-input v-model="rows[$index].marketReason" size="small" :disabled="isReadonly" placeholder="" @input="updateData" /></template>
          </el-table-column>
        </el-table-column>
        <!-- 操作 -->
        <el-table-column v-if="!isReadonly" label="" width="40" fixed="right">
          <template #default="{ $index }"><el-button size="small" type="danger" text @click="removeRow($index)">✕</el-button></template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 三、审计说明 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">三、审计说明</h4>
        <div class="sec-actions">
          <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiLoadingKey === 'note'" :disabled="isReadonly || !aiAvailable" @click="generateNote">🤖 AI辅助</el-button></el-tooltip>
          <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-10-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="4" :model-value="auditNote" :disabled="isReadonly" placeholder="请输入客户销售价格分析审计说明..." @input="(v: string) => updateNote(v)" />
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
      <summary>📋 编制提示（舞弊风险关注）</summary>
      <div class="guidance-content">
        <p>根据《中国注册会计师审计准则问题解答第18号——识别和应对第三方配合实施财务舞弊》：</p>
        <p>1. 在第三方配合下，进行显失公允的交易。例如，以明显高于其他客户的价格向第三方销售商品。</p>
        <p>2. 与同一客户或同受一方控制的多个客户在各期发生多次交易，在客户配合下，通过调节各次交易的商品销售价格，调节各期销售收入金额。</p>
      </div>
    </details>
  
    </template>

    <!-- 在线编辑：平台 sync bridge（批次B 迁移，非裸 GtOnlyOfficeSheet） -->
    <template v-else>
      <div style="min-height: 600px; height: calc(100vh - 280px);">
        <WorkpaperSyncEditorHost v-if="syncOoDescriptor" ref="syncHostRef" :descriptor="syncOoDescriptor" :bridge="syncBridge" />
        <div v-else class="oo-loading">正在打开 D4-10 同步编辑器…</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.d4-customer-price { padding: 16px; }
.sec { margin-bottom: 20px; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; margin: 0 0 8px; }
.sec-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.sec-actions { display: flex; gap: 8px; align-items: center; }
.objective-list { padding: 10px 14px; background: #f5f7fa; border-radius: 6px; }
.objective-item { margin: 0; font-size: var(--wp-font-size, 13px); color: #303133; line-height: 1.7; }
.total-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: var(--wp-font-size, 13px); flex-wrap: wrap; }
.formula-tag { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; max-width: 280px; overflow: hidden; text-overflow: ellipsis; }
.total-input { width: 140px; }
.total-input :deep(.el-input__inner) { text-align: right; }
.price-table { font-size: var(--wp-font-size, 13px); }
.price-table :deep(.el-table__cell) { font-size: var(--wp-font-size, 13px); padding: 4px 0; }
.num-cell { width: 100%; }
.num-cell :deep(.el-input__inner) { text-align: right; font-size: var(--wp-font-size, 13px); }
.has-formula { border-bottom: 1px dashed #909399; cursor: help; }
.val-exceed { color: #f56c6c; font-weight: 600; }
.guidance-details { margin-top: 16px; border-left: 3px solid #e6a23c; background: #fdf6ec; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { font-size: var(--wp-font-size, 13px); font-weight: 500; cursor: pointer; color: #e6a23c; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.8; }
.guidance-content p { margin: 0 0 4px; }

.mode-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
