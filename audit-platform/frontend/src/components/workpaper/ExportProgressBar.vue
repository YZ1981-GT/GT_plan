<script setup lang="ts">
/**
 * ExportProgressBar — 批量导出进度条（基于 SSE 推送）
 *
 * 订阅当前项目 SSE 流：
 *   - export.progress  → 更新进度
 *   - export.complete  → 显示下载链接（download_url）
 *   - export.failed    → 显示错误
 *
 * Validates: requirements.md §三 C-3
 */
import { ref, watch, onUnmounted } from 'vue'
import { ElButton, ElProgress, ElMessage } from 'element-plus'
import { eventBus, type SyncEventPayload } from '@/utils/eventBus'

const props = defineProps<{
  /** 后端任务 id（POST batch-export-async 返回） */
  taskId: string
  /** 总数（前端立即显示，避免初始空白） */
  total?: number
}>()

const emit = defineEmits<{
  (e: 'complete', downloadUrl: string): void
  (e: 'failed', error: string): void
}>()

const done = ref(0)
const total = ref(props.total ?? 0)
const percent = ref(0)
const status = ref<'pending' | 'running' | 'complete' | 'failed'>('pending')
const downloadUrl = ref<string | null>(null)
const errorMsg = ref<string | null>(null)

function onSseEvent(payload: SyncEventPayload) {
  const extra = (payload.extra || {}) as Record<string, any>
  if (extra.task_id !== props.taskId) return

  if (payload.event_type === 'export.progress') {
    done.value = Number(extra.done ?? 0)
    total.value = Number(extra.total ?? total.value)
    percent.value = Number(extra.percent ?? 0)
    status.value = 'running'
  } else if (payload.event_type === 'export.complete') {
    done.value = Number(extra.done ?? total.value)
    percent.value = 100
    status.value = 'complete'
    downloadUrl.value = String(extra.download_url ?? '')
    emit('complete', downloadUrl.value)
    ElMessage.success('批量导出已完成')
  } else if (payload.event_type === 'export.failed') {
    status.value = 'failed'
    errorMsg.value = String(extra.error ?? '导出失败')
    emit('failed', errorMsg.value)
    ElMessage.error(`批量导出失败：${errorMsg.value}`)
  }
}

eventBus.on('sse:sync-event', onSseEvent)
onUnmounted(() => {
  eventBus.off('sse:sync-event', onSseEvent)
})

watch(
  () => props.taskId,
  () => {
    done.value = 0
    percent.value = 0
    status.value = 'pending'
    downloadUrl.value = null
    errorMsg.value = null
  },
)

function triggerDownload() {
  if (downloadUrl.value) {
    window.open(downloadUrl.value, '_blank')
  }
}
</script>

<template>
  <div class="gt-export-progress">
    <div class="header">
      <span class="label">批量导出</span>
      <span class="count">{{ done }} / {{ total || '?' }}</span>
    </div>
    <el-progress
      :percentage="percent"
      :status="status === 'failed' ? 'exception' : status === 'complete' ? 'success' : undefined"
      :stroke-width="6"
    />
    <div v-if="status === 'complete' && downloadUrl" class="actions">
      <el-button type="primary" size="small" @click="triggerDownload">
        下载 ZIP
      </el-button>
    </div>
    <div v-else-if="status === 'failed'" class="error">
      {{ errorMsg }}
    </div>
  </div>
</template>

<style scoped>
.gt-export-progress {
  padding: 12px;
  border-radius: 6px;
  background: var(--gt-color-bg-fill, #f5f7fa);
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: var(--gt-font-size-sm);
}
.label { font-weight: 600; }
.count { color: var(--gt-color-text-secondary, #909399); }
.actions { margin-top: 8px; }
.error {
  margin-top: 6px;
  color: var(--gt-color-error, #f56c6c);
  font-size: var(--gt-font-size-xs);
}
</style>
