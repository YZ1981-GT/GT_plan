<script setup lang="ts">
/**
 * D4TabReturn — D4-20 销售退货检查表
 *
 * 6大结构区域：
 * 1. 产品退货政策（textarea）
 * 2. 退货总体情况（3行静态小表）
 * 3. 评估产品退货计提比例是否合理（两段文本）
 * 4. 重新测算产品退货金额（动态行表格）
 * 5. 检查本期产品退货情况（多级列头动态表）
 * 6. 检查期后产品退货情况（同Section 5结构）
 * + 检查内容说明 + 审计说明 + 审计结论
 *
 * 双模式：表格视图 / 在线编辑
 * OCR识别、AI辅助审计意见、统计仪表板
 */
import { ref, computed, inject, watch, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { Plus } from '@element-plus/icons-vue'

// ─── Props ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── Types ───────────────────────────────────────────────────────────
interface SummaryRow {
  category: string
  currentReturn: number
  currentRevenue: number
  currentRate: number
  priorReturn: number
  priorRevenue: number
  priorRate: number
}

interface ProvisionRow {
  id: string
  productName: string
  base: number
  rate: number
  shouldProvide: number
  alreadyProvided: number
  diff: number
  diffReason: string
}

interface ReturnCheckRow {
  id: string
  voucherDate: string
  voucherNo: string
  bizContent: string
  subjectName: string
  detailSubject: string
  debitAmount: number
  creditAmount: number
  customerName: string
  productName: string
  returnQty: string
  returnAmount: number
  returnReason: string
  hasLitigation: string
  isAbnormal: string
  indexRef: string
}

// ─── State ───────────────────────────────────────────────────────────
const policy = ref('')
const summaryRows = ref<SummaryRow[]>([
  { category: '贸易商', currentReturn: 0, currentRevenue: 0, currentRate: 0, priorReturn: 0, priorRevenue: 0, priorRate: 0 },
  { category: '终端用户', currentReturn: 0, currentRevenue: 0, currentRate: 0, priorReturn: 0, priorRevenue: 0, priorRate: 0 },
  { category: '合计', currentReturn: 0, currentRevenue: 0, currentRate: 0, priorReturn: 0, priorRevenue: 0, priorRate: 0 },
])
const assessment = ref('')
const assessmentHistory = ref('')
const provisionRows = ref<ProvisionRow[]>([])
const currentReturnRows = ref<ReturnCheckRow[]>([])
const postReturnRows = ref<ReturnCheckRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// ─── OCR ─────────────────────────────────────────────────────────────
const ocrTargetId = ref('')
const ocrTargetSection = ref<'current' | 'post'>('current')
const ocrDimension = ref<string>('voucher')
const ocrDialogVisible = ref(false)
const ocrResult = ref<Record<string, any>>({})

// ─── Auto-calc ───────────────────────────────────────────────────────
function calcSummaryRates() {
  summaryRows.value.forEach(r => {
    r.currentRate = r.currentRevenue > 0 ? r.currentReturn / r.currentRevenue : 0
    r.priorRate = r.priorRevenue > 0 ? r.priorReturn / r.priorRevenue : 0
  })
  // auto-calc 合计
  const trader = summaryRows.value[0]
  const endUser = summaryRows.value[1]
  const total = summaryRows.value[2]
  total.currentReturn = trader.currentReturn + endUser.currentReturn
  total.currentRevenue = trader.currentRevenue + endUser.currentRevenue
  total.currentRate = total.currentRevenue > 0 ? total.currentReturn / total.currentRevenue : 0
  total.priorReturn = trader.priorReturn + endUser.priorReturn
  total.priorRevenue = trader.priorRevenue + endUser.priorRevenue
  total.priorRate = total.priorRevenue > 0 ? total.priorReturn / total.priorRevenue : 0
}

function calcProvision(row: ProvisionRow) {
  row.shouldProvide = row.base * row.rate
  row.diff = row.shouldProvide - row.alreadyProvided
}

// ─── Load ────────────────────────────────────────────────────────────
function loadAll() {
  policy.value = props.allResponses.get('D4-20-policy')?.remark || ''
  const sumResp = props.allResponses.get('D4-20-summary')
  if (sumResp?.remark) { try { const p = JSON.parse(sumResp.remark); if (Array.isArray(p) && p.length === 3) summaryRows.value = p } catch { /* */ } }
  const assessResp = props.allResponses.get('D4-20-assessment')
  if (assessResp?.remark) { try { const p = JSON.parse(assessResp.remark); assessmentHistory.value = p.history || ''; assessment.value = p.evaluation || '' } catch { /* */ } }
  const provResp = props.allResponses.get('D4-20-provision')
  if (provResp?.remark) { try { const p = JSON.parse(provResp.remark); if (Array.isArray(p)) provisionRows.value = p } catch { /* */ } }
  const curResp = props.allResponses.get('D4-20-current-returns')
  if (curResp?.remark) { try { const p = JSON.parse(curResp.remark); if (Array.isArray(p)) currentReturnRows.value = p } catch { /* */ } }
  const postResp = props.allResponses.get('D4-20-post-returns')
  if (postResp?.remark) { try { const p = JSON.parse(postResp.remark); if (Array.isArray(p)) postReturnRows.value = p } catch { /* */ } }
  auditNote.value = props.allResponses.get('D4-20-note')?.remark || ''
  auditConclusion.value = props.allResponses.get('D4-20-conclusion')?.remark || ''
}

watch(() => [
  props.allResponses.get('D4-20-policy')?.remark,
  props.allResponses.get('D4-20-summary')?.remark,
  props.allResponses.get('D4-20-current-returns')?.remark,
], () => loadAll(), { immediate: true })

// ─── CRUD ────────────────────────────────────────────────────────────
function genId(): string { return `r-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}` }

function addProvisionRow() {
  if (props.isReadonly) return
  provisionRows.value.push({ id: genId(), productName: '', base: 0, rate: 0, shouldProvide: 0, alreadyProvided: 0, diff: 0, diffReason: '' })
  persistAll()
}
function removeProvisionRow(id: string) { if (props.isReadonly) return; provisionRows.value = provisionRows.value.filter(r => r.id !== id); persistAll() }

function addReturnRow(section: 'current' | 'post') {
  if (props.isReadonly) return
  const newRow: ReturnCheckRow = { id: genId(), voucherDate: '', voucherNo: '', bizContent: '', subjectName: '', detailSubject: '', debitAmount: 0, creditAmount: 0, customerName: '', productName: '', returnQty: '', returnAmount: 0, returnReason: '', hasLitigation: '', isAbnormal: '', indexRef: '' }
  if (section === 'current') currentReturnRows.value.push(newRow)
  else postReturnRows.value.push(newRow)
  persistAll()
}
function removeReturnRow(section: 'current' | 'post', id: string) {
  if (props.isReadonly) return
  if (section === 'current') currentReturnRows.value = currentReturnRows.value.filter(r => r.id !== id)
  else postReturnRows.value = postReturnRows.value.filter(r => r.id !== id)
  persistAll()
}

function onProvisionCellChange(row: ProvisionRow) { calcProvision(row); persistAll() }
function onSummaryChange() { calcSummaryRates(); persistAll() }

// ─── OCR handlers ────────────────────────────────────────────────────
async function handleOcrUpload(section: 'current' | 'post', rowId: string, file: File) {
  ocrTargetId.value = rowId
  ocrTargetSection.value = section
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData, { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any)
    const fields = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) { ElMessage.info('OCR完成，未识别到可填充字段'); return }
    ocrResult.value = fields
    ocrDimension.value = 'voucher'
    ocrDialogVisible.value = true
  } catch { ElMessage.warning('OCR识别失败') }
}

