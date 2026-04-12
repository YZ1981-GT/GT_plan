<template>
  <div class="ai-workpaper-fill">
    <div class="page-header">
      <h2>AI 底稿填充</h2>
    </div>

    <!-- 任务列表 -->
    <div class="tasks-section">
      <h3>填充任务</h3>
      <div class="task-list">
        <div
          v-for="task in tasks"
          :key="task.task_id"
          class="task-card"
          :class="task.status"
          @click="viewTask(task)"
        >
          <div class="task-info">
            <span class="task-name">{{ task.workpaper_name || task.template_name }}</span>
            <span class="status-badge" :class="task.status">{{ task.status }}</span>
          </div>
          <div class="task-meta">
            <span>{{ task.analysis_type }}</span>
            <span>{{ formatDate(task.created_at) }}</span>
          </div>
          <div class="progress-row" v-if="task.status === 'completed'">
            <div class="mini-progress">
              <div class="fill" :style="{ width: (task.fill_rate || 0) + '%' }"></div>
            </div>
            <span>{{ task.fill_rate?.toFixed(0) || 0 }}%</span>
          </div>
        </div>
        <div v-if="tasks.length === 0" class="empty">暂无填充任务</div>
      </div>
    </div>

    <!-- 新建任务 -->
    <div class="create-section">
      <h3>创建填充任务</h3>
      <div class="create-form">
        <div class="form-row">
          <div class="form-group">
            <label>底稿名称</label>
            <input v-model="form.workpaper_name" placeholder="如: 货币资金审计底稿" />
          </div>
          <div class="form-group">
            <label>分析类型</label>
            <select v-model="form.analysis_type">
              <option value="summary">内容摘要</option>
              <option value="fill">数据填充</option>
              <option value="compare">数据对比</option>
              <option value="risk">风险评估</option>
            </select>
          </div>
        </div>

        <div class="form-group">
          <label>分析要求</label>
          <textarea
            v-model="form.requirements"
            placeholder="描述需要的分析内容，如：提取本期期末现金余额、与银行对账单核对..."
            rows="3"
          ></textarea>
        </div>

        <div class="form-group">
          <label>支持文件（可选）</label>
          <input type="file" multiple @change="handleFileChange" accept=".xlsx,.xls,.pdf,.csv" />
          <div class="file-list" v-if="form.files.length">
            <span v-for="(f, i) in form.files" :key="i" class="file-tag">{{ f.name }}</span>
          </div>
        </div>

        <button class="btn-primary" @click="startFill" :disabled="loading || !form.workpaper_name">
          {{ loading ? '提交中...' : '开始填充' }}
        </button>
      </div>
    </div>

    <!-- 任务详情弹窗 -->
    <div class="modal-overlay" v-if="currentTask" @click.self="currentTask = null">
      <div class="modal fill-modal">
        <div class="modal-header">
          <h3>{{ currentTask.workpaper_name }}</h3>
          <button class="btn-sm" @click="currentTask = null">关闭</button>
        </div>

        <div class="task-status-bar">
          <span class="status-badge" :class="currentTask.status">{{ currentTask.status }}</span>
          <span v-if="currentTask.fill_rate">填充率: {{ currentTask.fill_rate.toFixed(1) }}%</span>
        </div>

        <!-- 结果内容 -->
        <div class="fill-result" v-if="fillResult">
          <div class="result-header">
            <h4>分析结果</h4>
            <div class="result-actions">
              <button class="btn-sm" @click="applyResult">应用到底稿</button>
              <button class="btn-sm" @click="exportResult">导出</button>
            </div>
          </div>

          <div class="result-sections">
            <div v-for="(section, idx) in fillResult.sections" :key="idx" class="result-section">
              <div class="section-title">{{ section.title }}</div>
              <div class="section-content">{{ section.content }}</div>
            </div>
          </div>

          <!-- 填充字段 -->
          <div v-if="fillResult.fields?.length" class="fill-fields">
            <h4>填充字段</h4>
            <table class="fields-table">
              <thead>
                <tr>
                  <th>字段</th>
                  <th>AI 填充值</th>
                  <th>原值</th>
                  <th>置信度</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="field in fillResult.fields" :key="field.field_id">
                  <td>{{ field.field_name }}</td>
                  <td>
                    <input
                      type="text"
                      v-model="field.filled_value"
                      :class="{ corrected: field.is_corrected }"
                    />
                  </td>
                  <td>{{ field.original_value || '-' }}</td>
                  <td>
                    <span class="confidence" :class="getConfidenceClass(field.confidence)">
                      {{ (field.confidence * 100).toFixed(0) }}%
                    </span>
                  </td>
                  <td>
                    <button class="btn-sm" @click="applyField(field)">确认</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 差异分析 -->
          <div v-if="fillResult.discrepancies?.length" class="discrepancies">
            <h4>差异分析</h4>
            <div v-for="(d, idx) in fillResult.discrepancies" :key="idx" class="discrepancy-item">
              <span class="disc-badge" :class="d.severity">{{ d.severity }}</span>
              <span>{{ d.description }}</span>
            </div>
          </div>
        </div>

        <div v-else-if="currentTask.status === 'pending'" class="waiting">
          <div class="spinner"></div>
          <p>AI 正在分析中，请稍候...</p>
        </div>

        <div v-else-if="currentTask.status === 'failed'" class="error">
          <p>处理失败: {{ currentTask.error_message || '未知错误' }}</p>
        </div>

        <div v-else class="no-result">
          <p>点击下方按钮获取填充结果</p>
          <button class="btn-primary" @click="loadResult" :disabled="loadingResult">
            {{ loadingResult ? '加载中...' : '获取结果' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAIWorkpaper } from '@/composables/useAI'

const props = defineProps({
  projectId: { type: String, required: true },
})

const {
  tasks,
  currentTask,
  loading,
  error,
  createFillTask,
  fetchTasks,
  getTaskResult,
} = useAIWorkpaper()

const form = ref({
  workpaper_name: '',
  analysis_type: 'summary',
  requirements: '',
  files: [],
})

const fillResult = ref(null)
const loadingResult = ref(false)

onMounted(async () => {
  await fetchTasks(props.projectId)
})

async function startFill() {
  if (!form.value.workpaper_name) return
  try {
    const task = await createFillTask({
      project_id: props.projectId,
      ...form.value,
    })
    tasks.value.unshift(task)
    await fetchTasks(props.projectId)
    // 清空表单
    form.value = { workpaper_name: '', analysis_type: 'summary', requirements: '', files: [] }
  } catch (e) {
    console.error('Create task failed:', e)
  }
}

function handleFileChange(e) {
  form.value.files = Array.from(e.target.files)
}

async function viewTask(task) {
  currentTask.value = task
  fillResult.value = null
  if (task.status === 'completed') {
    await loadResult()
  }
}

async function loadResult() {
  if (!currentTask.value) return
  loadingResult.value = true
  try {
    fillResult.value = await getTaskResult(currentTask.value.task_id)
  } catch (e) {
    console.error('Load result failed:', e)
  } finally {
    loadingResult.value = false
  }
}

function applyField(field) {
  field.is_corrected = true
  console.log('Apply field:', field)
}

function applyResult() {
  console.log('Apply result to workpaper:', fillResult.value)
}

function exportResult() {
  console.log('Export result:', fillResult.value)
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
.ai-workpaper-fill {
  padding: 20px;
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
}

.page-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-header h2 { margin: 0; font-size: 20px; }

.tasks-section, .create-section {
  background: #fff;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 20px;
}

.tasks-section h3, .create-section h3 {
  font-size: 16px;
  margin: 0 0 16px;
  color: #303133;
}

.task-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.task-card {
  padding: 14px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.task-card:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.15);
}

.task-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}

