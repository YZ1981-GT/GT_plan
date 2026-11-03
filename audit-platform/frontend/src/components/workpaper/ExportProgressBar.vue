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
import { downloadFile } from '@/utils/http'
import { getWorkpaperPackExportStatus } from '@/services/workpaperApi'
import { handleApiError } from '@/utils/errorHandler'

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
let pollTimer: ReturnType<typeof setTimeout> | null = null
let pollRound = 0

function clearPoll() {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = null
}

function markComplete(url: string, nextDone: number) {
  const first = status.value !== 'complete'
  done.value = nextDone || total.value
  percent.value = 100
  status.value = 'complete'
  downloadUrl.value = url
  clearPoll()
  if (first) {
    emit('complete', url)
    ElMessage.success('批量导出已完成')
  }
}

function markFailed(error: string) {
  const first = status.value !== 'failed'
  status.value = 'failed'
  errorMsg.value = error || '导出失败'
  clearPoll()
  if (first) {
    emit('failed', errorMsg.value)
    ElMessage.error(`批量导出失败：${errorMsg.value}`)
  }
}

async function pollStatus(round: number) {
  try {
    const result = await getWorkpaperPackExportStatus(props.taskId)
    if (round !== pollRound) return
    done.value = Number(result.done ?? 0)
    total.value = Number(result.total ?? total.value)
    percent.value = Number(result.percent ?? 0)
    if (result.status === 'complete' && result.download_url) {
      markComplete(String(result.download_url), done.value)
      return
    }
    if (result.status === 'failed') {
      markFailed(String(result.error || '导出失败'))
      return
    }
    status.value = result.status === 'pending' ? 'pending' : 'running'
  } catch {
    // SSE 仍可能送达；状态轮询暂时失败不打断任务，也不刷全局提示。
  }
  if (round === pollRound) pollTimer = setTimeout(() => void pollStatus(round), 2000)
}

function onSseEvent(payload: SyncEventPayload) {
  const extra = (payload.extra || {}) as Record<string, any>
  if (extra.task_id !== props.taskId) return

  if (payload.event_type === 'export.progress') {
    done.value = Number(extra.done ?? 0)
    total.value = Number(extra.total ?? total.value)
    percent.value = Number(extra.percent ?? 0)
    status.value = 'running'
  } else if (payload.event_type === 'export.complete') {
    markComplete(String(extra.download_url ?? ''), Number(extra.done ?? total.value))
  } else if (payload.event_type === 'export.failed') {
    markFailed(String(extra.error ?? '导出失败'))
  }
}

eventBus.on('sse:sync-event', onSseEvent)
onUnmounted(() => {
  pollRound += 1
  clearPoll()
  eventBus.off('sse:sync-event', onSseEvent)
})

watch(
  () => [props.taskId, props.total] as const,
  ([taskId, initialTotal]) => {
    pollRound += 1
    clearPoll()
    done.value = 0
    total.value = initialTotal ?? 0
    percent.value = 0
    status.value = 'pending'
    downloadUrl.value = null
    errorMsg.value = null
    if (taskId) void pollStatus(pollRound)
  },
  { immediate: true },
)

async function triggerDownload() {
  if (!downloadUrl.value) return
  // 经 http 取 blob 再保存：原先 window.open 新标签页带不上 Bearer 头，恒 401
  try {
    await downloadFile(downloadUrl.value, { fileName: '底稿批量导出.zip', silent: true })
  } catch (e) {
    handleApiError(e, '下载 ZIP')
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
