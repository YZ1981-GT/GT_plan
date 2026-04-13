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
    <div class="upload-zone" @drop.prevent="handleDrop" @dragover.prevent" @click="triggerUpload">
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
      <div class="results-table-wrap">
        <table class="results-table">
          <thead>
            <tr>
              <th>文件名</th>
              <th>类型</th>
              <th>字段名</th>
              <th>字段值</th>
              <th>置信度</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="doc in results" :key="doc.id">
              <tr
                v-for="(field, fi) in doc.fields"
                :key="field.id"
                :class="{ 'low-confidence': field.confidence < 0.80 }"
              >
                <td v-if="fi === 0" :rowspan="doc.fields.length">{{ doc.file_name }}</td>
                <td v-if="fi === 0" :rowspan="doc.fields.length">{{ doc.document_type }}</td>
                <td>{{ field.field_name }}</td>
                <td>
                  <span v-if="!field.editing">{{ field.field_value }}</span>
                  <input
                    v-else
                    v-model="field.editValue"
                    class="field-edit-input"
                    @keydown.enter="saveField(doc, field)"
                    @keydown.escape="field.editing = false"
                  />
                </td>
                <td :class="confidenceClass(field.confidence)">
                  {{ (field.confidence * 100).toFixed(0) }}%
                </td>
                <td>
                  <span :class="['status-badge', field.human_confirmed ? 'confirmed' : 'pending']">
                    {{ field.human_confirmed ? '✅ 已确认' : '⏳ 待确认' }}
                  </span>
                </td>
                <td>
                  <button
                    v-if="!field.human_confirmed"
                    class="btn-sm"
                    @click="startEdit(field)"
                  >✏️</button>
                  <button
                    v-if="field.editing"
                    class="btn-sm btn-primary"
                    @click="saveField(doc, field)"
                  >💾</button>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 匹配结果 -->
    <div v-if="matchResults.length > 0" class="match-results">
      <h4>🔗 账面匹配结果</h4>
      <table class="results-table">
        <thead>
          <tr>
            <th>单据</th>
            <th>匹配凭证号</th>
            <th>科目</th>
            <th>匹配金额</th>
            <th>差异</th>
            <th>结果</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in matchResults" :key="m.id" :class="matchRowClass(m.match_result)">
            <td>{{ m.file_name }}</td>
            <td>{{ m.matched_voucher_no || '-' }}</td>
            <td>{{ m.matched_account_code || '-' }}</td>
            <td>{{ m.matched_amount || '-' }}</td>
            <td>{{ m.difference_amount ? formatCurrency(m.difference_amount) : '-' }}</td>
            <td>
              <span :class="['status-badge', m.match_result]">
                {{ matchResultLabel(m.match_result) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
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

function matchRowClass(result) {
  if (result === 'mismatched') return 'row-warning'
  if (result === 'unmatched') return 'row-error'
  return ''
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
.panel-header h3 { margin: 0 0 12px; font-size: 16px; }

.tab-nav { display: flex; flex-wrap: wrap; gap: 4px; }
.tab-btn {
  padding: 4px 10px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.tab-btn.active { background: #4b2d77; color: #fff; border-color: #4b2d77; }

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
.upload-icon { font-size: 28px; }
.upload-types { font-size: 11px; color: #999; }

.progress-bar-wrap {
  position: relative;
  height: 24px;
  background: #f0f0f0;
  border-radius: 4px;
  margin-bottom: 16px;
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: #4b2d77;
  transition: width 0.3s;
}
.progress-text {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #fff;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 600;
}

.results-table-wrap { overflow-x: auto; }
.results-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.results-table th, .results-table td {
  border: 1px solid #eee;
  padding: 6px 8px;
  text-align: left;
}
.results-table th { background: #f9f9f9; font-weight: 600; }

.low-confidence { background: rgba(255,0,0,0.06); }
.conf-low { color: #ff4d4f; }
.conf-medium { color: #faad14; }
.conf-high { color: #52c41a; }

.status-badge {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}
.status-badge.pending { background: #fff7e6; color: #fa8c16; }
.status-badge.confirmed { background: #f6ffed; color: #52c41a; }
.status-badge.matched { background: #f6ffed; color: #52c41a; }
.status-badge.mismatched { background: #fff7e6; color: #fa8c16; }
.status-badge.unmatched { background: #fff2f0; color: #ff4d4f; }

.row-warning { background: rgba(255,173,0,0.08); }
.row-error { background: rgba(255,77,79,0.06); }

.field-edit-input {
  border: 1px solid #4b2d77;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 12px;
  width: 100%;
}

.btn-sm {
  padding: 2px 6px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
}
.btn-sm:hover { background: #f0f0f0; }
.btn-primary { background: #4b2d77; color: #fff; border-color: #4b2d77; }

.btn-link-ledger {
  padding: 4px 12px;
  background: #4b2d77;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.btn-link-ledger:disabled { background: #ccc; cursor: not-allowed; }

.match-results { margin-top: 16px; }
.match-results h4 { margin-bottom: 8px; font-size: 14px; }
</style>