.task-name { font-size: 14px; font-weight: 500; }

.task-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #909399;
}

.progress-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 12px;
}

.mini-progress {
  flex: 1;
  height: 4px;
  background: #f0f0f0;
  border-radius: 2px;
}

.mini-progress .fill {
  height: 100%;
  background: #409eff;
  transition: width 0.3s;
}

.create-form {
  max-width: 600px;
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-group {
  flex: 1;
  margin-bottom: 14px;
}

.form-group label {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
  color: #606266;
}

.form-group input[type="text"],
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
}

.file-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.file-tag {
  padding: 2px 8px;
  background: #f0f0f0;
  border-radius: 10px;
  font-size: 12px;
}

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
  width: 700px;
  max-width: 90vw;
  max-height: 85vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
}

.modal-header h3 { margin: 0; }

.task-status-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
  font-size: 14px;
}

.status-badge {
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
}

.status-badge.completed { background: #e7f7e7; color: #67c23a; }
.status-badge.pending { background: #fdf6ec; color: #e6a23c; }
.status-badge.failed { background: #fef0f0; color: #f56c6c; }

.result-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}

.result-header h4 { margin: 0; }

.result-actions { display: flex; gap: 8px; }

.result-sections {
  display: grid;
  gap: 12px;
  margin-bottom: 20px;
}

.result-section {
  padding: 12px;
  background: #f9f9f9;
  border-radius: 6px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #409eff;
  margin-bottom: 6px;
}

.section-content {
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

.fields-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.fields-table th, .fields-table td {
  padding: 8px;
  border: 1px solid #e4e7ed;
  text-align: left;
}

.fields-table th {
  background: #f5f7fa;
  font-weight: 500;
}

.fields-table td input {
  width: 100%;
  padding: 4px 8px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 13px;
}

.fields-table td input.corrected {
  border-color: #67c23a;
  background: #f0fdf4;
}

.confidence {
  padding: 2px 6px;
  border-radius: 8px;
  font-size: 12px;
}

.confidence.high { background: #e7f7e7; color: #67c23a; }
.confidence.medium { background: #fdf6ec; color: #e6a23c; }
.confidence.low { background: #fef0f0; color: #f56c6c; }

.discrepancies {
  margin-top: 16px;
}

.discrepancy-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border-bottom: 1px solid #f0f0f0;
  font-size: 13px;
}

.disc-badge {
  padding: 2px 8px;
  border-radius: 8px;
  font-size: 11px;
}

.disc-badge.high { background: #fef0f0; color: #f56c6c; }
.disc-badge.medium { background: #fdf6ec; color: #e6a23c; }
.disc-badge.low { background: #e7f7e7; color: #67c23a; }

.waiting, .error, .no-result {
  text-align: center;
  padding: 40px;
  color: #909399;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #f0f0f0;
  border-top-color: #409eff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error { color: #f56c6c; }

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

.empty { text-align: center; padding: 40px; color: #909399; }
</style>
