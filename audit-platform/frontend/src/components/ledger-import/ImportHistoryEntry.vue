<template>
  <div class="import-history-entry">
    <div class="entry-header">
      <el-tag size="small" type="info">{{ entry.engine_version || 'v1' }}</el-tag>
      <span class="entry-date">{{ formatDate(entry.created_at) }}</span>
      <el-tag v-if="entry.adapter_used" size="small">
        适配器: {{ entry.adapter_used }}
      </el-tag>
      <!-- 8.42: retention 徽章 -->
      <el-tag
        v-if="entry.retention_class"
        :type="retentionTagType"
        size="small"
        effect="plain"
      >
        {{ retentionLabel }}
      </el-tag>
    </div>

    <div class="entry-body">
      <span class="entry-status" :class="entry.status">
        {{ getStatusLabel(entry.status) }}
      </span>
      <span v-if="entry.file_count" class="entry-meta">
        {{ entry.file_count }} 个文件
      </span>
      <span v-if="entry.total_rows" class="entry-meta">
        {{ entry.total_rows.toLocaleString() }} 行
      </span>
    </div>

    <!-- 诊断入口 -->
    <div class="entry-actions">
      <!-- 5.12: 接管导入按钮（heartbeat 超 5min 才显示） -->
      <el-button
        v-if="canTakeover"
        link
        type="danger"
        size="small"
        aria-label="接管导入"
        :loading="takeoverLoading"
        @click="onTakeover"
      >
        接管导入
      </el-button>
      <!-- 4.4: 恢复导入按钮 -->
      <el-button
        v-if="canResume"
        link
        type="warning"
        size="small"
        aria-label="恢复导入"
        :loading="resumeLoading"
        @click="onResume"
      >
        恢复导入
      </el-button>
      <el-button
        v-if="entry.job_id"
        link
        type="primary"
        size="small"
        aria-label="查看诊断详情"
        @click="emit('show-diagnostics', entry.job_id)"
      >
        诊断详情
      </el-button>
      <el-button
        v-if="entry.detection_evidence"
        link
        type="primary"
        size="small"
        aria-label="查看识别决策树"
        @click="emit('show-evidence', entry.detection_evidence)"
      >
        识别决策
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { ledgerImportV2Api } from '@/services/ledgerImportV2Api'

// ─── Props & Emits ──────────────────────────────────────────────────────────

interface HistoryEntry {
  job_id: string
  status: string
  created_at: string
  adapter_used: string | null
  engine_version: string | null
  detection_evidence: Record<string, unknown> | null
  file_count?: number
  total_rows?: number
  retention_class?: 'transient' | 'archived' | 'legal_hold' | null
  project_id?: string
  heartbeat_at?: string | null
  lock_info?: { holder_id?: string; holder_name?: string } | null
}

const props = defineProps<{
  entry: HistoryEntry
  projectId?: string
}>()

const emit = defineEmits<{
  'show-diagnostics': [jobId: string]
  'show-evidence': [evidence: Record<string, unknown>]
  'resumed': [jobId: string]
  'taken-over': [jobId: string]
}>()

// ─── Resume (4.4) ───────────────────────────────────────────────────────────

const resumeLoading = ref(false)

/** Show resume button only for failed/timed_out jobs */
const canResume = computed(() => {
  return props.entry.job_id && ['failed', 'timed_out'].includes(props.entry.status)
})

async function onResume() {
  const pid = props.projectId || props.entry.project_id
  if (!pid || !props.entry.job_id) return
  resumeLoading.value = true
  try {
    await ledgerImportV2Api.resume(pid, props.entry.job_id)
    ElMessage.success('已恢复导入任务')
    emit('resumed', props.entry.job_id)
  } catch (e: any) {
    ElMessage.error(e?.message || '恢复导入失败')
  } finally {
    resumeLoading.value = false
  }
}

// ─── Takeover (5.12) ────────────────────────────────────────────────────────

const takeoverLoading = ref(false)

/** Show takeover button when job is running but heartbeat is stale (>5min) */
const canTakeover = computed(() => {
  if (!props.entry.job_id) return false
  if (props.entry.status !== 'running') return false
  if (!props.entry.heartbeat_at) return false
  // Check if heartbeat is older than 5 minutes
  const heartbeat = new Date(props.entry.heartbeat_at).getTime()
  const fiveMinAgo = Date.now() - 5 * 60 * 1000
  return heartbeat < fiveMinAgo
})

async function onTakeover() {
  const pid = props.projectId || props.entry.project_id
  if (!pid || !props.entry.job_id) return

  const { ElMessageBox } = await import('element-plus')
  try {
    const { value: reason } = await ElMessageBox.prompt(
      '请输入接管原因（如：原操作人离线）',
      '接管导入',
      { confirmButtonText: '确认接管', cancelButtonText: '取消', inputPlaceholder: '接管原因' }
    )
    takeoverLoading.value = true
    await ledgerImportV2Api.takeover(pid, props.entry.job_id)
    ElMessage.success('已接管导入任务')
    emit('taken-over', props.entry.job_id)
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      ElMessage.error(e?.message || '接管失败')
    }
  } finally {
    takeoverLoading.value = false
  }
}

// ─── Retention badge (8.42) ─────────────────────────────────────────────────

const RETENTION_MAP: Record<string, { label: string; type: '' | 'info' | 'danger' }> = {
  transient: { label: '临时(90天)', type: 'info' },
  archived: { label: '归档(10年)', type: '' },
  legal_hold: { label: '法定保留', type: 'danger' },
}

const retentionTagType = computed(() => {
  return RETENTION_MAP[props.entry.retention_class || '']?.type || 'info'
})

const retentionLabel = computed(() => {
  return RETENTION_MAP[props.entry.retention_class || '']?.label || props.entry.retention_class
})

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatDate(dateStr: string): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function getStatusLabel(status: string): string {
  const map: Record<string, string> = {
    completed: '✓ 完成',
    failed: '✗ 失败',
    running: '⟳ 进行中',
    queued: '⏳ 排队中',
    canceled: '⊘ 已取消',
    timed_out: '⏱ 超时',
  }
  return map[status] || status
}
</script>

<style scoped>
.import-history-entry {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  margin-bottom: 8px;
}

.entry-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.entry-date {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.entry-body {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}

.entry-status {
  font-weight: 500;
}

.entry-status.completed { color: var(--el-color-success); }
.entry-status.failed { color: var(--el-color-danger); }
.entry-status.running { color: var(--el-color-primary); }

.entry-meta {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.entry-actions {
  margin-top: 6px;
  display: flex;
  gap: 8px;
}
</style>
