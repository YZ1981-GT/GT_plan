<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * D4TabCutoffForward — D4-17 营业收入截止测试（账到单据）
 *
 * 从记账凭证→发货单方向检查期末收入是否记入恰当期间
 * 双模式：表格视图 / 在线编辑
 * 自动跨期判断、统计仪表板、AI辅助审计意见
 */
import { ref, computed, inject, watch, onBeforeUnmount, defineAsyncComponent, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { Plus } from '@element-plus/icons-vue'
import type { ExtractedVoucher, FillMode } from '../../composables/useCutoffAutoSampling'
import { D4_MAIN_REVENUE_STANDARD } from '../../composables/d4AccountScope'

const GtCutoffAutoSampling = defineAsyncComponent(() => import('../../cutoff/GtCutoffAutoSampling.vue'))

// ─── Props ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// 审计年度（主入口 provide('d4AuditYear')），回退"当前年-1"
const auditYear = inject<Ref<number> | null>('d4AuditYear', null)
const samplingYear = computed<number>(() => auditYear?.value ?? new Date().getFullYear() - 1)

// ─── Types ───────────────────────────────────────────────────────────
interface CutoffForwardRow {
  id: string
  voucherDate: string
  voucherNo: string
  voucherProduct: string
  voucherQty: string
  voucherAmount: number
  deliveryDate: string
  deliveryNo: string
  deliveryProduct: string
  deliveryQty: string
  deliveryAmount: number
  isCutoff: boolean | null
  remark: string
}

// ─── State ───────────────────────────────────────────────────────────
const rows = ref<CutoffForwardRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')
const cutoffDate = ref('2025-12-31')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// ─── OCR ─────────────────────────────────────────────────────────────
const ocrTargetId = ref('')
const ocrDimension = ref<string>('voucher')
const ocrDialogVisible = ref(false)
const ocrResult = ref<Record<string, any>>({})

// ─── Auto cutoff check ───────────────────────────────────────────────
function checkCutoff(row: CutoffForwardRow): boolean | null {
  if (!row.voucherDate || !row.deliveryDate) return null
  // D4-17: voucher in period, delivery after period → cutoff issue (×)
  return !(row.voucherDate <= cutoffDate.value && row.deliveryDate > cutoffDate.value)
}

function recalcAll() {
  rows.value.forEach(r => { r.isCutoff = checkCutoff(r) })
}

// ─── Load ────────────────────────────────────────────────────────────
function loadData() {
  const resp = props.allResponses.get('D4-17-rows')
  if (resp?.remark) {
    try { const parsed = JSON.parse(resp.remark); if (Array.isArray(parsed) && parsed.length) { rows.value = parsed; recalcAll(); return } } catch { /* */ }
  }
  rows.value = []
}
function loadNoteConclusion() {
  auditNote.value = props.allResponses.get('D4-17-note')?.remark || ''
  auditConclusion.value = props.allResponses.get('D4-17-conclusion')?.remark || ''
}

watch(() => props.allResponses.get('D4-17-rows')?.remark, () => loadData(), { immediate: true })
watch(() => props.allResponses.get('D4-17-note')?.remark, () => loadNoteConclusion(), { immediate: true })

// ─── CRUD ────────────────────────────────────────────────────────────
function addRow() {
  if (props.isReadonly) return
  rows.value.push({ id: `r-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`, voucherDate: '', voucherNo: '', voucherProduct: '', voucherQty: '', voucherAmount: 0, deliveryDate: '', deliveryNo: '', deliveryProduct: '', deliveryQty: '', deliveryAmount: 0, isCutoff: null, remark: '' })
  persistAll()
}
function removeRow(id: string) { if (props.isReadonly) return; rows.value = rows.value.filter(r => r.id !== id); persistAll() }
function onCellChange(row: CutoffForwardRow) { row.isCutoff = checkCutoff(row); persistAll() }

// ─── OCR handlers ────────────────────────────────────────────────────
async function handleOcrUpload(rowId: string, file: File) {
  ocrTargetId.value = rowId
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
  const row = rows.value.find(r => r.id === ocrTargetId.value)
  if (!row) return
  const fields = ocrResult.value
  if (ocrDimension.value === 'voucher') {
    if (fields.date) row.voucherDate = String(fields.date)
    if (fields.number) row.voucherNo = String(fields.number)
    if (fields.productName) row.voucherProduct = String(fields.productName)
    if (fields.quantity) row.voucherQty = String(fields.quantity)
    if (fields.amount) row.voucherAmount = Number(fields.amount) || 0
  } else {
    if (fields.date) row.deliveryDate = String(fields.date)
    if (fields.number) row.deliveryNo = String(fields.number)
    if (fields.productName) row.deliveryProduct = String(fields.productName)
    if (fields.quantity) row.deliveryQty = String(fields.quantity)
    if (fields.amount) row.deliveryAmount = Number(fields.amount) || 0
  }
  row.isCutoff = checkCutoff(row)
  ocrDialogVisible.value = false
  persistAll()
  ElMessage.success('OCR结果已填入')
}

// ─── Cutoff auto-sampling（useCutoffAutoSampling / GtCutoffAutoSampling，科目6001）─
const showCutoffPanel = ref(false)
// 面板默认条件：绑定本表截止日期（v-if 切换重挂时读取最新值）
const cutoffPanelDefaults = computed(() => ({ cutoffDate: cutoffDate.value }))

/** ExtractedVoucher → D4-17 行（账到单据：序时账凭证映射到记账凭证侧，发货单侧留待审计师追查） */
function extractedToRow(v: ExtractedVoucher): CutoffForwardRow {
  const amt = v.creditAmount ? parseFloat(v.creditAmount) : (v.debitAmount ? parseFloat(v.debitAmount) : 0)
  return {
    id: `r-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    voucherDate: v.voucherDate || '',
    voucherNo: v.voucherNo || '',
    voucherProduct: v.summary || '',
    voucherQty: '',
    voucherAmount: Number.isFinite(amt) ? amt : 0,
    deliveryDate: '', deliveryNo: '', deliveryProduct: '', deliveryQty: '', deliveryAmount: 0,
    isCutoff: null,
    remark: v.cutoffStatus === '可能跨期' ? '跨期疑点' : (v.remark || ''),
  }
}

/** 一键取数回写：按 fillMode 合并到 rows 并持久化（复用组件既有 persistAll） */
function handleCutoffFilled(payload: { samples: ExtractedVoucher[]; fillMode: FillMode }) {
  if (props.isReadonly) return
  const mapped = payload.samples.map(extractedToRow)
  if (payload.fillMode === 'replace') {
    rows.value = mapped
  } else if (payload.fillMode === 'merge') {
    const existingNos = new Set(rows.value.map(r => r.voucherNo).filter(Boolean))
    rows.value = [...rows.value, ...mapped.filter(r => !r.voucherNo || !existingNos.has(r.voucherNo))]
  } else {
    rows.value = [...rows.value, ...mapped]
  }
  recalcAll()
  showCutoffPanel.value = false
  persistAll()
  ElMessage.success(`已填入 ${mapped.length} 笔凭证`)
}

/** AI 复核意见回填审计说明 */
function onCutoffReviewApplied(text: string) {
  if (props.isReadonly || !text) return
  updateAuditNote(auditNote.value ? `${auditNote.value}\n${text}` : text)
}

// ─── Stats ───────────────────────────────────────────────────────────
const totalRows = computed(() => rows.value.length)
const cutoffIssues = computed(() => rows.value.filter(r => r.isCutoff === false).length)
const totalAmount = computed(() => rows.value.reduce((s, r) => s + (r.voucherAmount || 0), 0))

// ─── Persistence ─────────────────────────────────────────────────────
function persistAll() {
  props.allResponses.set('D4-17-rows', { item_id: 'D4-17-rows', conclusion: null, remark: JSON.stringify(rows.value) })
  props.allResponses.set('D4-17-note', { item_id: 'D4-17-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-17-conclusion', { item_id: 'D4-17-conclusion', conclusion: null, remark: auditConclusion.value })
  debounceSave()
}
function debounceSave() { if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000) }
function flushSave() {
  const keys = ['D4-17-rows', 'D4-17-note', 'D4-17-conclusion']
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
function handleExportTemplate() { exportTemplate('D4-17') }
function handleExportData() { exportData('D4-17') }
async function handleImportFile(uploadFile: any) { await importData('D4-17', uploadFile.raw || uploadFile) }

const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)
async function genNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiNoteLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-note', existingContent: auditNote.value, relatedContext: { task: '基于截止测试（账到单据）结果，生成审计说明', totalRows: totalRows.value, cutoffIssues: cutoffIssues.value, totalAmount: totalAmount.value, cutoffDate: cutoffDate.value } }, { _silent: true } as any)
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
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于截止测试（账到单据）结果生成审计结论', noteText: auditNote.value, cutoffIssues: cutoffIssues.value, totalRows: totalRows.value } }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    updateAuditConclusion(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false }
}
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

function rowClassName({ row }: { row: any }) { return row.isCutoff === false ? 'row-cutoff-issue' : '' }
</script>

<template>
  <div class="d4-cutoff-forward">
    <!-- 工具条 -->
    <div class="toolbar">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      <div class="toolbar-right">
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly || importing" @change="handleImportFile"><span>导入数据</span></el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-14" :context-project-id="projectId" />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-17-cutoff')">💬 复核</el-button>
      </div>
    </div>

    <!-- 统计仪表板 -->
    <div class="stats-dashboard">
      <div class="stat-card stat-primary">
        <div class="stat-value">{{ totalRows }}<span class="stat-unit">笔</span></div>
        <div class="stat-label">检查样本数</div>
      </div>
      <div class="stat-card" :class="{ 'stat-warn': cutoffIssues > 0 }">
        <div class="stat-value">{{ cutoffIssues }}<span class="stat-unit">笔</span></div>
        <div class="stat-label">跨期问题</div>
      </div>
      <div class="stat-card stat-amount">
        <div class="stat-value">{{ totalAmount ? (totalAmount / 10000).toFixed(2) : '—' }}<span class="stat-unit">万元</span></div>
        <div class="stat-label">检查金额</div>
      </div>
    </div>

    <template v-if="editorMode !== '在线编辑'">
      <!-- 方法论折叠 -->
      <details class="methodology-collapse">
        <summary class="methodology-summary">📖 审计目标与截止测试过程（点击展开）</summary>
        <div class="methodology-body">
          <p><strong>审计目标：</strong>确认与营业收入有关事项已记录于正确的会计期间。</p>
          <p><strong>审计过程：</strong>获取报表日前后一定天数、且金额大于设定阈值的收入记账凭证，与发货单核对确认收入是否记入了恰当的期间。</p>
        </div>
      </details>

      <!-- 引导条 -->
      <div class="guide-strip">
        <span class="guide-strip-label">编制流程：</span>
        <el-tooltip content="设定截止日期（通常为资产负债表日）" placement="bottom" :show-after="300"><span class="guide-chip">①设定截止日期</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="从收入明细账中选取期末附近的记账凭证" placement="bottom" :show-after="300"><span class="guide-chip">②选取期末凭证</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="根据记账凭证追查对应的发货单信息" placement="bottom" :show-after="300"><span class="guide-chip">③追查发货单</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="比较凭证日期与发货日期判断是否跨期" placement="bottom" :show-after="300"><span class="guide-chip">④判断跨期</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="填写审计说明与结论" placement="bottom" :show-after="300"><span class="guide-chip">⑤填审计意见</span></el-tooltip>
      </div>

      <!-- 截止日期 -->
      <div class="cutoff-date-bar">
        <label>截止日期：</label>
        <el-input v-model="cutoffDate" size="small" style="width:160px;" placeholder="YYYY-MM-DD" :disabled="isReadonly" @change="recalcAll(); persistAll()" />
        <el-button size="small" type="success" plain :disabled="isReadonly" @click="showCutoffPanel = !showCutoffPanel">
          {{ showCutoffPanel ? '收起取数面板' : '从序时账一键取数' }}
        </el-button>
      </div>

      <!-- 自动取数面板（科目6001，基准日±N天窗口一键取凭证并标注跨期） -->
      <GtCutoffAutoSampling
        v-if="showCutoffPanel"
        :key="`d4-17-${cutoffDate}`"
        :account-code="D4_MAIN_REVENUE_STANDARD"
        cutoff-direction="window"
        :default-conditions="cutoffPanelDefaults"
        :workpaper-id="wpId"
        :project-id="projectId"
        :year="samplingYear"
        :readonly="isReadonly"
        @filled="handleCutoffFilled"
        @applied="onCutoffReviewApplied"
      />

      <!-- 主表格 -->
      <el-table :data="rows" border stripe class="cutoff-table" :row-class-name="rowClassName">
        <el-table-column label="序号" width="55" align="center" fixed>
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>

        <!-- 记账凭证 -->
        <el-table-column label="记账凭证" align="center" class-name="col-voucher">
          <el-table-column label="日期" min-width="105">
            <template #default="{ row }"><el-input v-model="row.voucherDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="onCellChange(row)" /></template>
          </el-table-column>
          <el-table-column label="编号" min-width="100">
            <template #default="{ row }"><el-input v-model="row.voucherNo" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="品名" min-width="110">
            <template #default="{ row }"><el-input v-model="row.voucherProduct" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="数量" min-width="80">
            <template #default="{ row }"><el-input v-model="row.voucherQty" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="金额" min-width="110" align="right">
            <template #default="{ row }"><WpAmountInput v-model="row.voucherAmount" size="small" :disabled="isReadonly" style="width:100%" @change="onCellChange(row)" /></template>
          </el-table-column>
        </el-table-column>

        <!-- 发货单 -->
        <el-table-column label="发货单" align="center" class-name="col-delivery">
          <el-table-column label="日期" min-width="105">
            <template #default="{ row }"><el-input v-model="row.deliveryDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="onCellChange(row)" /></template>
          </el-table-column>
          <el-table-column label="编号" min-width="100">
            <template #default="{ row }"><el-input v-model="row.deliveryNo" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="品名" min-width="110">
            <template #default="{ row }"><el-input v-model="row.deliveryProduct" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="数量" min-width="80">
            <template #default="{ row }"><el-input v-model="row.deliveryQty" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="金额" min-width="110" align="right">
            <template #default="{ row }"><WpAmountInput v-model="row.deliveryAmount" size="small" :disabled="isReadonly" style="width:100%" @change="persistAll()" /></template>
          </el-table-column>
        </el-table-column>

        <!-- 是否跨期 -->
        <el-table-column label="跨期" width="60" align="center">
          <template #default="{ row }">
            <span v-if="row.isCutoff === true" class="cutoff-ok">√</span>
            <span v-else-if="row.isCutoff === false" class="cutoff-issue">×</span>
            <span v-else class="cutoff-na">—</span>
          </template>
        </el-table-column>

        <!-- 备注 -->
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }"><el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
        </el-table-column>

        <!-- 操作 -->
        <el-table-column label="操作" width="100" fixed="right" align="center">
          <template #default="{ row }">
            <el-upload :show-file-list="false" :auto-upload="false" :disabled="isReadonly"
              @change="(f: any) => handleOcrUpload(row.id, f.raw || f)" style="display:inline-block;">
              <el-button link size="small" :disabled="isReadonly" title="OCR识别附件">📎</el-button>
            </el-upload>
            <el-popconfirm title="确认删除？" @confirm="removeRow(row.id)">
              <template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div class="add-row-bar">
        <el-button :disabled="isReadonly" @click="addRow"><el-icon :size="16" style="margin-right:4px;"><Plus /></el-icon>添加行</el-button>
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
          <div class="opinion-field"><label>审计说明</label><el-input type="textarea" :autosize="{ minRows: 3, maxRows: 12 }" :model-value="auditNote" :disabled="isReadonly" placeholder="记录截止测试选样依据、检查范围、跨期问题描述及处理" @input="(v: string) => updateAuditNote(v)" /></div>
          <div class="opinion-field"><label>审计结论</label><el-input type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" :model-value="auditConclusion" :disabled="isReadonly" placeholder="基于截止测试结果，判断营业收入截止认定是否满足审计目标" @input="(v: string) => updateAuditConclusion(v)" /></div>
        </div>
      </el-card>

      <!-- 编制提示 -->
      <details class="tips-collapse">
        <summary class="tips-summary">📋 编制提示</summary>
        <ol class="tips-list">
          <li>本表适用于对"以发货单为确认收入时点"的被审计单位的截止测试（账到单据方向）。如被审计单位以验收单或签收单为收入确认时点，应以相应单据为检查对象。</li>
          <li>如果存在跨期舞弊风险或者所检查样本中发现有跨期的，应扩大测试期间和样本量，将检查结果与D4-18（单据到账方向）综合评价。</li>
        </ol>
      </details>
    </template>

    <!-- OnlyOffice -->
    <template v-if="editorMode === '在线编辑'">
      <div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="营业收入截止测试（账到单据）D4-17" :readonly="isReadonly" /></div>
    </template>

    <!-- OCR维度选择弹窗 -->
    <el-dialog v-model="ocrDialogVisible" title="OCR结果填入" width="400px" destroy-on-close>
      <p style="margin-bottom:12px;">请选择将OCR结果填入哪个维度：</p>
      <el-radio-group v-model="ocrDimension">
        <el-radio value="voucher">记账凭证</el-radio>
        <el-radio value="delivery">发货单</el-radio>
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
.d4-cutoff-forward { padding: 16px 20px; font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px; }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.stats-dashboard { display: flex; gap: 12px; margin-bottom: 20px; padding: 14px 18px; background: linear-gradient(135deg, #f8f9fe 0%, #f0f4ff 100%); border-radius: 10px; border: 1px solid #e4e7ed; }
.stat-card { padding: 10px 16px; min-width: 120px; border-radius: 8px; background: #fff; border: 1px solid #ebeef5; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.stat-card.stat-primary { border-left: 3px solid #409eff; }
.stat-card.stat-warn { border-left: 3px solid #f56c6c; }
.stat-card.stat-amount { border-left: 3px solid #67c23a; }
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
.cutoff-date-bar { margin-bottom: 14px; display: flex; align-items: center; gap: 8px; font-size: var(--wp-font-size, 13px); color: #606266; }
.cutoff-date-bar label { font-weight: 500; }
.cutoff-table { font-size: var(--wp-font-size, 13px); }
.cutoff-table :deep(.el-table__cell) { padding: 6px 0; }
.cutoff-table :deep(.col-voucher .el-table__cell) { background-color: #f0f5ff !important; }
.cutoff-table :deep(.col-delivery .el-table__cell) { background-color: #f0faf0 !important; }
.cutoff-table :deep(.row-cutoff-issue td) { border-left: 3px solid #f56c6c; }
.cutoff-ok { color: #67c23a; font-weight: 700; font-size: 16px; }
.cutoff-issue { color: #f56c6c; font-weight: 700; font-size: 16px; }
.cutoff-na { color: #c0c4cc; font-size: 14px; }
.add-row-bar { margin: 12px 0 20px; text-align: center; }
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
</style>
