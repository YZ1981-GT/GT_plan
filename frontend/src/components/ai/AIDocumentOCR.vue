<template>
  <div class="ai-ocr">
    <!-- 上传区 -->
    <div class="upload-section">
      <div
        class="upload-zone"
        :class="{ dragover: isDragover }"
        @dragover.prevent="isDragover = true"
        @dragleave="isDragover = false"
        @drop.prevent="handleDrop"
        @click="triggerFileInput"
      >
        <input
          type="file"
          ref="fileInput"
          accept=".jpg,.jpeg,.png,.pdf,.bmp,.tiff"
          multiple
          style="display: none"
          @change="handleFileChange"
        />
        <div class="upload-icon">📄</div>
        <p>点击或拖拽上传文档</p>
        <p class="upload-hint">支持 JPG, PNG, PDF, BMP, TIFF</p>
      </div>

      <div class="upload-options">
        <select v-model="documentType" class="doc-type-select">
          <option value="invoice">发票</option>
          <option value="receipt">收据</option>
          <option value="contract">合同</option>
          <option value="bank_statement">银行对账单</option>
          <option value="waybill">货运单据</option>
          <option value="other">其他</option>
        </select>
        <button class="btn-primary" @click="startOCR" :disabled="files.length === 0 || loading">
          {{ loading ? '识别中...' : '开始识别' }}
        </button>
      </div>

      <!-- 进度条 -->
      <div class="progress-bar" v-if="loading">
        <div class="progress-fill" :style="{ width: progress + '%' }"></div>
        <span class="progress-text">{{ progress }}%</span>
      </div>
    </div>

    <!-- 结果列表 -->
    <div class="results-section" v-if="scans.length > 0">
      <h3>识别结果</h3>
      <div class="scan-list">
        <div
          v-for="scan in scans"
          :key="scan.scan_id"
          class="scan-item"
          :class="{ selected: selectedScan?.scan_id === scan.scan_id }"
          @click="selectScan(scan)"
        >
          <div class="scan-info">
            <span class="scan-name">{{ scan.filename || scan.original_filename }}</span>
            <span class="scan-status" :class="scan.status">{{ scan.status }}</span>
          </div>
          <div class="scan-meta">
            <span>{{ scan.document_type }}</span>
            <span>{{ formatDate(scan.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 详情面板 -->
    <div class="detail-panel" v-if="selectedScan">
      <div class="detail-header">
        <h3>{{ selectedScan.filename || '文档详情' }}</h3>
        <button class="btn-sm" @click="selectedScan = null">关闭</button>
      </div>

      <!-- 原始图片 -->
      <div class="image-preview" v-if="selectedScan.file_url">
        <img :src="selectedScan.file_url" alt="原始文档" />
      </div>

      <!-- 提取字段 -->
      <div class="extracted-fields">
        <h4>提取字段</h4>
        <div v-if="loadingFields" class="loading">加载中...</div>
        <div v-else class="field-list">
          <div v-for="field in extractedFields" :key="field.field_id" class="field-item">
            <label>{{ field.field_name }}</label>
            <div class="field-value-row">
              <input
                type="text"
                v-model="field.value"
                :class="{ corrected: field.is_corrected }"
                @blur="saveField(field)"
              />
              <span class="confidence" :class="getConfidenceClass(field.confidence)">
                {{ (field.confidence * 100).toFixed(0) }}%
              </span>
            </div>
          </div>
          <div v-if="extractedFields.length === 0" class="empty">
            暂无提取字段
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAIOCR } from '@/composables/useAI'

const props = defineProps({
  projectId: { type: String, required: true },
})

const {
  scans,
  currentScan,
  loading,
  progress,
  uploadDocument,
  fetchScans,
  getScanDetails,
  updateExtractedField,
} = useAIOCR()

const files = ref([])
const isDragover = ref(false)
const documentType = ref('invoice')
const selectedScan = ref(null)
const extractedFields = ref([])
const loadingFields = ref(false)
const fileInput = ref(null)

onMounted(async () => {
  await fetchScans(props.projectId)
})

function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileChange(e) {
  addFiles(Array.from(e.target.files))
  e.target.value = ''
}

function handleDrop(e) {
  isDragover.value = false
  const dropped = Array.from(e.dataTransfer.files)
  addFiles(dropped)
}

function addFiles(newFiles) {
  files.value = [...files.value, ...newFiles]
}

async function startOCR() {
  if (files.value.length === 0) return

  const formData = new FormData()
  files.value.forEach(f => formData.append('files', f))
  formData.append('project_id', props.projectId)
  formData.append('document_type', documentType.value)

  try {
    await uploadDocument(formData)
    files.value = []
  } catch (e) {
    console.error('OCR failed:', e)
  }
}

async function selectScan(scan) {
  selectedScan.value = scan
  loadingFields.value = true
  try {
    const details = await getScanDetails(scan.scan_id)
    selectedScan.value = details
    // 加载提取字段
    const { aiOCR } = await import('@/api')
    const fields = await aiOCR.getExtractedFields(scan.scan_id)
    extractedFields.value = fields
  } catch (e) {
    console.error('Failed to load scan details:', e)
  } finally {
    loadingFields.value = false
  }
}

async function saveField(field) {
  try {
    await updateExtractedField(selectedScan.value.scan_id, field.field_id, field.value)
    field.is_corrected = true
  } catch (e) {
    console.error('Failed to save field:', e)
  }
}

function getConfidenceClass(confidence) {
  if (confidence >= 0.9) return 'high'
  if (confidence >= 0.7) return 'medium'
  return 'low'
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleDateString('zh-CN')
}
</script>

<style scoped>
.ai-ocr {
  padding: 20px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.upload-section {
  margin-bottom: 24px;
}

.upload-zone {
  border: 2px dashed #dcdfe6;
  border-radius: 8px;
  padding: 40px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: #fafafa;
}

.upload-zone:hover, .upload-zone.dragover {
  border-color: #409eff;
  background: #ecf5ff;
}

.upload-icon {
  font-size: 40px;
  margin-bottom: 8px;
}

.upload-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.upload-options {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  align-items: center;
}

.doc-type-select {
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  font-size: 14px;
}

.progress-bar {
  margin-top: 12px;
  height: 24px;
  background: #f0f0f0;
  border-radius: 12px;
  overflow: hidden;
  position: relative;
}

.progress-fill {
  height: 100%;
  background: #409eff;
  transition: width 0.3s;
}

.progress-text {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 12px;
  color: #606266;
}

.results-section {
  margin-bottom: 24px;
}

.results-section h3 {
  margin-bottom: 12px;
  font-size: 16px;
  color: #303133;
}

.scan-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.scan-item {
  padding: 12px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.scan-item:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.15);
}

.scan-item.selected {
  border-color: #409eff;
  background: #ecf5ff;
}

.scan-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.scan-name {
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.scan-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
}

.scan-status.completed { background: #e7f7e7; color: #67c23a; }
.scan-status.pending { background: #fdf6ec; color: #e6a23c; }
.scan-status.failed { background: #fef0f0; color: #f56c6c; }

.scan-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #909399;
}

.detail-panel {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 20px;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.detail-header h3 {
  margin: 0;
  font-size: 16px;
}

.image-preview {
  margin-bottom: 20px;
  max-height: 400px;
  overflow: auto;
}

.image-preview img {
  max-width: 100%;
  border-radius: 4px;
}

.extracted-fields h4 {
  margin: 0 0 12px;
  font-size: 14px;
}

.field-list {
  display: grid;
  gap: 12px;
}

.field-item label {
  display: block;
  font-size: 13px;
  color: #606266;
  margin-bottom: 4px;
}

.field-value-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.field-value-row input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  font-size: 14px;
}

.field-value-row input.corrected {
  border-color: #67c23a;
  background: #f0f9ff;
}

.confidence {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
}

.confidence.high { background: #e7f7e7; color: #67c23a; }
.confidence.medium { background: #fdf6ec; color: #e6a23c; }
.confidence.low { background: #fef0f0; color: #f56c6c; }

.loading, .empty {
  text-align: center;
  padding: 20px;
  color: #909399;
}

.btn-primary {
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 8px 16px;
  cursor: pointer;
  font-size: 14px;
}

.btn-primary:disabled {
  background: #a0cfff;
  cursor: not-allowed;
}

.btn-sm {
  padding: 6px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
}
</style>
