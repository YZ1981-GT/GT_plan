<template>
  <div class="pdf-export-page">
    <div class="pe-header">
      <h2 class="pe-title">PDF 导出</h2>
    </div>

    <el-row :gutter="16">
      <!-- 左侧：导出配置 -->
      <el-col :span="10">
        <div class="panel">
          <h4 class="panel-title">文档选择</h4>
          <el-checkbox-group v-model="selectedDocs" class="doc-checkboxes">
            <el-checkbox value="audit_report" label="审计报告" />
            <el-checkbox value="balance_sheet" label="资产负债表" />
            <el-checkbox value="income_statement" label="利润表" />
            <el-checkbox value="cash_flow_statement" label="现金流量表" />
            <el-checkbox value="equity_statement" label="所有者权益变动表" />
            <el-checkbox value="disclosure_notes" label="财务报表附注" />
          </el-checkbox-group>

          <el-divider />

          <h4 class="panel-title">导出选项</h4>
          <el-form label-width="100px">
            <el-form-item label="密码保护">
              <el-switch v-model="passwordProtected" />
            </el-form-item>
            <el-form-item v-if="passwordProtected" label="密码">
              <el-input v-model="password" type="password" show-password placeholder="设置PDF打开密码" />
            </el-form-item>
          </el-form>

          <el-button type="primary" @click="onExport" :loading="exportLoading"
            :disabled="selectedDocs.length === 0" style="width: 100%; margin-top: 12px">
            开始导出
          </el-button>

          <!-- 进度条 -->
          <div v-if="currentTask" class="progress-section">
            <el-divider />
            <div class="progress-info">
              <span>状态: {{ taskStatusLabel(currentTask.status) }}</span>
              <span>{{ currentTask.progress_percentage }}%</span>
            </div>
            <el-progress :percentage="currentTask.progress_percentage"
              :status="progressStatus(currentTask.status)" :stroke-width="12" />
            <div v-if="currentTask.status === 'completed'" class="download-link">
              <el-button type="success" @click="onDownload(currentTask.id)">下载 PDF</el-button>
              <span v-if="currentTask.file_size" class="file-size">
                {{ formatFileSize(currentTask.file_size) }}
              </span>
            </div>
            <div v-if="currentTask.status === 'failed'" class="error-msg">
              {{ currentTask.error_message || '导出失败' }}
            </div>
          </div>
        </div>
      </el-col>

      <!-- 右侧：历史记录 -->
      <el-col :span="14">
        <div class="panel">
          <h4 class="panel-title">导出历史</h4>
          <el-table :data="history" v-loading="historyLoading" border stripe size="small">
            <el-table-column label="时间" width="160">
              <template #default="{ row }">{{ row.created_at?.slice(0, 19).replace('T', ' ') }}</template>
            </el-table-column>
            <el-table-column label="类型" width="100">
              <template #default="{ row }">
                <el-tag size="small">{{ row.task_type === 'full_archive' ? '完整归档' : '单文档' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">{{ taskStatusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="大小" width="100">
              <template #default="{ row }">{{ row.file_size ? formatFileSize(row.file_size) : '-' }}</template>
            </el-table-column>
            <el-table-column label="完成时间" width="160">
              <template #default="{ row }">{{ row.completed_at?.slice(0, 19).replace('T', ' ') || '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button v-if="row.status === 'completed'" size="small" type="primary"
                  @click="onDownload(row.id)">下载</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  createExportTask, getExportTaskStatus, getExportDownloadUrl, getExportHistory,
  type ExportTaskData,
} from '@/services/auditPlatformApi'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)

const selectedDocs = ref<string[]>([])
const passwordProtected = ref(false)
const password = ref('')
const exportLoading = ref(false)
const historyLoading = ref(false)
const currentTask = ref<ExportTaskData | null>(null)
const history = ref<ExportTaskData[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

function taskStatusLabel(s: string) {
  const m: Record<string, string> = { queued: '排队中', processing: '处理中', completed: '已完成', failed: '失败' }
  return m[s] || s
}

function statusTagType(s: string) {
  const m: Record<string, string> = { queued: 'info', processing: 'warning', completed: 'success', failed: 'danger' }
  return m[s] || 'info'
}

function progressStatus(s: string) {
  if (s === 'completed') return 'success'
  if (s === 'failed') return 'exception'
  return undefined
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

async function onExport() {
  exportLoading.value = true
  try {
    const taskType = selectedDocs.value.length > 1 ? 'full_archive' : 'single_document'
    const result = await createExportTask(
      projectId.value, taskType, selectedDocs.value,
      passwordProtected.value, passwordProtected.value ? password.value : undefined,
    )
    currentTask.value = result
    ElMessage.success('导出任务已创建')
    startPolling(result.id)
  } finally { exportLoading.value = false }
}

function startPolling(taskId: string) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const status = await getExportTaskStatus(taskId)
      currentTask.value = status
      if (status.status === 'completed' || status.status === 'failed') {
        stopPolling()
        fetchHistory()
      }
    } catch { stopPolling() }
  }, 2000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

function onDownload(taskId: string) {
  window.open(getExportDownloadUrl(taskId), '_blank')
}

async function fetchHistory() {
  historyLoading.value = true
  try { history.value = await getExportHistory(projectId.value) }
  catch { history.value = [] }
  finally { historyLoading.value = false }
}

onMounted(fetchHistory)
onUnmounted(stopPolling)
</script>

<style scoped>
.pdf-export-page { padding: 16px; }
.pe-header { margin-bottom: 16px; }
.pe-title { margin: 0; color: var(--gt-color-primary); font-size: 20px; }
.panel { background: #fff; border-radius: var(--gt-radius-sm); padding: 16px; box-shadow: var(--gt-shadow-sm); }
.panel-title { margin: 0 0 12px; font-size: 14px; color: var(--gt-color-primary); }
.doc-checkboxes { display: flex; flex-direction: column; gap: 8px; }
.progress-section { margin-top: 8px; }
.progress-info { display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px; color: #666; }
.download-link { margin-top: 8px; display: flex; align-items: center; gap: 8px; }
.file-size { font-size: 12px; color: #999; }
.error-msg { margin-top: 8px; color: var(--gt-color-coral, #e74c3c); font-size: 13px; }
</style>