function confirmOcrFill() {
  const rows = ocrTargetSection.value === 'current' ? currentReturnRows.value : postReturnRows.value
  const row = rows.find(r => r.id === ocrTargetId.value)
  if (!row) return
  const f = ocrResult.value
  if (ocrDimension.value === 'voucher') {
    if (f.date) row.voucherDate = String(f.date)
    if (f.number || f.voucherNo) row.voucherNo = String(f.number || f.voucherNo)
    if (f.bizContent) row.bizContent = String(f.bizContent)
    if (f.subjectName || f.accountSubject) row.subjectName = String(f.subjectName || f.accountSubject)
    if (f.detailSubject) row.detailSubject = String(f.detailSubject)
    if (f.debitAmount) row.debitAmount = Number(f.debitAmount) || 0
    if (f.creditAmount) row.creditAmount = Number(f.creditAmount) || 0
  } else {
    if (f.customerName) row.customerName = String(f.customerName)
    if (f.productName) row.productName = String(f.productName)
    if (f.quantity || f.returnQty) row.returnQty = String(f.quantity || f.returnQty)
    if (f.amount || f.returnAmount) row.returnAmount = Number(f.amount || f.returnAmount) || 0
    if (f.reason || f.returnReason) row.returnReason = String(f.reason || f.returnReason)
  }
  ocrDialogVisible.value = false
  persistAll()
  ElMessage.success('OCR结果已填入')
}

