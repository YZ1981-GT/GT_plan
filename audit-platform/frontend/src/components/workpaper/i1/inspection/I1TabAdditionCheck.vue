<template>
  <div class="i1-tab-addition-check">
    <!-- 蓝色引导区 -->
    <div class="guidance-area">
      <div class="guidance-grid">
        <div class="guidance-step"><span class="step-num">①</span> 从审定表"本期增加"取数确定检查总体</div>
        <div class="guidance-step"><span class="step-num">②</span> 通过抽凭引擎选取样本或手工添加检查项</div>
        <div class="guidance-step"><span class="step-num">③</span> 逐项核对合同/发票/支付凭证（📎OCR自动识别）</div>
        <div class="guidance-step"><span class="step-num">④</span> 确认入账金额、取得方式、入账时点的正确性</div>
      </div>
    </div>

    <!-- 琥珀色方法论 -->
    <div class="methodology-context">
      <p><b>CAS6 无形资产取得规则</b>：外购无形资产成本=购买价款+相关税费+直接归属费用（不含可抵扣进项税）；
      自行开发无形资产=满足资本化条件后的开发支出（研究阶段费用化）；接受投资/非货币交换/政府补助/合并取得按相应准则确认入账价值。
      关注：是否符合资本化条件（CAS6第8条）、入账时点是否正确、金额是否完整。</p>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实本期新增无形资产入账金额、取得方式及入账时点的正确性与完整性，验证资本化条件符合 CAS6，并与审定表本期增加勾稽一致。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:I1-5" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 跨底稿交叉引用提示区：I2资本化转入 -->
    <div class="cross-ref-bar">
      <span class="cross-ref-label">数据来源：</span>
      <GtIndexChip value="I2" @click="navigateToI2" />
      <span class="cross-ref-desc">开发支出资本化转入无形资产</span>
    </div>

    <!-- 导入导出 + 抽凭引擎 -->
    <el-card shadow="never" class="sampling-card">
      <template #header>
        <div class="section-title">
          <span>增加检查表（{{ rows.length }} 项）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleSampling" :disabled="isReadonly">🎲 抽凭引擎</el-button>
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-dropdown size="small" trigger="click" :disabled="isReadonly">
              <el-button size="small">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
                  <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
                  <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" type="default" link @click="handleReview('I1-5')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <!-- 检查明细表 -->
      <el-table :data="tableData" border stripe size="small" max-height="480" class="check-table" show-summary :summary-method="getSummary">
        <el-table-column type="index" label="序号" width="50" align="center" fixed />
        <el-table-column prop="name" label="名称" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" placeholder="无形资产名称" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="acquisitionMethod" label="取得方式" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.acquisitionMethod" size="small" placeholder="选择" style="width:90px">
              <el-option label="外购" value="外购" />
              <el-option label="自行开发" value="自行开发" />
              <el-option label="接受投资" value="接受投资" />
              <el-option label="非货币交换" value="非货币交换" />
              <el-option label="政府补助" value="政府补助" />
              <el-option label="合并取得" value="合并取得" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.acquisitionMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="entryDate" label="入账日期" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.entryDate" type="date" size="small" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:110px" />
            <span v-else>{{ row.entryDate }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="entryAmount" label="入账金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.entryAmount" :controls="false" size="small" :precision="2" style="width:110px" />
            <span v-else class="amount-cell">{{ fmtAmt(row.entryAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="contractInvoiceNo" label="合同/发票号" width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.contractInvoiceNo" size="small" placeholder="合同或发票号" />
            <span v-else>{{ row.contractInvoiceNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="paymentMethod" label="支付方式" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.paymentMethod" size="small" placeholder="选择" style="width:85px">
              <el-option label="银行转账" value="银行转账" />
              <el-option label="现金" value="现金" />
              <el-option label="票据" value="票据" />
              <el-option label="抵债" value="抵债" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.paymentMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="checkConclusion" label="审查结论" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.checkConclusion" size="small" style="width:85px">
              <el-option label="无异常" value="无异常" />
              <el-option label="有异常" value="有异常" />
              <el-option label="待核实" value="待核实" />
            </el-select>
            <el-tag v-else :type="conclusionTagType(row.checkConclusion)" size="small">{{ row.checkConclusion || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="📎" width="50" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="handleOcr(row)" :disabled="isReadonly" title="上传附件OCR识别">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计联动提示 -->
      <div class="summary-bar">
        <span>检查金额合计: <b class="amount-cell">{{ fmtAmt(totalAmount) }}</b></span>
        <span>审定表"本期增加": <b class="amount-cell formula-link" @click="navigateToAdjudication" title="点击跳转审定表">{{ fmtAmt(adjudicationAddition) }}</b></span>
        <span v-if="diffAmount !== 0" class="diff-warning">差额: <b>{{ fmtAmt(diffAmount) }}</b></span>
        <span>异常: <b :class="{ 'error-amount': anomalyCount > 0 }">{{ anomalyCount }}</b> 项</span>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5, maxRows: 10 }" :disabled="isReadonly" placeholder="填写审计说明：检查范围与抽样方法、合同/发票/支付凭证核对情况、资本化条件判断及异常项处理等。" @blur="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="经检查，本期新增无形资产入账金额、取得方式及入账时点正确，与审定表勾稽一致，未见异常…" @blur="handleSave" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>📎 点击附件按钮上传合同/发票图片→OCR识别→确认后自动填入金额/日期/合同号</li>
        <li>🎲 抽凭引擎可按MUS/随机/系统抽样自动选取检查样本</li>
        <li>检查要点：入账金额与合同/发票一致、取得方式分类正确、入账时点截止正确、资本化条件（CAS6第8条）</li>
        <li>合计行自动联动审定表I1"本期增加"列，差额≠0将显示黄色警告</li>
        <li>I2开发支出资本化转入项可通过抽凭引擎或手工添加后核对I2底稿</li>
      </ul>
    </details>

    <!-- 抽凭引擎 dialog -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 1701 无形资产-增加）" width="720px" :close-on-click-modal="false" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :account-codes="['1701']"
        dialog-mode
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, watch, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId?: string, value?: any]
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Types ───────────────────────────────────────────────────────────────────

interface AdditionRow {
  rowId: string
  name: string
  acquisitionMethod: string
  entryDate: string
  entryAmount: number
  contractInvoiceNo: string
  paymentMethod: string
  checkConclusion: string
  attachmentUrl: string
  ocrResult: string
  remark: string
  voucherSampleId: string
}

// ─── State ───────────────────────────────────────────────────────────────────

const rows = ref<AdditionRow[]>([])
const conclusion = ref('')
const auditNote = ref('')
const showSamplingDialog = ref(false)

// ─── Storage item_id ─────────────────────────────────────────────────────────

const ITEM_PREFIX = 'I1-5'

// ─── Load from allResponses ──────────────────────────────────────────────────

function loadData() {
  const rowItem = props.allResponses.get(`${ITEM_PREFIX}-rows`)
  if (rowItem?.remark) {
    try {
      const parsed = JSON.parse(rowItem.remark)
      rows.value = Array.isArray(parsed) ? parsed.map(normalizeRow) : []
    } catch { rows.value = [] }
  } else { rows.value = [] }

  const conclusionItem = props.allResponses.get(`${ITEM_PREFIX}-conclusion`)
  conclusion.value = (conclusionItem?.remark ?? conclusionItem?.conclusion ?? '') as string

  const noteItem = props.allResponses.get(`${ITEM_PREFIX}-audit-note`)
  auditNote.value = (noteItem?.remark ?? noteItem?.conclusion ?? '') as string
}

function normalizeRow(raw: any): AdditionRow {
  return {
    rowId: raw.rowId ?? `i1add-${Math.random().toString(36).slice(2, 10)}`,
    name: raw.name ?? '',
    acquisitionMethod: raw.acquisitionMethod ?? '',
    entryDate: raw.entryDate ?? '',
    entryAmount: Number(raw.entryAmount) || 0,
    contractInvoiceNo: raw.contractInvoiceNo ?? '',
    paymentMethod: raw.paymentMethod ?? '',
    checkConclusion: raw.checkConclusion ?? '',
    attachmentUrl: raw.attachmentUrl ?? '',
    ocrResult: raw.ocrResult ?? '',
    remark: raw.remark ?? '',
    voucherSampleId: raw.voucherSampleId ?? '',
  }
}

watch(() => props.allResponses, () => loadData(), { immediate: true })

// ─── Computed ────────────────────────────────────────────────────────────────

const tableData = computed(() => rows.value)

const totalAmount = computed(() =>
  rows.value.reduce((sum, r) => sum + (r.entryAmount || 0), 0),
)

const anomalyCount = computed(() =>
  rows.value.filter((r) => r.checkConclusion === '有异常').length,
)

/** 从审定表allResponses取"本期增加"合计（原值区块） */
const adjudicationAddition = computed(() => {
  const adjItem = props.allResponses.get('I1-adjudication-cost-addition-total')
  if (adjItem?.remark) return Number(adjItem.remark) || 0
  // fallback: 尝试从allResponses其他字段取
  const fallback = props.allResponses.get('I1-cost-addition')
  return Number(fallback?.remark) || 0
})

const diffAmount = computed(() => totalAmount.value - adjudicationAddition.value)

// ─── Actions ─────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入无形资产名称',
      '新增检查项',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '如：XX软件著作权' },
    )
    if (!name?.trim()) return
    const newRow: AdditionRow = {
      rowId: `i1add-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      name: name.trim(),
      acquisitionMethod: '',
      entryDate: '',
      entryAmount: 0,
      contractInvoiceNo: '',
      paymentMethod: '',
      checkConclusion: '',
      attachmentUrl: '',
      ocrResult: '',
      remark: '',
      voucherSampleId: '',
    }
    rows.value.push(newRow)
    persist()
  } catch { /* cancelled */ }
}

function removeRow(rowId: string) {
  const idx = rows.value.findIndex((r) => r.rowId === rowId)
  if (idx >= 0) {
    rows.value.splice(idx, 1)
    persist()
  }
}

function handleSampling() {
  showSamplingDialog.value = true
}

/** 抽凭引擎完成后回调 */
function onSampleFilled(samples: any[]) {
  showSamplingDialog.value = false
  if (!samples?.length) return
  for (const s of samples) {
    const newRow: AdditionRow = {
      rowId: `i1add-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      name: s.summary || s.description || s.accountName || '抽样项',
      acquisitionMethod: '',
      entryDate: s.date ?? s.entryDate ?? '',
      entryAmount: Number(s.amount) || 0,
      contractInvoiceNo: s.voucherNo ?? '',
      paymentMethod: '',
      checkConclusion: '',
      attachmentUrl: '',
      ocrResult: '',
      remark: '',
      voucherSampleId: s.sampleId ?? '',
    }
    rows.value.push(newRow)
  }
  persist()
  ElMessage.success(`已添加 ${samples.length} 个抽样项`)
}

/** 行级 OCR：📎上传→POST /d4/contract-ocr→ElMessageBox确认→merge字段 */
async function handleOcr(row: AdditionRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${props.wpId}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields = data?.extracted_fields || {}
      if (!Object.keys(fields).length) {
        ElMessageBox.alert('OCR完成，未识别到可填充字段', '提示')
        return
      }
      const preview = Object.entries(fields).map(([k, v]) => `${k}: ${v}`).join('\n')
      await ElMessageBox.confirm(
        `识别结果：\n${preview}\n\n确认填入？`,
        'OCR识别结果',
        { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
      )
      // merge fields into row
      if (fields.amount || fields.entryAmount) row.entryAmount = Number(fields.amount || fields.entryAmount) || row.entryAmount
      if (fields.date || fields.entryDate) row.entryDate = (fields.date || fields.entryDate) as string
      if (fields.contractNo || fields.contract_no || fields.invoiceNo || fields.invoice_no) {
        row.contractInvoiceNo = (fields.contractNo || fields.contract_no || fields.invoiceNo || fields.invoice_no) as string
      }
      if (fields.paymentMethod) row.paymentMethod = fields.paymentMethod as string
      if (fields.name || fields.assetName) row.name = row.name || (fields.name || fields.assetName) as string
      row.attachmentUrl = file.name
      row.ocrResult = JSON.stringify(fields)
      persist()
      ElMessage.success('OCR结果已填入')
    } catch { /* user cancelled or request failed */ }
  }
  input.click()
}

/** 导入导出 */
async function handleExportTemplate() {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/i1/export-template?sheet=I1-5`, { responseType: 'blob' })
    downloadBlob(res.data, 'I1-5_增加检查表_模板.xlsx')
  } catch { ElMessage.warning('导出模板失败') }
}

async function handleExportData() {
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/i1/export-data`,
      { sheet: 'I1-5', rows: rows.value },
      { responseType: 'blob' },
    )
    downloadBlob(res.data, 'I1-5_增加检查表_数据.xlsx')
  } catch { ElMessage.warning('导出数据失败') }
}

