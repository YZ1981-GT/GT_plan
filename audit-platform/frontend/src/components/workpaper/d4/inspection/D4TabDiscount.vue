<script setup lang="ts">
/**
 * D4TabDiscount — D4-19 销售折扣与折让检查
 *
 * 检查与营业收入有关的折扣是否已恰当记录、相关披露是否正确
 * 双模式：表格视图 / 在线编辑
 * 自动计算折扣比例、OCR识别、AI辅助审计意见
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
interface DiscountRow {
  id: string
  customerName: string
  discountType: string
  revenueAmount: number
  discountAmount: number
  discountRate: number
  reason: string
  voucherDate: string
  voucherNo: string
  accountSubject: string
  detailSubject: string
  debitAmount: number
  creditAmount: number
  approvalDate: string
  approver: string
  remark: string
}

// ─── State ───────────────────────────────────────────────────────────
const rows = ref<DiscountRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// ─── OCR ─────────────────────────────────────────────────────────────
const ocrTargetId = ref('')
const ocrDimension = ref<string>('basic')
const ocrDialogVisible = ref(false)
const ocrResult = ref<Record<string, any>>({})

// ─── Auto-calc discount rate ─────────────────────────────────────────
function calcRate(row: DiscountRow) {
  row.discountRate = (row.revenueAmount > 0 && row.discountAmount > 0) ? row.discountAmount / row.revenueAmount : 0
}

// ─── Load ────────────────────────────────────────────────────────────
function loadData() {
  const resp = props.allResponses.get('D4-19-rows')
  if (resp?.remark) {
    try { const parsed = JSON.parse(resp.remark); if (Array.isArray(parsed) && parsed.length) { rows.value = parsed; return } } catch { /* */ }
  }
  rows.value = []
}
function loadNoteConclusion() {
  auditNote.value = props.allResponses.get('D4-19-note')?.remark || ''
  auditConclusion.value = props.allResponses.get('D4-19-conclusion')?.remark || ''
}

watch(() => props.allResponses.get('D4-19-rows')?.remark, () => loadData(), { immediate: true })
watch(() => props.allResponses.get('D4-19-note')?.remark, () => loadNoteConclusion(), { immediate: true })

// ─── CRUD ────────────────────────────────────────────────────────────
function addRow() {
  if (props.isReadonly) return
  rows.value.push({ id: `r-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`, customerName: '', discountType: '', revenueAmount: 0, discountAmount: 0, discountRate: 0, reason: '', voucherDate: '', voucherNo: '', accountSubject: '', detailSubject: '', debitAmount: 0, creditAmount: 0, approvalDate: '', approver: '', remark: '' })
  persistAll()
}
function removeRow(id: string) { if (props.isReadonly) return; rows.value = rows.value.filter(r => r.id !== id); persistAll() }
function onCellChange(row: DiscountRow) { calcRate(row); persistAll() }

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
    ocrDimension.value = 'basic'
    ocrDialogVisible.value = true
  } catch { ElMessage.warning('OCR识别失败') }
}

function confirmOcrFill() {
  const row = rows.value.find(r => r.id === ocrTargetId.value)
  if (!row) return
  const f = ocrResult.value
  if (ocrDimension.value === 'basic') {
    if (f.customerName) row.customerName = String(f.customerName)
    if (f.discountType) row.discountType = String(f.discountType)
    if (f.amount || f.revenueAmount) row.revenueAmount = Number(f.amount || f.revenueAmount) || 0
    if (f.discountAmount) row.discountAmount = Number(f.discountAmount) || 0
    if (f.reason) row.reason = String(f.reason)
  } else if (ocrDimension.value === 'voucher') {
    if (f.date) row.voucherDate = String(f.date)
    if (f.number || f.voucherNo) row.voucherNo = String(f.number || f.voucherNo)
    if (f.accountSubject) row.accountSubject = String(f.accountSubject)
    if (f.detailSubject) row.detailSubject = String(f.detailSubject)
    if (f.debitAmount) row.debitAmount = Number(f.debitAmount) || 0
    if (f.creditAmount) row.creditAmount = Number(f.creditAmount) || 0
  } else {
    if (f.date || f.approvalDate) row.approvalDate = String(f.date || f.approvalDate)
    if (f.approver) row.approver = String(f.approver)
  }
  calcRate(row)
  ocrDialogVisible.value = false
  persistAll()
  ElMessage.success('OCR结果已填入')
}

// ─── Stats ───────────────────────────────────────────────────────────
const totalCount = computed(() => rows.value.length)
const totalDiscount = computed(() => rows.value.reduce((s, r) => s + (r.discountAmount || 0), 0))
const avgRate = computed(() => { const valid = rows.value.filter(r => r.discountRate > 0); return valid.length ? valid.reduce((s, r) => s + r.discountRate, 0) / valid.length : 0 })