// ─── Stats ───────────────────────────────────────────────────────────
const currentReturnTotal = computed(() => currentReturnRows.value.reduce((s, r) => s + (r.returnAmount || 0), 0))
const postReturnTotal = computed(() => postReturnRows.value.reduce((s, r) => s + (r.returnAmount || 0), 0))
const returnRateDisplay = computed(() => {
  const total = summaryRows.value[2]
  return total.currentRate > 0 ? (total.currentRate * 100).toFixed(2) + '%' : '—'
})

// ─── Persistence ─────────────────────────────────────────────────────
function persistAll() {
  props.allResponses.set('D4-20-policy', { item_id: 'D4-20-policy', conclusion: null, remark: policy.value })
  props.allResponses.set('D4-20-summary', { item_id: 'D4-20-summary', conclusion: null, remark: JSON.stringify(summaryRows.value) })
  props.allResponses.set('D4-20-assessment', { item_id: 'D4-20-assessment', conclusion: null, remark: JSON.stringify({ history: assessmentHistory.value, evaluation: assessment.value }) })
  props.allResponses.set('D4-20-provision', { item_id: 'D4-20-provision', conclusion: null, remark: JSON.stringify(provisionRows.value) })
  props.allResponses.set('D4-20-current-returns', { item_id: 'D4-20-current-returns', conclusion: null, remark: JSON.stringify(currentReturnRows.value) })
  props.allResponses.set('D4-20-post-returns', { item_id: 'D4-20-post-returns', conclusion: null, remark: JSON.stringify(postReturnRows.value) })
  props.allResponses.set('D4-20-note', { item_id: 'D4-20-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-20-conclusion', { item_id: 'D4-20-conclusion', conclusion: null, remark: auditConclusion.value })
  debounceSave()
}
function debounceSave() { if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000) }
function flushSave() {
  const keys = ['D4-20-policy', 'D4-20-summary', 'D4-20-assessment', 'D4-20-provision', 'D4-20-current-returns', 'D4-20-post-returns', 'D4-20-note', 'D4-20-conclusion']
  window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } }))
}
function updateAuditNote(val: string) { if (props.isReadonly) return; auditNote.value = val; persistAll() }
function updateAuditConclusion(val: string) { if (props.isReadonly) return; auditConclusion.value = val; persistAll() }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })

// ─── Mode / AI / Import-Export ───────────────────────────────────────
const editorMode = ref<string>('表格视图')
const modeOptions = ['表格视图', '在线编辑']
const aiAvailable = ref(false)
async function checkAiHealth() { try { const res = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = ['healthy', 'degraded'].includes(res.data?.data?.status ?? res.data?.status) } catch { aiAvailable.value = false } }
checkAiHealth()

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
function handleExportTemplate(sheet: string) { exportTemplate(sheet as any) }
function handleExportData(sheet: string) { exportData(sheet as any) }
async function handleImportFile(sheet: string, uploadFile: any) { await importData(sheet as any, uploadFile.raw || uploadFile) }

const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)
async function genNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiNoteLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'return-analysis', existingContent: auditNote.value, relatedContext: { task: '基于销售退货检查结果，生成审计说明', currentReturnTotal: currentReturnTotal.value, postReturnTotal: postReturnTotal.value, returnRate: returnRateDisplay.value, provisionCount: provisionRows.value.length, currentRowCount: currentReturnRows.value.length, postRowCount: postReturnRows.value.length } }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    updateAuditNote(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false }
}
async function genConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiConclusionLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于销售退货检查结果生成审计结论', noteText: auditNote.value, currentReturnTotal: currentReturnTotal.value, postReturnTotal: postReturnTotal.value, returnRate: returnRateDisplay.value } }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    updateAuditConclusion(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false }
}
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

async function genSectionAi(section: 'policy' | 'history' | 'evaluation') {
  if (props.isReadonly || !aiAvailable.value) return
  const taskMap: Record<string, string> = {
    policy: '根据被审计单位行业特点，生成产品退货政策描述（包括退货条件、期限、流程）',
    history: '基于退货总体情况数据，分析历史退货趋势和主要退货原因',
    evaluation: '基于历史退货情况和行业经验，评估当前退货计提比例是否合理',
  }
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'return-analysis',
      existingContent: section === 'policy' ? policy.value : section === 'history' ? assessmentHistory.value : assessment.value,
      relatedContext: { task: taskMap[section], currentReturnTotal: currentReturnTotal.value, postReturnTotal: postReturnTotal.value, returnRate: returnRateDisplay.value, summaryData: summaryRows.value },
    }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    if (section === 'policy') policy.value = text
    else if (section === 'history') assessmentHistory.value = text
    else assessment.value = text
    persistAll()
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
}

