<template>
  <div class="import-history-entry">
    <div class="entry-header">
      <el-tag size="small" type="info">{{ entry.engine_version || 'v1' }}</el-tag>
      <span class="entry-date">{{ formatDate(entry.created_at) }}</span>
      <el-tag v-if="entry.adapter_used" size="small">
        适配器: {{ entry.adapter_used }}
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
}

defineProps<{
  entry: HistoryEntry
}>()

const emit = defineEmits<{
  'show-diagnostics': [jobId: string]
  'show-evidence': [evidence: Record<string, unknown>]
}>()

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
