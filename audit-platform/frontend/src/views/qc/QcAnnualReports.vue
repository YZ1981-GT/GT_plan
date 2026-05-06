<template>
  <div class="qc-annual-reports">
    <!-- 顶部横幅 -->
    <div class="gt-page-banner gt-page-banner--teal">
      <div class="gt-banner-content">
        <h2>📊 年度质量报告</h2>
        <span class="gt-banner-sub">共 {{ reports.length }} 份报告</span>
      </div>
      <div class="gt-banner-actions">
        <el-button size="small" type="primary" @click="showGenerateDialog = true">生成年报</el-button>
        <el-button size="small" @click="loadReports" :loading="loading">刷新</el-button>
      </div>
    </div>

    <!-- 报告表格 -->
    <el-table
      :data="reports"
      v-loading="loading"
      stripe
      style="width: 100%;"
    >
      <el-table-column label="年度" prop="year" width="100" align="center">
        <template #default="{ row }">
          <span style="font-weight: 600;">{{ row.year }}</span>
        </template>
      </el-table-column>

      <el-table-column label="状态" prop="status" width="140" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small" effect="dark">
            {{ statusLabel(row.status) }}
          </el-tag>
          <span v-if="row.status === 'running'" class="running-indicator" />
        </template>
      </el-table-column>

      <el-table-column label="创建时间" prop="created_at" min-width="180">
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>

      <el-table-column label="操作" width="140" align="center">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'completed'"
            size="small"
            type="primary"
            link
            @click="downloadReport(row)"
            :loading="row._downloading"
          >
            下载
          </el-button>
          <span v-else-if="row.status === 'running'" class="status-hint">生成中...</span>
          <span v-else-if="row.status === 'failed'" class="status-hint status-hint--error">生成失败</span>
          <span v-else class="status-hint">排队中</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 生成年报对话框 -->
    <el-dialog v-model="showGenerateDialog" title="生成年度质量报告" width="400px">
      <el-form :model="generateForm" label-width="80px">
        <el-form-item label="年度">
          <el-input-number
            v-model="generateForm.year"
            :min="2000"
            :max="2099"
            style="width: 100%;"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showGenerateDialog = false">取消</el-button>
        <el-button type="primary" @click="generateReport" :loading="generating">生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import http from '@/utils/http'

// ─── Types ──────────────────────────────────────────────────────────────────

interface ReportItem {
  id: string
  year: number
  status: string
  created_at: string
  _downloading?: boolean
}

// ─── State ──────────────────────────────────────────────────────────────────

const reports = ref<ReportItem[]>([])
const loading = ref(false)

// Generate dialog
const showGenerateDialog = ref(false)
const generating = ref(false)
const generateForm = ref({
  year: new Date().getFullYear(),
})

// Polling
let pollTimer: ReturnType<typeof setInterval> | null = null

// ─── Helpers ────────────────────────────────────────────────────────────────

function statusTagType(status: string): 'success' | 'warning' | 'info' | 'danger' {
  switch (status) {
    case 'completed': return 'success'
    case 'running': return 'warning'
    case 'queued': return 'info'
    case 'failed': return 'danger'
    default: return 'info'
  }
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    completed: '已完成',
    running: '生成中',
    queued: '排队中',
    failed: '失败',
  }
  return map[status] || status
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '—'
  return dateStr.replace('T', ' ').slice(0, 16)
}

function hasRunningReport(): boolean {
  return reports.value.some((r) => r.status === 'running' || r.status === 'queued')
}

// ─── Data Loading ───────────────────────────────────────────────────────────

async function loadReports() {
  loading.value = true
  try {
    const data = await api.get<any>('/api/qc/annual-reports')
    if (Array.isArray(data)) {
      reports.value = data
    } else if (data && Array.isArray(data.items)) {
      reports.value = data.items
    } else {
      reports.value = []
    }
    // Start/stop polling based on status
    managePoll()
  } catch {
    reports.value = []
  } finally {
    loading.value = false
  }
}

async function generateReport() {
  generating.value = true
  try {
    await api.post(`/api/qc/annual-reports?year=${generateForm.value.year}`)
    ElMessage.success('年报生成任务已提交')
    showGenerateDialog.value = false
    await loadReports()
  } catch {
    ElMessage.error('提交失败')
  } finally {
    generating.value = false
  }
}

async function downloadReport(row: ReportItem) {
  row._downloading = true
  try {
    const response = await http.get(`/api/qc/annual-reports/${row.id}/download`, {
      responseType: 'blob',
    })
    const blob = new Blob([response.data])
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `质量年报_${row.year}.pdf`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('下载失败')
  } finally {
    row._downloading = false
  }
}

// ─── Polling ────────────────────────────────────────────────────────────────

function managePoll() {
  if (hasRunningReport()) {
    if (!pollTimer) {
      pollTimer = setInterval(async () => {
        try {
          const data = await api.get<any>('/api/qc/annual-reports')
          if (Array.isArray(data)) {
            reports.value = data
          } else if (data && Array.isArray(data.items)) {
            reports.value = data.items
          }
          if (!hasRunningReport()) {
            stopPoll()
            ElMessage.success('年报生成完成')
          }
        } catch {
          // Ignore poll errors
        }
      }, 5000)
    }
  } else {
    stopPoll()
  }
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  loadReports()
})

onUnmounted(() => {
  stopPoll()
})
</script>

<style scoped>
.qc-annual-reports {
  padding: 0;
}

.running-indicator {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: #e6a23c;
  margin-left: 6px;
  animation: pulse 1.2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.status-hint {
  font-size: 12px;
  color: #909399;
}

.status-hint--error {
  color: #f56c6c;
}
</style>
