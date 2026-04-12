<template>
  <div class="ai-contract-analysis">
    <!-- 顶部标签页 -->
    <div class="tab-nav">
      <button :class="{ active: activeTab === 'upload' }" @click="activeTab = 'upload'">上传分析</button>
      <button :class="{ active: activeTab === 'text' }" @click="activeTab = 'text'">文本分析</button>
      <button :class="{ active: activeTab === 'reports' }" @click="activeTab = 'reports'">分析报告</button>
    </div>

    <!-- 上传分析 -->
    <div v-if="activeTab === 'upload'" class="tab-content">
      <div class="upload-area">
        <div
          class="drop-zone"
          :class="{ dragover: isDragover }"
          @dragover.prevent="isDragover = true"
          @dragleave="isDragover = false"
          @drop.prevent="handleDrop"
          @click="triggerFile"
        >
          <input type="file" ref="fileInput" accept=".pdf,.docx,.doc,.txt" style="display:none" @change="handleFileChange" />
          <div class="drop-icon">📄</div>
          <p>点击或拖拽上传合同文件</p>
          <p class="hint">支持 PDF, Word, TXT</p>
        </div>

        <div class="analysis-options">
          <div class="option-group">
            <label>合同类型</label>
            <select v-model="contractType">
              <option value="采购合同">采购合同</option>
              <option value="销售合同">销售合同</option>
              <option value="贷款合同">贷款合同</option>
              <option value="租赁合同">租赁合同</option>
              <option value="服务合同">服务合同</option>
              <option value="其他">其他</option>
            </select>
          </div>
          <div class="option-group">
            <label>分析类型</label>
            <select v-model="analysisType">
              <option value="full">全面分析</option>
              <option value="risk">风险分析</option>
              <option value="clause">条款提取</option>
            </select>
          </div>
          <button class="btn-primary" @click="analyzeFile" :disabled="!selectedFile || loading">
            {{ loading ? '分析中...' : '开始分析' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 文本分析 -->
    <div v-if="activeTab === 'text'" class="tab-content">
      <div class="text-analysis">
        <div class="option-row">
          <select v-model="contractType">
            <option value="采购合同">采购合同</option>
            <option value="销售合同">销售合同</option>
            <option value="贷款合同">贷款合同</option>
            <option value="其他">其他</option>
          </select>
          <select v-model="analysisType">
            <option value="full">全面分析</option>
            <option value="risk">风险分析</option>
            <option value="clause">条款提取</option>
          </select>
        </div>
        <textarea
          v-model="contractText"
          placeholder="粘贴合同文本内容..."
          rows="12"
        ></textarea>
        <button class="btn-primary" @click="analyzeText" :disabled="!contractText.trim() || loading">
          {{ loading ? '分析中...' : '开始分析' }}
        </button>
      </div>
    </div>

    <!-- 分析报告列表 -->
    <div v-if="activeTab === 'reports'" class="tab-content">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="reports.length === 0" class="empty">
        暂无分析报告
      </div>
      <div v-else class="report-list">
        <div v-for="report in reports" :key="report.report_id" class="report-item" @click="viewReport(report.report_id)">
          <div class="report-info">
            <span class="report-name">{{ report.document_name }}</span>
            <span class="report-type badge">{{ report.analysis_type }}</span>
          </div>
          <div class="report-meta">
            <span>{{ report.status }}</span>
            <span>{{ formatDate(report.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 报告详情弹窗 -->
    <div class="modal-overlay" v-if="currentReport" @click.self="currentReport = null">
      <div class="modal report-modal">
        <div class="modal-header">
          <h3>{{ currentReport.document_name }}</h3>
          <button class="btn-sm" @click="currentReport = null">关闭</button>
        </div>
        <div class="report-summary" v-if="currentReport.summary">
          <h4>摘要</h4>
          <p>{{ currentReport.summary }}</p>
        </div>
        <div class="report-items" v-if="currentReport.items?.length">
          <h4>分析项目</h4>
          <div v-for="(item, idx) in currentReport.items" :key="idx" class="analysis-item">
            <div class="item-header">
              <span class="item-type badge" :class="item.severity">{{ item.item_type }}</span>
              <span class="item-title">{{ item.item_title }}</span>
            </div>
            <p class="item-content">{{ item.item_content }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAIContract } from '@/composables/useAI'

const props = defineProps({
  projectId: { type: String, required: true },
})

const {
  reports,
  currentReport,
  loading,
  analyzeContract,
  analyzeFile: analyzeFileApi,
  fetchReports,
  getReport,
} = useAIContract()

const activeTab = ref('upload')
const selectedFile = ref(null)
const isDragover = ref(false)
const contractType = ref('采购合同')
const analysisType = ref('full')
const contractText = ref('')
const fileInput = ref(null)

onMounted(async () => {
  await fetchReports(props.projectId)
})

function triggerFile() {
  fileInput.value?.click()
}

function handleFileChange(e) {
  selectedFile.value = e.target.files[0]
}

function handleDrop(e) {
  isDragover.value = false
  selectedFile.value = e.dataTransfer.files[0]
}

async function analyzeFile() {
  if (!selectedFile.value) return
  const formData = new FormData()
  formData.append('file', selectedFile.value)
  formData.append('project_id', props.projectId)
  formData.append('contract_type', contractType.value)
  formData.append('analysis_type', analysisType.value)

  try {
    await analyzeFileApi(formData)
    await fetchReports(props.projectId)
  } catch (e) {
    console.error('Analysis failed:', e)
  }
}

async function analyzeText() {
  if (!contractText.value.trim()) return
  try {
    await analyzeContract({
      project_id: props.projectId,
      contract_text: contractText.value,
      contract_type: contractType.value,
      analysis_type: analysisType.value,
    })
    await fetchReports(props.projectId)
    activeTab.value = 'reports'
  } catch (e) {
    console.error('Analysis failed:', e)
  }
}

async function viewReport(reportId) {
  currentReport.value = await getReport(reportId)
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleDateString('zh-CN')
}
</script>

<style scoped>
.ai-contract-analysis {
  padding: 20px;
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
}

.tab-nav {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  border-bottom: 1px solid #e4e7ed;
}

.tab-nav button {
  padding: 10px 20px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  color: #606266;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}

.tab-nav button.active {
  color: #409eff;
  border-bottom-color: #409eff;
}

.tab-content {
  background: #fff;
  padding: 20px;
  border-radius: 8px;
}

.drop-zone {
  border: 2px dashed #dcdfe6;
  border-radius: 8px;
  padding: 40px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.drop-zone:hover, .drop-zone.dragover {
  border-color: #409eff;
  background: #ecf5ff;
}

.drop-icon { font-size: 40px; margin-bottom: 8px; }
.hint { font-size: 12px; color: #909399; }

.analysis-options {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  align-items: flex-end;
}

.option-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.option-group label {
  font-size: 13px;
  color: #606266;
}

.option-group select {
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
}

.text-analysis textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  font-size: 14px;
  margin: 12px 0;
  font-family: inherit;
  resize: vertical;
  box-sizing: border-box;
}

.option-row {
  display: flex;
  gap: 12px;
}

.option-row select {
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
}

.report-list {
  display: grid;
  gap: 12px;
}

.report-item {
  padding: 14px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.report-item:hover {
  border-color: #409eff;
  background: #f5f9ff;
}

.report-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}

.report-name { font-size: 14px; font-weight: 500; }

.report-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #909399;
}

.badge {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  background: #ecf5ff;
  color: #409eff;
}

.badge.risk, .badge.high { background: #fef0f0; color: #f56c6c; }
.badge.medium { background: #fdf6ec; color: #e6a23c; }
.badge.low { background: #e7f7e7; color: #67c23a; }

.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  max-width: 800px;
  width: 90vw;
  max-height: 80vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
}

.modal-header h3 { margin: 0; }

.report-summary, .report-items {
  margin-bottom: 20px;
}

.report-summary h4, .report-items h4 {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.analysis-item {
  padding: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  margin-bottom: 8px;
}

.item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.item-title {
  font-size: 14px;
  font-weight: 500;
}

.item-content {
  font-size: 13px;
  color: #606266;
  margin: 0;
  line-height: 1.6;
}

.loading, .empty {
  text-align: center;
  padding: 40px;
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
}
</style>
