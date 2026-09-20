<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * D4TabOtherContract — D4-34 其他业务收入合同测算表
 *
 * 双区块：房屋租赁业务(11列) + 咨询业务(10列)
 * 差异=本期实计收入-本期应计收入 自动计算
 * 双模式 + AI + 导入导出
 */
import { ref, computed, inject, watch, onBeforeUnmount, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import { parseNum, calcChangeAmount } from '../../composables/useD4FormulaEngine'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { Plus } from '@element-plus/icons-vue'
import { useD4InspectionWriteback } from '../../composables/useD4InspectionWriteback'
import { d4_34Candidates, D4_OTHER_ACCOUNT_CODE, D4_OTHER_ACCOUNT_NAME } from '../../composables/d4OtherGroupPushPredicates'
import { eventBus } from '@/utils/eventBus'
// D4-34 双向回写：子组件自管 sync bridge（dedicated sync sheet，sheetKey=d434-managed，
// 同 entry gt-d4-operating-revenue；后端 phase5_d4_other_contract_sheet 作为 sibling sheet
// 并入 phase5_d4_revenue_detail，adapter d4.revenue_detail）——与 D4-9 同架构（双区 dict store）。
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from '../../sync/useWorkpaperSyncBridge'
import GtEntrySyncCapabilityNotice from '../../sync/GtEntrySyncCapabilityNotice.vue'
import WorkpaperSyncEditorHost from '../../sync/WorkpaperSyncEditorHost.vue'
import { readStoreProjection } from '../../sync/workpaperSyncApi'
import { capabilityForEntry } from '../../sync/workpaperSyncCapability'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

interface RentalRow { id: string; tenant: string; period: string; area: string; unitPrice: number|string; contractRef: string; actualMonths: number|string; expectedRevenue: number|string; actualRevenue: number|string; diff: number; indexRef: string }
interface ConsultRow { id: string; client: string; project: string; duration: string; contractAmount: number|string; contractRef: string; expectedRevenue: number|string; actualRevenue: number|string; diff: number; indexRef: string }

const rentals = ref<RentalRow[]>([])
const consults = ref<ConsultRow[]>([])
const auditNote = ref(''); const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// 数值解析走引擎单一真源（替换本地 pn，消除第二套解析路径）
const pn = parseNum

function createRental(name: string): RentalRow { return { id: `rt-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,6)}`, tenant: name, period: '', area: '', unitPrice: '', contractRef: '', actualMonths: '', expectedRevenue: '', actualRevenue: '', diff: 0, indexRef: '' } }
function createConsult(name: string): ConsultRow { return { id: `cs-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,6)}`, client: name, project: '', duration: '', contractAmount: '', contractRef: '', expectedRevenue: '', actualRevenue: '', diff: 0, indexRef: '' } }

function loadData() {
  const r = props.allResponses.get('D4-34-data')
  if (r?.remark) { try { const p = JSON.parse(r.remark); if (p) { rentals.value = p.rentals || []; consults.value = p.consults || []; return } } catch {} }
  rentals.value = []; consults.value = []
}
function loadNote() { auditNote.value = props.allResponses.get('D4-34-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-34-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-34-data')?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get('D4-34-note')?.remark, loadNote, { immediate: true })

async function addRental() { if (props.isReadonly) return; try { const { value } = await ElMessageBox.prompt('请输入承租方名称', '添加租赁记录', { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' }); if (value?.trim()) { rentals.value.push(createRental(value.trim())); persistAll() } } catch {} }
async function addConsult() { if (props.isReadonly) return; try { const { value } = await ElMessageBox.prompt('请输入委托方名称', '添加咨询记录', { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' }); if (value?.trim()) { consults.value.push(createConsult(value.trim())); persistAll() } } catch {} }
function removeRental(id: string) { if (props.isReadonly) return; rentals.value = rentals.value.filter(r => r.id !== id); persistAll() }
function removeConsult(id: string) { if (props.isReadonly) return; consults.value = consults.value.filter(r => r.id !== id); persistAll() }

// 差异 = 实计 - 应计，走引擎 calcChangeAmount（单一真源，保留符号不 abs）
function updateRental(id: string, field: keyof RentalRow, value: any) { if (props.isReadonly) return; const row = rentals.value.find(r => r.id === id); if (!row) return; (row as any)[field] = value; row.diff = calcChangeAmount(pn(row.actualRevenue), pn(row.expectedRevenue)); persistAll() }
function updateConsult(id: string, field: keyof ConsultRow, value: any) { if (props.isReadonly) return; const row = consults.value.find(r => r.id === id); if (!row) return; (row as any)[field] = value; row.diff = calcChangeAmount(pn(row.actualRevenue), pn(row.expectedRevenue)); persistAll() }

function persistAll() {
  props.allResponses.set('D4-34-data', { item_id: 'D4-34-data', conclusion: null, remark: JSON.stringify({ rentals: rentals.value, consults: consults.value }) })
  props.allResponses.set('D4-34-note', { item_id: 'D4-34-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-34-conclusion', { item_id: 'D4-34-conclusion', conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; const keys = ['D4-34-data','D4-34-note','D4-34-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }, 2000)
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
// 同步 flush：立即派发待存改动（清 debounce），供 bridge.flushHtml 在 readStoreProjection 前落库，
// 防投影读到旧值（与 D4-20 flushPendingSave 同职责）。
function flushPendingSave() {
  if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null }
  const keys = ['D4-34-data','D4-34-note','D4-34-conclusion']
  window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushPendingSave() } })

// ─── 双模式 sync bridge（D4-34 其他业务收入合同测算，dedicated sync sheet）──────────
const D4_34_ENTRY = 'xlsx/gt-d4-operating-revenue'
const D4_34_SHEET_KEY = 'd434-managed'
const ooHealthy = ref(false)
async function checkOoHealth() {
  try { const r = await http.get('/api/onlyoffice/health', { _silent: true } as any); ooHealthy.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' } catch { ooHealthy.value = false }
}
checkOoHealth()
const syncSwitching = ref(false)
const syncBridge = useWorkpaperSyncBridge({
  entryId: ref(D4_34_ENTRY),
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: ref(D4_34_SHEET_KEY),
  capability: capabilityForEntry(D4_34_ENTRY),
  flushHtml: async () => {
    flushPendingSave()
    const snap = await readStoreProjection({ projectId: props.projectId, wpId: props.wpId, entryId: D4_34_ENTRY })
    return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: D4_34_SHEET_KEY }
  },
  reloadHtml: async () => { if (reloadWorkpaperData) await reloadWorkpaperData() },
})
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncBusy = computed(
  () => syncSwitching.value
    || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)
const editorMode = computed<string>({
  get: () => (syncBridge.mode.value === 'oo' ? '在线编辑' : '表格视图'),
  set: (v: string) => { void switchMode(v === '在线编辑' ? 'onlyoffice' : 'structured') },
})
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
  return { text: syncBridge.mode.value === 'oo' ? 'Excel 在线编辑' : '表格视图', type: 'success' as const }
})
const modeOptions = ['表格视图', '在线编辑']
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)
async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于其他业务收入合同测算(D4-34)结果生成审计说明', rentalCount: rentals.value.length, consultCount: consults.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于合同测算结果生成审计结论', noteText: auditNote.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
function fmtAmt(v: number): string { return v ? v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—' }
function rowClass({ row }: { row: any }) { return row.diff !== 0 && row.diff ? 'row-diff' : '' }

// ─── A13 错报推送（科目 6051；两区差异各自独立成条，保留符号不 abs，走判据单一真源）─────
const { pushToA13 } = useD4InspectionWriteback({
  wpCode: 'D4-34',
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
const pushableCount = computed(() => d4_34Candidates(rentals.value as any, consults.value as any).length)
function pushDiffsToA13() {
  if (props.isReadonly) return
  const cands = d4_34Candidates(rentals.value as any, consults.value as any)
  if (!cands.length) { ElMessage.info('无合同测算差异，无需推送'); return }
  const items = cands.map(c => ({
    voucherNo: c.voucherNo,
    amount: c.refAmount ?? 0, // 差异保留符号，人工认定
    description: c.description,
    indexRef: c.indexRef,
  }))
  pushToA13(items, D4_OTHER_ACCOUNT_CODE, D4_OTHER_ACCOUNT_NAME)
}

// ─── 公式管理（打开平台全局公式管理中心，定位到本底稿 D4-34；同 E1 范式）───────────
// 平台唯一一套公式：wp_formula 表权威存储，后端权威执行 + CAS + 审计；
// 支持跨底稿 TB()/WP()/ROW() 取数联动与表内 SUM_ROW()/IF() 运算校对。
function openFormulaManager() {
  eventBus.emit('open-formula-manager', { nodeKey: 'wp_d4_34' })
}

// ─── OCR附件上传 ─────────────────────────────────────────────────────
async function handleOcrUpload(type: 'rental' | 'consult', rowId: string, file: File) {
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData, { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any)
    const fields = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) { ElMessage.info('OCR完成，未识别到可填充字段'); return }

    // 根据类型自动填入识别结果
    if (type === 'rental') {
      const row = rentals.value.find(r => r.id === rowId)
      if (!row) return
      if (fields.tenant || fields.party) { row.tenant = String(fields.tenant || fields.party); }
      if (fields.period || fields.duration) { row.period = String(fields.period || fields.duration); }
      if (fields.area) { row.area = String(fields.area); }
      if (fields.unitPrice || fields.price) { row.unitPrice = parseFloat(fields.unitPrice || fields.price) || ''; }
      if (fields.amount || fields.contractAmount) { row.expectedRevenue = parseFloat(fields.amount || fields.contractAmount) || ''; }
      persistAll()
    } else {
      const row = consults.value.find(r => r.id === rowId)
      if (!row) return
      if (fields.client || fields.party) { row.client = String(fields.client || fields.party); }
      if (fields.project || fields.serviceContent) { row.project = String(fields.project || fields.serviceContent); }
      if (fields.duration || fields.period) { row.duration = String(fields.duration || fields.period); }
      if (fields.contractAmount || fields.amount) { row.contractAmount = parseFloat(fields.contractAmount || fields.amount) || ''; }
      persistAll()
    }
    ElMessage.success('OCR结果已填入')
  } catch { ElMessage.warning('OCR识别失败') }
}
</script>

<template>
<div class="d4-other-contract">
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-button size="small" type="warning" plain :disabled="isReadonly||pushableCount===0" @click="pushDiffsToA13" title="把合同测算差异推送到 A13 未更正错报汇总（差异保留符号，人工认定）">推送差异至 A13{{ pushableCount ? `（${pushableCount}）` : '' }}</el-button><el-button size="small" @click="openFormulaManager" title="打开平台公式管理中心（唯一一套公式，支持跨底稿取数联动与表内校对）">ƒx 公式管理</el-button><el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu>
    <el-dropdown-item disabled class="dropdown-group-label">— 房屋租赁业务 —</el-dropdown-item>
    <el-dropdown-item @click="exportTemplate('D4-34-rental')">导出模板</el-dropdown-item>
    <el-dropdown-item @click="exportData('D4-34-rental')">导出数据</el-dropdown-item>
    <el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="(f:any)=>importData('D4-34-rental',f.raw||f)"><span>导入数据</span></el-upload></el-dropdown-item>
    <el-dropdown-item disabled class="dropdown-group-label">— 咨询业务 —</el-dropdown-item>
    <el-dropdown-item @click="exportTemplate('D4-34-consult')">导出模板</el-dropdown-item>
    <el-dropdown-item @click="exportData('D4-34-consult')">导出数据</el-dropdown-item>
    <el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="(f:any)=>importData('D4-34-consult',f.raw||f)"><span>导入数据</span></el-upload></el-dropdown-item>
  </el-dropdown-menu></template></el-dropdown><GtIndexChip value="wp:D4-34" :context-project-id="projectId" /><el-tag :type="syncStateTag.type" size="small" class="sync-state-tag">{{ syncStateTag.text }}</el-tag><GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d4-operating-revenue" /><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-34-contract')">💬 复核</el-button></div></div>

  <template v-if="editorMode !== '在线编辑'">
    <!-- 方法论折叠（审计目标+审计过程） -->
    <details class="methodology-collapse" open>
      <summary class="methodology-summary">📖 审计目标与审计过程（点击展开/收起）</summary>
      <div class="methodology-body">
        <p class="method-title"><strong>一、审计目标：</strong></p>
        <ol class="method-objectives">
          <li>利润表中记录的其他业务收入已发生，且与被审计单位有关，已记录于恰当的账户。</li>
          <li>所有应当记录的其他业务收入均已记录，所有应当包括在财务报表中的相关披露均已包括。</li>
          <li>与其他业务收入有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述。</li>
          <li>与其他业务收入有关的交易和事项已记录于正确的会计期间。</li>
        </ol>
        <p class="method-title"><strong>二、审计过程：</strong></p>
        <p class="method-hint">1. 房屋租赁业务（其他租赁可参照）：根据合同约定的租赁面积、单价、期间测算本期应确认收入，与实际确认金额核对差异。</p>
        <p class="method-hint">2. 咨询业务：根据合同约定的金额、期限测算本期应确认收入，与实际确认金额核对差异。</p>
      </div>
    </details>

    <!-- ═══ 区块1：房屋租赁业务 ═══ -->
    <div class="block-section rental-block">
      <div class="block-header"><span class="block-title">1. 房屋租赁业务</span><span class="block-hint">（其他租赁可参照）</span><el-button size="small" :disabled="isReadonly" @click="addRental"><el-icon :size="12"><Plus /></el-icon> 添加</el-button></div>
      <el-table :data="rentals" border stripe size="small" class="contract-table" :row-class-name="rowClass">
        <el-table-column label="#" width="40" align="center"><template #default="{ $index }">{{ $index+1 }}</template></el-table-column>
        <el-table-column label="承租方" min-width="100"><template #default="{ row }"><el-input v-model="row.tenant" size="small" :disabled="isReadonly" @change="updateRental(row.id,'tenant',row.tenant)" /></template></el-table-column>
        <el-table-column label="租赁期间" min-width="100"><template #default="{ row }"><el-input v-model="row.period" size="small" :disabled="isReadonly" @change="updateRental(row.id,'period',row.period)" /></template></el-table-column>
        <el-table-column label="租赁面积" min-width="80"><template #default="{ row }"><el-input v-model="row.area" size="small" :disabled="isReadonly" @change="updateRental(row.id,'area',row.area)" /></template></el-table-column>
        <el-table-column label="合同单价" min-width="90" align="right"><template #default="{ row }"><el-input-number v-model="row.unitPrice" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateRental(row.id,'unitPrice',row.unitPrice)" /></template></el-table-column>
        <el-table-column label="合同索引" width="70"><template #default="{ row }"><el-input v-model="row.contractRef" size="small" :disabled="isReadonly" @change="updateRental(row.id,'contractRef',row.contractRef)" /></template></el-table-column>
        <el-table-column label="实际租赁月数" min-width="80" align="right"><template #default="{ row }"><el-input-number v-model="row.actualMonths" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateRental(row.id,'actualMonths',row.actualMonths)" /></template></el-table-column>
        <el-table-column label="本期应计收入" min-width="100" align="right"><template #default="{ row }"><WpAmountInput v-model="row.expectedRevenue" size="small" :disabled="isReadonly" style="width:100%" @change="updateRental(row.id,'expectedRevenue',row.expectedRevenue)" /></template></el-table-column>
        <el-table-column label="本期实计收入" min-width="100" align="right"><template #default="{ row }"><WpAmountInput v-model="row.actualRevenue" size="small" :disabled="isReadonly" style="width:100%" @change="updateRental(row.id,'actualRevenue',row.actualRevenue)" /></template></el-table-column>
        <el-table-column min-width="80" align="right" class-name="auto-calc-col"><template #header><span class="auto-calc-header">差异 <el-tooltip content="本期实计收入 − 本期应计收入（自动计算）" placement="top"><span class="fx-mark">ƒx</span></el-tooltip></span></template><template #default="{ row }"><span class="auto-calc" :class="{ 'diff-warn': row.diff !== 0 }">{{ fmtAmt(row.diff) }}</span></template></el-table-column>
        <el-table-column label="索引" width="60"><template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="updateRental(row.id,'indexRef',row.indexRef)" /></template></el-table-column>
        <el-table-column label="附件" width="70" align="center">
          <template #default="{ row }">
            <el-dropdown trigger="click" size="small">
              <el-button link size="small" :disabled="isReadonly" title="上传合同附件并OCR识别">📎</el-button>
              <template #dropdown><el-dropdown-menu>
                <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="(f:any) => handleOcrUpload('rental', row.id, f.raw||f)"><span>上传文件</span></el-upload></el-dropdown-item>
                <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="(f:any) => handleOcrUpload('rental', row.id, f.raw||f)"><span>上传文件夹</span></el-upload></el-dropdown-item>
              </el-dropdown-menu></template>
            </el-dropdown>
          </template>
        </el-table-column>
        <el-table-column width="40" align="center"><template #default="{ row }"><el-popconfirm title="删除？" @confirm="removeRental(row.id)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">×</el-button></template></el-popconfirm></template></el-table-column>
      </el-table>
    </div>

    <!-- ═══ 区块2：咨询业务 ═══ -->
    <div class="block-section consult-block">
      <div class="block-header"><span class="block-title">2. 咨询业务</span><el-button size="small" :disabled="isReadonly" @click="addConsult"><el-icon :size="12"><Plus /></el-icon> 添加</el-button></div>
      <el-table :data="consults" border stripe size="small" class="contract-table" :row-class-name="rowClass">
        <el-table-column label="#" width="40" align="center"><template #default="{ $index }">{{ $index+1 }}</template></el-table-column>
        <el-table-column label="委托方" min-width="100"><template #default="{ row }"><el-input v-model="row.client" size="small" :disabled="isReadonly" @change="updateConsult(row.id,'client',row.client)" /></template></el-table-column>
        <el-table-column label="咨询项目" min-width="100"><template #default="{ row }"><el-input v-model="row.project" size="small" :disabled="isReadonly" @change="updateConsult(row.id,'project',row.project)" /></template></el-table-column>
        <el-table-column label="委托期限" min-width="80"><template #default="{ row }"><el-input v-model="row.duration" size="small" :disabled="isReadonly" @change="updateConsult(row.id,'duration',row.duration)" /></template></el-table-column>
        <el-table-column label="合同金额" min-width="100" align="right"><template #default="{ row }"><WpAmountInput v-model="row.contractAmount" size="small" :disabled="isReadonly" style="width:100%" @change="updateConsult(row.id,'contractAmount',row.contractAmount)" /></template></el-table-column>
        <el-table-column label="合同索引" width="70"><template #default="{ row }"><el-input v-model="row.contractRef" size="small" :disabled="isReadonly" @change="updateConsult(row.id,'contractRef',row.contractRef)" /></template></el-table-column>
        <el-table-column label="本期应计收入" min-width="100" align="right"><template #default="{ row }"><WpAmountInput v-model="row.expectedRevenue" size="small" :disabled="isReadonly" style="width:100%" @change="updateConsult(row.id,'expectedRevenue',row.expectedRevenue)" /></template></el-table-column>
        <el-table-column label="本期实计收入" min-width="100" align="right"><template #default="{ row }"><WpAmountInput v-model="row.actualRevenue" size="small" :disabled="isReadonly" style="width:100%" @change="updateConsult(row.id,'actualRevenue',row.actualRevenue)" /></template></el-table-column>
        <el-table-column min-width="80" align="right" class-name="auto-calc-col"><template #header><span class="auto-calc-header">差异 <el-tooltip content="本期实计收入 − 本期应计收入（自动计算）" placement="top"><span class="fx-mark">ƒx</span></el-tooltip></span></template><template #default="{ row }"><span class="auto-calc" :class="{ 'diff-warn': row.diff !== 0 }">{{ fmtAmt(row.diff) }}</span></template></el-table-column>
        <el-table-column label="索引" width="60"><template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="updateConsult(row.id,'indexRef',row.indexRef)" /></template></el-table-column>
        <el-table-column label="附件" width="70" align="center">
          <template #default="{ row }">
            <el-dropdown trigger="click" size="small">
              <el-button link size="small" :disabled="isReadonly" title="上传合同附件并OCR识别">📎</el-button>
              <template #dropdown><el-dropdown-menu>
                <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="(f:any) => handleOcrUpload('consult', row.id, f.raw||f)"><span>上传文件</span></el-upload></el-dropdown-item>
                <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="(f:any) => handleOcrUpload('consult', row.id, f.raw||f)"><span>上传文件夹</span></el-upload></el-dropdown-item>
              </el-dropdown-menu></template>
            </el-dropdown>
          </template>
        </el-table-column>
        <el-table-column width="40" align="center"><template #default="{ row }"><el-popconfirm title="删除？" @confirm="removeConsult(row.id)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">×</el-button></template></el-popconfirm></template></el-table-column>
      </el-table>
    </div>

    <!-- 审计意见区 -->
    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="分析合同测算差异原因" @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断其他业务收入确认是否合理" @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>
  </template>
  <!-- 在线编辑：平台 sync bridge（dedicated sync sheet，非裸 GtOnlyOfficeSheet） -->
  <template v-if="editorMode==='在线编辑'"><div class="oo-container"><WorkpaperSyncEditorHost v-if="syncOoDescriptor" :descriptor="syncOoDescriptor" :bridge="syncBridge" /><div v-else class="oo-loading">正在打开 D4-34 同步编辑器…</div></div></template>
</div>
</template>

<style scoped>
.d4-other-contract{padding:16px 20px;font-size: var(--wp-font-size, 13px)}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
:deep(.dropdown-group-label) { font-size: 12px; color: #909399; cursor: default; }
.block-section{margin-bottom:20px;border:1px solid #ebeef5;border-radius:8px;padding:14px 16px}
.methodology-collapse{margin-bottom:16px;border-radius:6px;border:1px solid #faecd8;border-left:3px solid #e6a23c;background:#fffbf0}.methodology-summary{cursor:pointer;padding:8px 14px;font-size: var(--wp-font-size, 13px);font-weight:500;color:#b88230}.methodology-body{padding:8px 14px 12px;font-size:12px;color:#606266;line-height:1.8}.method-title{margin-bottom:4px;font-size: var(--wp-font-size, 13px)}.method-objectives{margin:4px 0 10px 16px;padding:0}.method-objectives li{margin-bottom:3px}.method-hint{margin-bottom:4px;color:#909399;font-style:italic}
.rental-block{border-left:3px solid #67c23a}
.consult-block{border-left:3px solid #409eff}
.block-header{display:flex;align-items:center;gap:12px;margin-bottom:10px}.block-title{font-size:14px;font-weight:600;color:#303133}.block-hint{font-size:12px;color:#909399}
.contract-table{font-size: var(--wp-font-size, 13px)}.contract-table :deep(.el-table__cell){padding:5px 4px}.contract-table :deep(.row-diff td){background-color:#fdf6ec !important}
.auto-calc{color:#909399;font-style:italic;border-bottom:1px dashed #c0c4cc;cursor:help}.diff-warn{color:#e6a23c;font-weight:600;font-style:normal}
/* 自动计算列统一灰底，对齐 D4-2 蓝本 .auto-calc-col */
.contract-table :deep(td.auto-calc-col.el-table__cell){background-color:#f5f7fa !important}
.auto-calc-header{color:#606266}.auto-calc-header .fx-mark{color:#909399;font-style:italic;font-size:11px}
.audit-opinion-card{margin-bottom:16px}.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
</style>