function fmtAmount(v: number): string { if (!v) return '—'; return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function fmtRate(v: number): string { if (!v) return '—'; return (v * 100).toFixed(2) + '%' }
</script>

<template>
  <div class="d4-return">
    <!-- 工具条 -->
    <div class="toolbar">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      <div class="toolbar-right">
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item disabled class="dropdown-section-label">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportTemplate('D4-20-provision')">　重新测算表</el-dropdown-item>
              <el-dropdown-item @click="handleExportTemplate('D4-20-current')">　本期退货明细</el-dropdown-item>
              <el-dropdown-item @click="handleExportTemplate('D4-20-post')">　期后退货明细</el-dropdown-item>
              <el-dropdown-item divided disabled class="dropdown-section-label">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleExportData('D4-20-provision')">　重新测算表</el-dropdown-item>
              <el-dropdown-item @click="handleExportData('D4-20-current')">　本期退货明细</el-dropdown-item>
              <el-dropdown-item @click="handleExportData('D4-20-post')">　期后退货明细</el-dropdown-item>
              <el-dropdown-item divided disabled class="dropdown-section-label">导入数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly || importing" @change="(f: any) => handleImportFile('D4-20-provision', f)"><span>　重新测算表</span></el-upload>
              </el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly || importing" @change="(f: any) => handleImportFile('D4-20-current', f)"><span>　本期退货明细</span></el-upload>
              </el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly || importing" @change="(f: any) => handleImportFile('D4-20-post', f)"><span>　期后退货明细</span></el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-12" :context-project-id="projectId" />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-20-return')">💬 复核</el-button>
      </div>
    </div>

    <!-- 统计仪表板 -->
    <div class="stats-dashboard">
      <div class="stat-card stat-primary">
        <div class="stat-value">{{ currentReturnTotal ? fmtAmount(currentReturnTotal) : '—' }}</div>
        <div class="stat-label">本期退货总额</div>
      </div>
      <div class="stat-card stat-amount">
        <div class="stat-value">{{ postReturnTotal ? fmtAmount(postReturnTotal) : '—' }}</div>
        <div class="stat-label">期后退货总额</div>
      </div>
      <div class="stat-card stat-rate">
        <div class="stat-value">{{ returnRateDisplay }}</div>
        <div class="stat-label">退货比例</div>
      </div>
    </div>

    <template v-if="editorMode !== '在线编辑'">
      <!-- 方法论折叠 -->
      <details class="methodology-collapse">
        <summary class="methodology-summary">📖 审计目标与退货检查过程（点击展开）</summary>
        <div class="methodology-body">
          <p><strong>审计目标：</strong>确认与营业收入相关的产品退货是否已恰当记录、退货准备计提比例是否合理。</p>
          <p><strong>审计过程：</strong>了解退货政策→汇总退货总体情况→评估计提比例→重新测算退货金额→检查本期/期后退货明细→综合评价。</p>
        </div>
      </details>

      <!-- 引导条 -->
      <div class="guide-strip">
        <span class="guide-strip-label">编制流程：</span>
        <el-tooltip content="了解被审计单位的产品退货政策" placement="bottom" :show-after="300"><span class="guide-chip">①退货政策</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="汇总本年度及上年度退货总体情况" placement="bottom" :show-after="300"><span class="guide-chip">②退货总况</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="评估计提比例是否合理" placement="bottom" :show-after="300"><span class="guide-chip">③评估比例</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="重新测算产品退货金额" placement="bottom" :show-after="300"><span class="guide-chip">④重新测算</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="检查本期及期后产品退货情况" placement="bottom" :show-after="300"><span class="guide-chip">⑤退货明细</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="填写审计说明与结论" placement="bottom" :show-after="300"><span class="guide-chip">⑥审计意见</span></el-tooltip>
      </div>

      <!-- ═══ Section 1: 产品退货政策 ═══ -->
      <div class="section-block">
        <div class="section-header-row">
          <h4 class="section-title">一、产品退货政策</h4>
          <el-tooltip :content="aiTip" placement="top">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" @click="genSectionAi('policy')">🤖 AI辅助</el-button>
          </el-tooltip>
        </div>
        <el-input type="textarea" :autosize="{ minRows: 3, maxRows: 10 }" v-model="policy" :disabled="isReadonly" placeholder="描述被审计单位的产品退货政策，包括退货条件、退货期限、退货流程等" @input="persistAll()" />
      </div>

      <!-- ═══ Section 2: 退货总体情况 ═══ -->
      <div class="section-block">
        <h4 class="section-title">二、退货总体情况</h4>
        <el-table :data="summaryRows" border stripe class="summary-table" size="small">
          <el-table-column prop="category" label="分类" min-width="100" align="center">
            <template #default="{ row }"><span class="category-label">{{ row.category }}</span></template>
          </el-table-column>
          <el-table-column label="本年度" align="center" class-name="col-current">
            <el-table-column label="退货金额" min-width="120" align="right">
              <template #default="{ row, $index }">
                <el-input-number v-if="$index < 2" v-model="row.currentReturn" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="onSummaryChange" />
                <span v-else class="auto-calc" title="自动合计">{{ fmtAmount(row.currentReturn) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="收入金额" min-width="120" align="right">
              <template #default="{ row, $index }">
                <el-input-number v-if="$index < 2" v-model="row.currentRevenue" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="onSummaryChange" />
                <span v-else class="auto-calc" title="自动合计">{{ fmtAmount(row.currentRevenue) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="比例" min-width="80" align="right">
              <template #default="{ row }"><span class="auto-calc" title="退货金额÷收入金额">{{ fmtRate(row.currentRate) }}</span></template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="上年度" align="center" class-name="col-prior">
            <el-table-column label="退货金额" min-width="120" align="right">
              <template #default="{ row, $index }">
                <el-input-number v-if="$index < 2" v-model="row.priorReturn" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="onSummaryChange" />
                <span v-else class="auto-calc" title="自动合计">{{ fmtAmount(row.priorReturn) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="收入金额" min-width="120" align="right">
              <template #default="{ row, $index }">
                <el-input-number v-if="$index < 2" v-model="row.priorRevenue" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="onSummaryChange" />
                <span v-else class="auto-calc" title="自动合计">{{ fmtAmount(row.priorRevenue) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="比例" min-width="80" align="right">
              <template #default="{ row }"><span class="auto-calc" title="退货金额÷收入金额">{{ fmtRate(row.priorRate) }}</span></template>
            </el-table-column>
          </el-table-column>
        </el-table>
      </div>

      <!-- ═══ Section 3: 评估产品退货计提比例是否合理 ═══ -->
      <div class="section-block">
        <h4 class="section-title">三、评估产品退货计提比例是否合理</h4>
        <div class="assessment-sub">
          <div class="sub-label-row">
            <label class="sub-label">(1) 历史退货情况</label>
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" @click="genSectionAi('history')">🤖 AI辅助</el-button>
            </el-tooltip>
          </div>
          <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" v-model="assessmentHistory" :disabled="isReadonly" placeholder="描述历史退货情况、退货趋势分析" @input="persistAll()" />
        </div>
        <div class="assessment-sub">
          <div class="sub-label-row">
            <label class="sub-label">(2) 综合评估结论</label>
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" @click="genSectionAi('evaluation')">🤖 AI辅助</el-button>
            </el-tooltip>
          </div>
          <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" v-model="assessment" :disabled="isReadonly" placeholder="综合评估退货计提比例是否合理，是否需要调整" @input="persistAll()" />
        </div>
      </div>

      <!-- ═══ Section 4: 重新测算产品退货金额 ═══ -->
      <div class="section-block">
        <h4 class="section-title">四、重新测算产品退货金额</h4>
        <el-table :data="provisionRows" border stripe class="provision-table" size="small">
          <el-table-column label="序号" width="55" align="center">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column label="产品名称" min-width="120">
            <template #default="{ row }"><el-input v-model="row.productName" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="计提基数" min-width="120" align="right">
            <template #default="{ row }"><el-input-number v-model="row.base" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="onProvisionCellChange(row)" /></template>
          </el-table-column>
          <el-table-column label="计提比例" min-width="90" align="right">
            <template #default="{ row }"><el-input-number v-model="row.rate" size="small" :controls="false" :disabled="isReadonly" :precision="4" :step="0.01" style="width:100%" @change="onProvisionCellChange(row)" /></template>
          </el-table-column>
          <el-table-column label="应计提金额" min-width="120" align="right">
            <template #default="{ row }"><span class="auto-calc" title="计提基数 × 计提比例">{{ fmtAmount(row.shouldProvide) }}</span></template>
          </el-table-column>
          <el-table-column label="账面已计提金额" min-width="130" align="right">
            <template #default="{ row }"><el-input-number v-model="row.alreadyProvided" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="onProvisionCellChange(row)" /></template>
          </el-table-column>
          <el-table-column label="差异金额" min-width="110" align="right">
            <template #default="{ row }"><span class="auto-calc" :class="{ 'diff-warn': row.diff !== 0 }" title="应计提 - 已计提">{{ fmtAmount(row.diff) }}</span></template>
          </el-table-column>
          <el-table-column label="差异原因" min-width="140">
            <template #default="{ row }"><el-input v-model="row.diffReason" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="操作" width="70" align="center">
            <template #default="{ row }">
              <el-popconfirm title="确认删除？" @confirm="removeProvisionRow(row.id)">
                <template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
        <div class="add-row-bar">
          <el-button :disabled="isReadonly" size="small" @click="addProvisionRow"><el-icon :size="14" style="margin-right:4px;"><Plus /></el-icon>添加产品</el-button>
        </div>
      </div>

      <!-- ═══ Section 5: 检查本期产品退货情况 ═══ -->
      <div class="section-block">
        <h4 class="section-title">五、检查本期产品退货情况</h4>
        <el-table :data="currentReturnRows" border stripe class="return-check-table" size="small">
          <el-table-column label="序号" width="50" align="center" fixed>
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <!-- 记账凭证 -->
          <el-table-column label="记账凭证" align="center" class-name="col-voucher">
            <el-table-column label="日期" min-width="100">
              <template #default="{ row }"><el-input v-model="row.voucherDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="编号" min-width="90">
              <template #default="{ row }"><el-input v-model="row.voucherNo" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="业务内容" min-width="110">
              <template #default="{ row }"><el-input v-model="row.bizContent" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="科目名称" min-width="100">
              <template #default="{ row }"><el-input v-model="row.subjectName" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="二级明细" min-width="100">
              <template #default="{ row }"><el-input v-model="row.detailSubject" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="借方金额" min-width="110" align="right">
              <template #default="{ row }"><el-input-number v-model="row.debitAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="贷方金额" min-width="110" align="right">
              <template #default="{ row }"><el-input-number v-model="row.creditAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="persistAll()" /></template>
            </el-table-column>
          </el-table-column>
          <!-- 退货单 -->
          <el-table-column label="退货单" align="center" class-name="col-return">
            <el-table-column label="客户名称" min-width="110">
              <template #default="{ row }"><el-input v-model="row.customerName" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="产品名称" min-width="100">
              <template #default="{ row }"><el-input v-model="row.productName" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="退货数量" min-width="80">
              <template #default="{ row }"><el-input v-model="row.returnQty" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="退货金额" min-width="110" align="right">
              <template #default="{ row }"><el-input-number v-model="row.returnAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="退货原因" min-width="110">
              <template #default="{ row }"><el-input v-model="row.returnReason" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
          </el-table-column>
          <!-- 判断列 -->
          <el-table-column label="是否涉及诉讼" min-width="90" align="center">
            <template #default="{ row }"><el-input v-model="row.hasLitigation" size="small" :disabled="isReadonly" placeholder="是/否" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="是否异常" min-width="80" align="center">
            <template #default="{ row }"><el-input v-model="row.isAbnormal" size="small" :disabled="isReadonly" placeholder="是/否" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="索引号" min-width="80">
            <template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
          <!-- 操作 -->
          <el-table-column label="操作" width="100" fixed="right" align="center">
            <template #default="{ row }">
              <el-upload :show-file-list="false" :auto-upload="false" :disabled="isReadonly"
                @change="(f: any) => handleOcrUpload('current', row.id, f.raw || f)" style="display:inline-block;">
                <el-button link size="small" :disabled="isReadonly" title="OCR识别附件">📎</el-button>
              </el-upload>
              <el-popconfirm title="确认删除？" @confirm="removeReturnRow('current', row.id)">
                <template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
        <div class="add-row-bar">
          <el-button :disabled="isReadonly" size="small" @click="addReturnRow('current')"><el-icon :size="14" style="margin-right:4px;"><Plus /></el-icon>添加行</el-button>
        </div>
      </div>

      <!-- ═══ Section 6: 检查期后产品退货情况 ═══ -->
      <div class="section-block">
        <h4 class="section-title">六、检查期后产品退货情况</h4>
        <el-table :data="postReturnRows" border stripe class="return-check-table" size="small">
          <el-table-column label="序号" width="50" align="center" fixed>
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <!-- 记账凭证 -->
          <el-table-column label="记账凭证" align="center" class-name="col-voucher">
            <el-table-column label="日期" min-width="100">
              <template #default="{ row }"><el-input v-model="row.voucherDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="编号" min-width="90">
              <template #default="{ row }"><el-input v-model="row.voucherNo" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="业务内容" min-width="110">
              <template #default="{ row }"><el-input v-model="row.bizContent" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="科目名称" min-width="100">
              <template #default="{ row }"><el-input v-model="row.subjectName" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="二级明细" min-width="100">
              <template #default="{ row }"><el-input v-model="row.detailSubject" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="借方金额" min-width="110" align="right">
              <template #default="{ row }"><el-input-number v-model="row.debitAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="贷方金额" min-width="110" align="right">
              <template #default="{ row }"><el-input-number v-model="row.creditAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="persistAll()" /></template>
            </el-table-column>
          </el-table-column>
          <!-- 退货单 -->
          <el-table-column label="退货单" align="center" class-name="col-return">
            <el-table-column label="客户名称" min-width="110">
              <template #default="{ row }"><el-input v-model="row.customerName" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="产品名称" min-width="100">
              <template #default="{ row }"><el-input v-model="row.productName" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="退货数量" min-width="80">
              <template #default="{ row }"><el-input v-model="row.returnQty" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="退货金额" min-width="110" align="right">
              <template #default="{ row }"><el-input-number v-model="row.returnAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="persistAll()" /></template>
            </el-table-column>
            <el-table-column label="退货原因" min-width="110">
              <template #default="{ row }"><el-input v-model="row.returnReason" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
            </el-table-column>
          </el-table-column>
          <!-- 判断列 -->
          <el-table-column label="是否涉及诉讼" min-width="90" align="center">
            <template #default="{ row }"><el-input v-model="row.hasLitigation" size="small" :disabled="isReadonly" placeholder="是/否" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="是否异常" min-width="80" align="center">
            <template #default="{ row }"><el-input v-model="row.isAbnormal" size="small" :disabled="isReadonly" placeholder="是/否" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="索引号" min-width="80">
            <template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
          <!-- 操作 -->
          <el-table-column label="操作" width="100" fixed="right" align="center">
            <template #default="{ row }">
              <el-upload :show-file-list="false" :auto-upload="false" :disabled="isReadonly"
                @change="(f: any) => handleOcrUpload('post', row.id, f.raw || f)" style="display:inline-block;">
                <el-button link size="small" :disabled="isReadonly" title="OCR识别附件">📎</el-button>
              </el-upload>
              <el-popconfirm title="确认删除？" @confirm="removeReturnRow('post', row.id)">
                <template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
        <div class="add-row-bar">
          <el-button :disabled="isReadonly" size="small" @click="addReturnRow('post')"><el-icon :size="14" style="margin-right:4px;"><Plus /></el-icon>添加行</el-button>
        </div>
      </div>

      <!-- 审计意见区 -->
      <el-card class="audit-opinion-card" shadow="never">
        <template #header>
          <div class="opinion-header">
            <span class="opinion-title">审计意见区</span>
            <div class="opinion-actions">
              <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly || !aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip>
              <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly || !aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip>
            </div>
          </div>
        </template>
        <div class="opinion-body">
          <div class="opinion-field"><label>审计说明</label><el-input type="textarea" :autosize="{ minRows: 3, maxRows: 12 }" :model-value="auditNote" :disabled="isReadonly" placeholder="记录退货检查范围、退货政策合理性评价、计提比例测算差异分析、退货原因分析等" @input="(v: string) => updateAuditNote(v)" /></div>
          <div class="opinion-field"><label>审计结论</label><el-input type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" :model-value="auditConclusion" :disabled="isReadonly" placeholder="基于退货检查结果，判断产品退货是否已恰当记录、退货准备计提是否合理" @input="(v: string) => updateAuditConclusion(v)" /></div>
        </div>
      </el-card>

      <!-- 编制提示 -->
      <details class="tips-collapse">
        <summary class="tips-summary">📋 检查内容说明</summary>
        <ol class="tips-list">
          <li>了解被审计单位的退货政策，包括退货条件、退货期限、退货流程，评估退货政策是否合理。</li>
          <li>获取本年度及上年度各类退货的总体情况，分析退货金额占收入比例的变动趋势，关注异常波动。</li>
          <li>评估产品退货计提比例是否合理，结合历史退货经验、行业水平、管理层预期进行综合判断。</li>
          <li>重新测算产品退货金额，比较应计提金额与账面已计提金额的差异，分析差异原因是否合理。</li>
          <li>检查本期及期后退货情况，关注是否存在涉及诉讼的退货、异常退货（如跨期退货、关联方退货、大额退货等）。</li>
        </ol>
      </details>
    </template>

    <!-- OnlyOffice -->
    <template v-if="editorMode === '在线编辑'">
      <div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="销售退货检查表 D4-20" :readonly="isReadonly" /></div>
    </template>

    <!-- OCR维度选择弹窗 -->
    <el-dialog v-model="ocrDialogVisible" title="OCR结果填入" width="400px" destroy-on-close>
      <p style="margin-bottom:12px;">请选择将OCR结果填入哪个维度：</p>
      <el-radio-group v-model="ocrDimension">
        <el-radio value="voucher">记账凭证</el-radio>
        <el-radio value="return">退货单</el-radio>
      </el-radio-group>
      <div style="margin-top:16px;padding:10px;background:#f5f7fa;border-radius:4px;font-size:12px;">
        <div v-for="(val, key) in ocrResult" :key="key">{{ key }}: {{ val }}</div>
      </div>
      <template #footer>
        <el-button @click="ocrDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmOcrFill">确认填入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.d4-return { padding: 16px 20px; font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px; }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.stats-dashboard { display: flex; gap: 12px; margin-bottom: 20px; padding: 14px 18px; background: linear-gradient(135deg, #f8f9fe 0%, #f0f4ff 100%); border-radius: 10px; border: 1px solid #e4e7ed; }
.stat-card { padding: 10px 16px; min-width: 130px; border-radius: 8px; background: #fff; border: 1px solid #ebeef5; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.stat-card.stat-primary { border-left: 3px solid #409eff; }
.stat-card.stat-amount { border-left: 3px solid #e6a23c; }
.stat-card.stat-rate { border-left: 3px solid #67c23a; }
.stat-value { font-size: 18px; font-weight: 700; color: #303133; font-variant-numeric: tabular-nums; }
.stat-unit { font-size: 12px; font-weight: 400; color: #909399; margin-left: 2px; }
.stat-label { font-size: 12px; color: #909399; margin-top: 2px; }
.methodology-collapse { margin-bottom: 14px; border-radius: 6px; border: 1px solid #faecd8; border-left: 3px solid #e6a23c; background: #fffbf0; }
.methodology-summary { cursor: pointer; padding: 8px 14px; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #b88230; }
.methodology-body { padding: 8px 14px 12px; font-size: 12px; color: #606266; line-height: 1.8; }
.methodology-body p { margin: 0 0 6px; }
.guide-strip { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; padding: 10px 14px; background: #f0f9eb; border-radius: 6px; border: 1px solid #e1f3d8; }
.guide-strip-label { font-weight: 600; color: #67c23a; font-size: 12px; }
.guide-chip { background: #fff; border: 1px solid #c2e7b0; border-radius: 4px; padding: 2px 8px; font-size: 12px; color: #529b2e; cursor: help; }
.guide-chip:hover { background: #f0f9eb; }
.guide-arrow { color: #a8abb2; font-size: 12px; }
.section-block { margin-bottom: 24px; }
.section-title { font-size: 14px; font-weight: 600; color: #303133; margin: 0 0 12px; padding-bottom: 6px; border-bottom: 1px solid #ebeef5; }
.section-header-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-row .section-title { margin: 0; padding-bottom: 0; border-bottom: none; }
.sub-label-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.assessment-sub { margin-bottom: 12px; }
.sub-label { display: block; font-size: 12px; color: #606266; font-weight: 500; margin-bottom: 4px; }
.category-label { font-weight: 500; color: #303133; }
.summary-table { font-size: var(--wp-font-size, 13px); }
.summary-table :deep(.el-table__cell) { padding: 6px 0; }
.summary-table :deep(.col-current .el-table__cell) { background-color: #f0f5ff !important; }
.summary-table :deep(.col-prior .el-table__cell) { background-color: #f0faf0 !important; }
.provision-table { font-size: var(--wp-font-size, 13px); }
.provision-table :deep(.el-table__cell) { padding: 6px 0; }
.return-check-table { font-size: var(--wp-font-size, 13px); }
.return-check-table :deep(.el-table__cell) { padding: 6px 0; }
.return-check-table :deep(.col-voucher .el-table__cell) { background-color: #f0f5ff !important; }
.return-check-table :deep(.col-return .el-table__cell) { background-color: #f0faf0 !important; }
.auto-calc { color: #909399; font-style: italic; border-bottom: 1px dashed #c0c4cc; cursor: help; }
.diff-warn { color: #f56c6c; font-weight: 600; }
.add-row-bar { margin: 10px 0 0; text-align: center; }
.audit-opinion-card { margin-bottom: 20px; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 8px; }
.opinion-body { display: flex; flex-direction: column; gap: 14px; }
.opinion-field label { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.tips-collapse { margin-bottom: 16px; border-radius: 6px; border: 1px solid #fde2e2; border-left: 3px solid #f56c6c; }
.tips-summary { cursor: pointer; padding: 8px 14px; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #f56c6c; }
.tips-list { margin: 8px 14px 12px; padding-left: 18px; font-size: 12px; color: #606266; line-height: 2; }
.oo-container { min-height: 600px; height: calc(100vh - 280px); border-radius: 8px; overflow: hidden; }
.dropdown-section-label { font-size: 12px !important; color: #909399 !important; font-weight: 500; }
</style>
