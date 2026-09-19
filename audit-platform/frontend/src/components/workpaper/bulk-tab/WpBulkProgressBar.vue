<template>
  <div class="gt-bulk-progress">
    <div class="header">
      <span class="label">{{ label }}</span>
      <span class="count">{{ current }} / {{ total || '?' }}</span>
    </div>
    <el-progress
      :percentage="percent"
      :indeterminate="indeterminate"
      :duration="2"
      :status="progressStatus"
      :stroke-width="8"
    />
    <div v-if="message" class="msg">{{ message }}</div>
  </div>
</template>

<script setup lang="ts">
/**
 * WpBulkProgressBar — 批量导入导出 SSE 进度条
 *
 * 复用共享 SSE 封装（@/utils/sse createSSE，经 composable.subscribeProgress）。
 * - 传入 taskId 时订阅后端 GET /bulk-tab/progress/{task_id} 实时进度
 * - 未传 taskId（同步端点直返 ZIP/报告）时以不确定态动画表示"处理中"
 *
 * Requirements: 6.1
 */
import { ref, computed, watch, onUnmounted } from 'vue'
import { ElProgress } from 'element-plus'
import { useBulkTabImportExport, type BulkProgressEvent } from '@/composables/useBulkTabImportExport'

const props = defineProps<{
  /** 项目 ID */
  projectId: string
  /** 操作标题（如"导出全部模板"） */
  label?: string
  /** 异步任务 ID（同步端点无此值时留空 → 不确定态） */
  taskId?: string | null
}>()

const emit = defineEmits<{
  (e: 'complete'): void
  (e: 'error', msg: string): void
}>()

const projectIdRef = computed(() => props.projectId)
const { subscribeProgress, closeProgress } = useBulkTabImportExport(projectIdRef)

const current = ref(0)
const total = ref(0)
const message = ref<string>('')
const status = ref<'running' | 'completed' | 'failed'>('running')
const label = computed(() => props.label ?? '处理中')

/** 无 taskId → 同步操作，展示不确定态 */
const indeterminate = computed(() => !props.taskId && status.value === 'running')

const percent = computed(() => {
  if (status.value === 'completed') return 100
  if (total.value <= 0) return indeterminate.value ? 100 : 0
  return Math.min(100, Math.round((current.value / total.value) * 100))
})

const progressStatus = computed<'' | 'success' | 'exception'>(() => {
  if (status.value === 'completed') return 'success'
  if (status.value === 'failed') return 'exception'
  return ''
})

let cleanup: (() => void) | null = null

function reset() {
  current.value = 0
  total.value = 0
  message.value = ''
  status.value = 'running'
}

function startSubscription(taskId: string) {
  reset()
  cleanup = subscribeProgress(taskId, (data: BulkProgressEvent) => {
    current.value = Number(data.current ?? 0)
    total.value = Number(data.total ?? total.value)
    message.value = data.message ?? ''
    if (data.status === 'completed') {
      status.value = 'completed'
      emit('complete')
    } else if (data.status === 'failed' || data.error) {
      status.value = 'failed'
      message.value = data.error || data.message || '处理失败'
      emit('error', message.value)
    } else {
      status.value = 'running'
    }
  })
}

watch(
  () => props.taskId,
  (taskId) => {
    if (cleanup) {
      cleanup()
      cleanup = null
    }
    if (taskId) {
      startSubscription(taskId)
    } else {
      reset()
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  if (cleanup) cleanup()
  closeProgress()
})
</script>

<style scoped>
.gt-bulk-progress {
  padding: 12px;
  border-radius: 6px;
  background: var(--gt-color-bg-fill, #f5f7fa);
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: 13px;
}
.label {
  font-weight: 600;
}
.count {
  color: var(--gt-color-text-secondary, #909399);
}
.msg {
  margin-top: 6px;
  font-size: 12px;
  color: var(--gt-color-text-secondary, #909399);
}
</style>