// ─── Persistence ─────────────────────────────────────────────────────
function persistAll() {
  props.allResponses.set('D4-19-rows', { item_id: 'D4-19-rows', conclusion: null, remark: JSON.stringify(rows.value) })
  props.allResponses.set('D4-19-note', { item_id: 'D4-19-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-19-conclusion', { item_id: 'D4-19-conclusion', conclusion: null, remark: auditConclusion.value })
  debounceSave()
}
function debounceSave() { if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000) }
function flushSave() {
  const keys = ['D4-19-rows', 'D4-19-note', 'D4-19-conclusion']
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
function handleExportTemplate() { exportTemplate('D4-19') }
function handleExportData() { exportData('D4-19') }
async function handleImportFile(uploadFile: any) { await importData('D4-19', uploadFile.raw || uploadFile) }

const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)
async function genNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiNoteLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-note', existingContent: auditNote.value, relatedContext: { task: '基于销售折扣与折让检查结果，生成审计说明', totalCount: totalCount.value, totalDiscount: totalDiscount.value, avgRate: avgRate.value } }, { _silent: true } as any)
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
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于销售折扣与折让检查结果生成审计结论', noteText: auditNote.value, totalCount: totalCount.value, totalDiscount: totalDiscount.value, avgRate: avgRate.value } }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    updateAuditConclusion(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false }
}
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