async function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    formData.append('sheet', 'I1-5')
    try {
      const res = await http.post(
        `/api/workpapers/${props.wpId}/i1/import-data`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      const imported = res.data?.data?.rows ?? res.data?.rows ?? []
      if (imported.length) {
        await ElMessageBox.confirm(`识别到 ${imported.length} 行数据，是否导入？`, '导入确认')
        rows.value = imported.map(normalizeRow)
        persist()
        ElMessage.success(`已导入 ${imported.length} 行`)
      } else {
        ElMessage.warning('未识别到有效数据')
      }
    } catch { /* cancelled */ }
  }
  input.click()
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function navigateToAdjudication() {
  emit('navigate-sheet', '审定表I1')
}

function navigateToI2() {
  emit('navigate-sheet', 'I2')
}

function handleReview(id: string) { openReviewDialog(id) }

// ─── Persist ─────────────────────────────────────────────────────────────────

function persist() {
  // 行数据通过 emit save(itemId,value) 通知父组件保存
  emit('save', `${ITEM_PREFIX}-rows`, JSON.stringify(rows.value))
}

function handleSave() {
  emit('save', `${ITEM_PREFIX}-conclusion`, conclusion.value)
}

function saveAuditNote() {
  if (props.isReadonly) return
  emit('save', `${ITEM_PREFIX}-audit-note`, auditNote.value)
}

