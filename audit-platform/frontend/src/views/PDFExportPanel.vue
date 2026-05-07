<template>
  <div class="gt-pdf-export gt-fade-in">
    <!-- 页面横幅 -->
    <div class="gt-pe-banner">
      <div class="gt-pe-banner-text">
        <h2>PDF 导出</h2>
        <p>选择文档 · 设置密码 · 一键导出</p>
      </div>
    </div>

    <el-row :gutter="16">
      <!-- 左侧：导出配置 -->
      <el-col :span="10">
        <div class="gt-pe-panel">
          <h4 class="gt-pe-panel-title">文档选择</h4>
          <el-checkbox-group v-model="selectedDocs" class="gt-pe-doc-checkboxes">
            <el-checkbox value="audit_report" label="审计报告" />
            <el-checkbox value="balance_sheet" label="资产负债表" />
            <el-checkbox value="income_statement" label="利润表" />
            <el-checkbox value="cash_flow_statement" label="现金流量表" />
            <el-checkbox value="equity_statement" label="所有者权益变动表" />
            <el-checkbox value="disclosure_notes" label="财务报表附注" />
          </el-checkbox-group>

          <el-divider />

          <h4 class="gt-pe-panel-title">导出选项</h4>
          <el-form label-width="100px">
            <el-form-item label="密码保护">
              <el-switch v-model="passwordProtected" />
            </el-form-item>
            <el-form-item v-if="passwordProtected" label="密码">
              <el-input v-model="password" type="password" show-password placeholder="设置PDF打开密码" />
            </el-form-item>
            <el-form-item label="报表语言">
              <el-select v-model="exportLanguage" style="width: 100%" placeholder="选择导出语言">
                <el-option label="中文" value="zh-CN" />
                <el-option label="English" value="en-US" />
              </el-select>
            </el-form-item>
          </el-form>

          <el-button type="primary" @click="onExport" :loading="exportLoading"
            :disabled="selectedDocs.length === 0" style="width: 100%; margin-top: 12px"
            v-permission="'report:export'">
            开始导出
          </el-button>

          <!-- 进度条 -->
          <div v-if="currentTask" class="gt-pe-progress-section">
            <el-divider />
            <div class="gt-pe-progress-info">
              <span>状态: {{ taskStatusLabel(currentTask.status) }}</span>
              <span>{{ currentTask.progress_percentage }}%</span>
            </div>
            <el-progress :percentage="currentTask.progress_percentage"
              :status="progressStatus(currentTask.status)" :stroke-width="12" />
            <div v-if="currentTask.status === 'completed'" class="gt-pe-download-link">
              <el-button type="success" @click="onDownload(currentTask.id)">下载 PDF</el-button>
              <span v-if="currentTask.file_size" class="gt-pe-file-size">
                {{ formatFileSize(currentTask.file_size) }}
              </span>
            </div>
            <div v-if="currentTask.status === 'failed'" class="gt-pe-error-msg">
              {{ currentTask.error_message || '导出失败' }}
            </div>
          </div>
        </div>
      </el-col>

      <!-- 右侧：历史记录 -->
      <el-col :span="14">
        <div class="gt-pe-panel">
          <h4 class="gt-pe-panel-title">导出历史</h4>
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
                <el-tag :type="(statusTagType(row.status)) || undefined" size="small">{{ taskStatusLabel(row.status) }}</el-tag>
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
const exportLanguage = ref('zh-CN')
const exportLoading = ref(false)
const historyLoading = ref(false)
const currentTask = ref<ExportTaskData | null>(null)
const history = ref<ExportTaskData[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

function taskStatusLabel(s: string) {
  const m: Record<string, string> = { queued: '排队中', processing: '处理中', completed: '已完成', failed: '失败' }
  return m[s] || s
}

function statusTagType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = { queued: 'info', processing: 'warning', completed: 'success', failed: 'danger' }
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
  import('@/services/commonApi').then(({ downloadFileAsBlob }) => {
    downloadFileAsBlob(getExportDownloadUrl(taskId), `审计报告_${taskId.slice(0, 8)}.pdf`)
  })
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
.gt-pdf-export { padding: var(--gt-space-5); }

/* ── 页面横幅 ── */
.gt-pe-banner {
  display: flex; justify-content: space-between; align-items: center;
  background: var(--gt-gradient-primary);
  border-radius: var(--gt-radius-lg);
  padding: 20px 28px;
  margin-bottom: var(--gt-space-5);
  color: #fff;
  position: relative; overflow: hidden;
  box-shadow: 0 4px 20px rgba(75, 45, 119, 0.2);
  background-image: var(--gt-gradient-primary), linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 100% 100%, 20px 20px, 20px 20px;
}
.gt-pe-banner::before {
  content: '';
  position: absolute; top: -40%; right: -10%;
  width: 45%; height: 180%;
  background: radial-gradient(ellipse, rgba(255,255,255,0.07) 0%, transparent 65%);
  pointer-events: none;
}
.gt-pe-banner-text h2 { margin: 0 0 2px; font-size: 18px; font-weight: 700; }
.gt-pe-banner-text p { margin: 0; font-size: 12px; opacity: 0.75; }

.gt-pe-panel {
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  padding: var(--gt-space-5); box-shadow: var(--gt-shadow-sm);
  border: 1px solid rgba(75, 45, 119, 0.04);
}
.gt-pe-panel-title {
  margin: 0 0 var(--gt-space-3); font-size: var(--gt-font-size-md); font-weight: 600;
  color: var(--gt-color-primary);
  display: flex; align-items: center; gap: 8px;
}
.gt-pe-panel-title::before {
  content: '';
  width: 3px; height: 14px;
  background: var(--gt-gradient-primary);
  border-radius: 2px;
}
.gt-pe-doc-checkboxes { display: flex; flex-direction: column; gap: var(--gt-space-3); }
.gt-pe-progress-section { margin-top: var(--gt-space-3); }
.gt-pe-progress-info { display: flex; justify-content: space-between; margin-bottom: 6px; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); }
.gt-pe-download-link { margin-top: var(--gt-space-3); display: flex; align-items: center; gap: var(--gt-space-2); }
.gt-pe-file-size { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-pe-error-msg { margin-top: var(--gt-space-2); color: var(--gt-color-coral); font-size: var(--gt-font-size-sm); }
</style>