function fmtAmount(v: number): string { if (!v) return '—'; return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function fmtRate(v: number): string { return (v * 100).toFixed(2) + '%' }
</script>

<template>
  <div class="d4-discount">
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
        <GtIndexChip value="wp:D4-12" :context-project-id="projectId" />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-19-discount')">💬 复核</el-button>
      </div>
    </div>

    <!-- 统计仪表板 -->
    <div class="stats-dashboard">
      <div class="stat-card stat-primary">
        <div class="stat-value">{{ totalCount }}<span class="stat-unit">笔</span></div>
        <div class="stat-label">折扣笔数</div>
      </div>
      <div class="stat-card stat-amount">
        <div class="stat-value">{{ totalDiscount ? fmtAmount(totalDiscount) : '—' }}</div>
        <div class="stat-label">折扣总额</div>
      </div>
      <div class="stat-card stat-rate">
        <div class="stat-value">{{ avgRate > 0 ? fmtRate(avgRate) : '—' }}</div>
        <div class="stat-label">平均折扣率</div>
      </div>
    </div>

    <template v-if="editorMode !== '在线编辑'">
      <!-- 方法论折叠 -->
      <details class="methodology-collapse">
        <summary class="methodology-summary">📖 审计目标与折扣检查过程（点击展开）</summary>
        <div class="methodology-body">
          <p><strong>审计目标：</strong>与营业收入有关的折扣已恰当记录、相关披露正确。</p>
          <p><strong>审计过程：</strong>获取折扣与折让明细记录，核对记账凭证、检查审批手续，评价折扣政策执行的合规性。</p>
        </div>
      </details>

      <!-- 引导条 -->
      <div class="guide-strip">
        <span class="guide-strip-label">编制流程：</span>
        <el-tooltip content="从客户折扣明细表获取折扣记录" placement="bottom" :show-after="300"><span class="guide-chip">①获取折扣记录</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="核对折扣对应的记账凭证信息" placement="bottom" :show-after="300"><span class="guide-chip">②核对凭证</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="检查折扣审批手续是否完整" placement="bottom" :show-after="300"><span class="guide-chip">③检查审批</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="评价折扣是否符合公司折扣政策" placement="bottom" :show-after="300"><span class="guide-chip">④评价合规性</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="填写审计说明与结论" placement="bottom" :show-after="300"><span class="guide-chip">⑤填审计意见</span></el-tooltip>
      </div>

      <!-- 主表格 -->
      <el-table :data="rows" border stripe class="discount-table">
        <el-table-column label="序号" width="55" align="center" fixed>
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>

        <!-- 基本信息 -->
        <el-table-column label="基本信息" align="center" class-name="col-basic">
          <el-table-column label="客户名称" min-width="120">
            <template #default="{ row }"><el-input v-model="row.customerName" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="折扣类型" min-width="100">
            <template #default="{ row }"><el-input v-model="row.discountType" size="small" :disabled="isReadonly" placeholder="价格折扣/现金折扣/销售折让" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="收入金额" min-width="110" align="right">
            <template #default="{ row }"><el-input-number v-model="row.revenueAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="onCellChange(row)" /></template>
          </el-table-column>
          <el-table-column label="折扣金额" min-width="110" align="right">
            <template #default="{ row }"><el-input-number v-model="row.discountAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="onCellChange(row)" /></template>
          </el-table-column>
          <el-table-column label="折扣比例" min-width="80" align="right">
            <template #default="{ row }"><span class="auto-calc">{{ row.discountRate > 0 ? fmtRate(row.discountRate) : '—' }}</span></template>
          </el-table-column>
          <el-table-column label="原因" min-width="120">
            <template #default="{ row }"><el-input v-model="row.reason" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
        </el-table-column>

        <!-- 记账凭证 -->
        <el-table-column label="记账凭证" align="center" class-name="col-voucher">
          <el-table-column label="日期" min-width="105">
            <template #default="{ row }"><el-input v-model="row.voucherDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="编号" min-width="90">
            <template #default="{ row }"><el-input v-model="row.voucherNo" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="会计科目" min-width="100">
            <template #default="{ row }"><el-input v-model="row.accountSubject" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="明细科目" min-width="100">
            <template #default="{ row }"><el-input v-model="row.detailSubject" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="借方金额" min-width="110" align="right">
            <template #default="{ row }"><el-input-number v-model="row.debitAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="贷方金额" min-width="110" align="right">
            <template #default="{ row }"><el-input-number v-model="row.creditAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="persistAll()" /></template>
          </el-table-column>
        </el-table-column>

        <!-- 审批单 -->
        <el-table-column label="审批单" align="center" class-name="col-approval">
          <el-table-column label="日期" min-width="105">
            <template #default="{ row }"><el-input v-model="row.approvalDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="persistAll()" /></template>
          </el-table-column>
          <el-table-column label="审批人" min-width="80">
            <template #default="{ row }"><el-input v-model="row.approver" size="small" :disabled="isReadonly" @change="persistAll()" /></template>
          </el-table-column>
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
          <div class="opinion-field"><label>审计说明</label><el-input type="textarea" :autosize="{ minRows: 3, maxRows: 12 }" :model-value="auditNote" :disabled="isReadonly" placeholder="记录折扣检查范围、各类折扣的合理性判断及合规性评价" @input="(v: string) => updateAuditNote(v)" /></div>
          <div class="opinion-field"><label>审计结论</label><el-input type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" :model-value="auditConclusion" :disabled="isReadonly" placeholder="基于折扣检查结果，判断折扣记录是否恰当、披露是否正确" @input="(v: string) => updateAuditConclusion(v)" /></div>
        </div>
      </el-card>

      <!-- 编制提示 -->
      <details class="tips-collapse">
        <summary class="tips-summary">📋 编制提示</summary>
        <ol class="tips-list">
          <li>企业交易基于与客户的同阶段折扣政策，应核实折扣政策是否经适当审批。</li>
          <li>价格折扣：销售前即确定的价格让步，应直接抵减收入；现金折扣：为鼓励客户提前付款而给予的折扣，计入财务费用。</li>
          <li>销售折让：因质量问题等原因给予的价格扣减，应有完整的审批流程和原因说明。</li>
          <li>折扣比例异常偏高或波动较大时，应追查原因并评估对收入确认的影响。</li>
          <li>关注关联方交易中的折扣是否符合独立交易原则。</li>
        </ol>
      </details>
    </template>

    <!-- OnlyOffice -->
    <template v-if="editorMode === '在线编辑'">
      <div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="销售折扣与折让检查D4-19" :readonly="isReadonly" /></div>
    </template>

    <!-- OCR维度选择弹窗 -->
    <el-dialog v-model="ocrDialogVisible" title="OCR结果填入" width="400px" destroy-on-close>
      <p style="margin-bottom:12px;">请选择将OCR结果填入哪个维度：</p>
      <el-radio-group v-model="ocrDimension">
        <el-radio value="basic">基本信息</el-radio>
        <el-radio value="voucher">记账凭证</el-radio>
        <el-radio value="approval">审批单</el-radio>
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
.d4-discount { padding: 16px 20px; font-size: var(--wp-font-size, 13px); }
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
.discount-table { font-size: var(--wp-font-size, 13px); }
.discount-table :deep(.el-table__cell) { padding: 6px 0; }
.discount-table :deep(.col-basic .el-table__cell) { background-color: #f0faf0 !important; }
.discount-table :deep(.col-voucher .el-table__cell) { background-color: #f0f5ff !important; }
.discount-table :deep(.col-approval .el-table__cell) { background-color: #f8f0ff !important; }
.auto-calc { color: #909399; font-style: italic; border-bottom: 1px dashed #c0c4cc; cursor: help; }
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