// ─── Summary ─────────────────────────────────────────────────────────────────

function getSummary({ columns, data }: any) {
  const sums: string[] = []
  columns.forEach((col: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    if (col.property === 'entryAmount') {
      sums[idx] = fmtAmt(totalAmount.value)
      return
    }
    sums[idx] = ''
  })
  return sums
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function conclusionTagType(val: string): '' | 'success' | 'danger' | 'warning' {
  if (val === '无异常') return 'success'
  if (val === '有异常') return 'danger'
  if (val === '待核实') return 'warning'
  return ''
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-addition-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

.guidance-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6ecfa 100%);
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 12px;
}
.guidance-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}
.guidance-step {
  font-size: 12px;
  color: #1a5276;
  display: flex;
  align-items: center;
  gap: 6px;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2980b9;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #7d6608;
  line-height: 1.6;
}
.methodology-context b { color: #5a4e04; }

.cross-ref-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  margin-bottom: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  border: 1px dashed var(--el-border-color);
  font-size: 12px;
}
.cross-ref-label {
  color: var(--el-text-color-secondary);
  font-weight: 500;
}
.cross-ref-desc {
  color: var(--el-text-color-regular);
}

.sampling-card { margin-bottom: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.title-actions { display: flex; gap: 8px; align-items: center; }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-link {
  text-decoration: underline dashed;
  cursor: help;
  color: var(--el-color-primary);
}
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.diff-warning { color: var(--el-color-warning-dark-2); font-weight: 500; }
.summary-bar {
  display: flex;
  gap: 24px;
  padding: 10px 12px;
  margin-top: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  flex-wrap: wrap;
}
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
