<template>
  <div class="gt-document-ocr-panel">
    <div class="panel-header">
      <h3>📄 单据智能识别</h3>
      <div class="tab-nav">
        <button
          v-for="tab in docTypeTabs"
          :key="tab.value"
          :class="['tab-btn', { active: currentType === tab.value }]"
          @click="currentType = tab.value"
        >
          {{ tab.label }}
        </button>
      </div>
    </div>

    <!-- 上传区域 -->
    <div class="upload-zone" @drop.prevent="handleDrop" @dragover.prevent @click="triggerUpload">
      <input
        ref="fileInput"
        type="file"
        multiple
        accept="image/*,.pdf"
        @change="handleFileChange"
        style="display:none"
      />
      <div class="upload-hint">
        <span class="upload-icon">📤</span>
        <span>拖入或点击上传图片/PDF</span>
        <span class="upload-types">支持：发票、出入库单、物流单、报销单等</span>
      </div>
    </div>

    <!-- 进度 -->
    <div v-if="uploadProgress > 0 && uploadProgress < 100" class="progress-bar-wrap">
      <div class="progress-bar" :style="{ width: uploadProgress + '%' }"></div>
      <span class="progress-text">识别中... {{ uploadProgress }}%</span>
    </div>

    <!-- 识别结果 -->
    <div v-if="results.length > 0" class="results-section">
      <div class="results-header">
        <span>识别结果 ({{ results.length }})</span>
        <button class="btn-link-ledger" @click="matchWithLedger" :disabled="matching">
          {{ matching ? '匹配中...' : '🔗 与账面数据匹配' }}
        </button>
      </div>
      <el-table
        :data="flattenedResults"
        :span-method="resultsSpanMethod"
        border
        size="small"
        :header-cell-style="{ background: '#f0edf5', whiteSpace: 'nowrap', fontSize: '12px' }"
        :row-class-name="resultsRowClassName"
      >
        <el-table-column prop="file_name" label="文件名" min-width="120" />
        <el-table-column prop="document_type" label="类型" min-width="100" />
        <el-table-column prop="field_name" label="字段名" min-width="100" />
        <el-table-column label="字段值" min-width="140">
          <template #default="{ row }">
            <span v-if="!row.editing">{{ row.field_value }}</span>
            <input
              v-else
              v-model="row.editValue"
              class="field-edit-input"
              @keydown.enter="saveField(row._doc, row)"
              @keydown.escape="row.editing = false"
            />
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="80" align="center">
          <template #default="{ row }">
            <span :class="confidenceClass(row.confidence)">
              {{ (row.confidence * 100).toFixed(0) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <span :class="['status-badge', row.human_confirmed ? 'confirmed' : 'pending']">
              {{ row.human_confirmed ? '✅ 已确认' : '⏳ 待确认' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <button
              v-if="!row.human_confirmed && !row.editing"
              class="btn-sm"
              @click="startEdit(row)"
            >✏️</button>
            <button
              v-if="row.editing"
              class="btn-sm btn-primary"
              @click="saveField(row._doc, row)"
            >💾</button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 匹配结果 -->
    <div v-if="matchResults.length > 0" class="match-results">
      <h4>🔗 账面匹配结果</h4>
      <el-table
        :data="matchResults"
        border
        size="small"
        :header-cell-style="{ background: '#f0edf5', whiteSpace: 'nowrap', fontSize: '12px' }"
        :row-class-name="matchRowClassName"
      >
        <el-table-column prop="file_name" label="单据" min-width="120" />
        <el-table-column label="匹配凭证号" min-width="120">
          <template #default="{ row }">{{ row.matched_voucher_no || '-' }}</template>
        </el-table-column>
        <el-table-column label="科目" min-width="120">
          <template #default="{ row }">{{ row.matched_account_code || '-' }}</template>
        </el-table-column>
        <el-table-column label="匹配金额" min-width="120" align="right">
          <template #default="{ row }">{{ row.matched_amount || '-' }}</template>
        </el-table-column>
        <el-table-column label="差异" min-width="120" align="right">
          <template #default="{ row }">
            {{ row.difference_amount ? formatCurrency(row.difference_amount) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="结果" width="110" align="center">
          <template #default="{ row }">
            <span :class="['status-badge', row.match_result]">
              {{ matchResultLabel(row.match_result) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ocrApi } from '@/services/aiApi'

const props = defineProps({ projectId: { type: String, required: true } })

const docTypeTabs = [
  { label: '全部', value: 'all' },
  { label: '销售发票', value: 'sales_invoice' },
  { label: '采购发票', value: 'purchase_invoice' },
  { label: '银行回单', value: 'bank_receipt' },
  { label: '银行对账单', value: 'bank_statement' },
  { label: '出库单', value: 'outbound_order' },
  { label: '入库单', value: 'inbound_order' },
  { label: '物流单', value: 'logistics_order' },
  { label: '报销单', value: 'expense_report' },
  { label: '合同', value: 'contract' },
]

const currentType = ref('all')
const fileInput = ref(null)
const uploadProgress = ref(0)
const results = ref([])
const matchResults = ref([])
const matching = ref(false)

/** Flatten results into one row per field, with _doc reference and _rowSpan for merge */
const flattenedResults = computed(() => {
  const rows = []
  for (const doc of results.value) {
    for (let fi = 0; fi < doc.fields.length; fi++) {
      const field = doc.fields[fi]
      rows.push({
        ...field,
        file_name: doc.file_name,
        document_type: doc.document_type,
        _doc: doc,
        _isFirstField: fi === 0,
        _fieldCount: doc.fields.length,
      })
    }
  }
  return rows
})

/** Span method for results table: merge file_name and document_type columns */
function resultsSpanMethod({ row, columnIndex }) {
  // Only merge first two columns (file_name, document_type)
  if (columnIndex === 0 || columnIndex === 1) {
    if (row._isFirstField) {
      return { rowspan: row._fieldCount, colspan: 1 }
    }
    return { rowspan: 0, colspan: 0 }
  }
}

/** Row class for low confidence highlighting */
function resultsRowClassName({ row }) {
  if (row.confidence < 0.80) return 'low-confidence'
  return ''
}

/** Row class for match results */
function matchRowClassName({ row }) {
  if (row.match_result === 'mismatched') return 'row-warning'
  if (row.match_result === 'unmatched') return 'row-error'
  return ''
}

function triggerUpload() { fileInput.value?.click() }

async function handleFileChange(e) {
  const files = Array.from(e.target.files)
  if (files.length > 0) await uploadFiles(files)
}

async function handleDrop(e) {
  const files = Array.from(e.dataTransfer.files)
  const allowed = files.filter(f => f.type.startsWith('image/') || f.type === 'application/pdf')
  if (allowed.length > 0) await uploadFiles(allowed)
}

async function uploadFiles(files) {
  uploadProgress.value = 1
  try {
    const res = await ocrApi.batchUploadDocuments(
      props.projectId,
      files,
      currentType.value === 'all' ? undefined : currentType.value,
      (p) => { uploadProgress.value = p }
    )
    // 轮询任务状态
    const taskId = res.task_id
    pollTaskStatus(taskId)
  } catch (e) {
    console.error(e)
    uploadProgress.value = 0
  }
}

async function pollTaskStatus(taskId) {
  const poll = async () => {
    const status = await ocrApi.getTaskStatus(taskId)
    uploadProgress.value = status.progress || 0
    if (status.status === 'completed') {
      uploadProgress.value = 100
      await loadResults()
      setTimeout(() => { uploadProgress.value = 0 }, 2000)
    } else if (status.status === 'failed') {
      uploadProgress.value = 0
    } else {
      setTimeout(poll, 2000)
    }
  }
  await poll()
}

async function loadResults() {
  const res = await ocrApi.getDocumentList(
    props.projectId,
    currentType.value === 'all' ? undefined : currentType.value
  )
  results.value = res || []
}

async function matchWithLedger() {
  matching.value = true
  try {
    for (const doc of results.value) {
      await ocrApi.matchWithLedger(props.projectId, doc.id)
    }
    const matchRes = await ocrApi.getDocumentList(props.projectId)
    matchResults.value = matchRes || []
  } finally {
    matching.value = false
  }
}

function startEdit(field) {
  field.editValue = field.field_value
  field.editing = true
}

async function saveField(doc, field) {
  try {
    await ocrApi.updateExtractedField(props.projectId, doc.id, field.id, {
      field_value: field.editValue,
      human_confirmed: true
    })
    field.field_value = field.editValue
    field.human_confirmed = true
    field.editing = false
  } catch (e) {
    console.error(e)
  }
}

function confidenceClass(score) {
  if (score < 0.70) return 'conf-low'
  if (score < 0.80) return 'conf-medium'
  return 'conf-high'
}

function matchResultLabel(r) {
  const m = { matched: '✅ 已匹配', mismatched: '⚠️ 不匹配', unmatched: '❌ 未匹配' }
  return m[r] || r
}

function formatCurrency(val) {
  if (val == null) return '-'
  return Number(val).toLocaleString('zh-CN', { style: 'currency', currency: 'CNY' })
}
</script>

<style scoped>
.gt-document-ocr-panel { padding: 16px; }

.panel-header { margin-bottom: 16px; }
.panel-header h3 { margin: 0 0 12px; font-size: var(--gt-font-size-md); }

.tab-nav { display: flex; flex-wrap: wrap; gap: 4px; }
.tab-btn {
  padding: 4px 10px;
  border: 1px solid #ddd;
  background: var(--gt-color-bg-white);
  border-radius: 4px;
  cursor: pointer;
  font-size: var(--gt-font-size-xs);
}
.tab-btn.active { background: var(--gt-color-primary); color: var(--gt-color-text-inverse); border-color: #4b2d77; }

.upload-zone {
  border: 2px dashed #ccc;
  border-radius: 8px;
  padding: 24px;
  text-align: center;
  cursor: pointer;
  margin-bottom: 16px;
}
.upload-zone:hover { border-color: #4b2d77; }
.upload-hint { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.upload-icon { font-size: var(--gt-font-size-3xl); }
.upload-types { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }

.progress-bar-wrap {
  position: relative;
  height: 24px;
  background: var(--gt-color-border-lighter);
  border-radius: 4px;
  margin-bottom: 16px;
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: var(--gt-color-primary);
  transition: width 0.3s;
}
.progress-text {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-inverse);
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 600;
}

:deep(.low-confidence) { background: rgba(255,0,0,0.06) !important; }
.conf-low { color: var(--gt-color-coral); }
.conf-medium { color: var(--gt-color-wheat); }
.conf-high { color: var(--gt-color-success); }

.status-badge {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: var(--gt-font-size-xs);
}
.status-badge.pending { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); }
.status-badge.confirmed { background: var(--gt-bg-success); color: var(--gt-color-success); }
.status-badge.matched { background: var(--gt-bg-success); color: var(--gt-color-success); }
.status-badge.mismatched { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); }
.status-badge.unmatched { background: var(--gt-bg-danger); color: var(--gt-color-coral); }

:deep(.row-warning) { background: rgba(255,173,0,0.08) !important; }
:deep(.row-error) { background: rgba(255,77,79,0.06) !important; }

.field-edit-input {
  border: 1px solid #4b2d77;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: var(--gt-font-size-xs);
  width: 100%;
}

.btn-sm {
  padding: 2px 6px;
  border: 1px solid #ddd;
  background: var(--gt-color-bg-white);
  border-radius: 4px;
  cursor: pointer;
  font-size: var(--gt-font-size-xs);
}
.btn-sm:hover { background: var(--gt-color-border-lighter); }
.btn-primary { background: var(--gt-color-primary); color: var(--gt-color-text-inverse); border-color: #4b2d77; }

.btn-link-ledger {
  padding: 4px 12px;
  background: var(--gt-color-primary);
  color: var(--gt-color-text-inverse);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: var(--gt-font-size-xs);
}
.btn-link-ledger:disabled { background: var(--gt-color-border); cursor: not-allowed; }

.match-results { margin-top: 16px; }
.match-results h4 { margin-bottom: 8px; font-size: var(--gt-font-size-sm); }
</style>
